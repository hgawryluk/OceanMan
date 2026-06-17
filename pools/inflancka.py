import io
import re
from datetime import datetime
from urllib.parse import urljoin

import httpx
import pdfplumber
from bs4 import BeautifulSoup

from models import PoolSchedule, SlotReading

PAGE_URL = "https://sport.um.warszawa.pl/waw/aktywna-warszawa/harmonogramy-w-osrodku-inflancka"
BASE_URL = "https://sport.um.warszawa.pl"
HEADERS = {"User-Agent": "OceanMan/1.0 (personal pool schedule tracker)"}

WEEKDAY_MAP = {
    "poniedziałek": "monday",
    "wtorek": "tuesday",
    "środa": "wednesday",
    "czwartek": "thursday",
    "piątek": "friday",
    "sobota": "saturday",
    "niedziela": "sunday",
}

TIME_RE = re.compile(r"^\d{2}:\d{2}$")
LANE_NUMS = set(map(str, range(10)))

# Color of a free ("Tory dostępne") cell in the PDF color legend.
FREE_COLOR = (0.706, 0.776, 0.906)
COLOR_TOL = 0.03


def _color_is_free(color) -> bool:
    if not isinstance(color, (tuple, list)) or len(color) < 3:
        return False
    return all(abs(color[i] - FREE_COLOR[i]) < COLOR_TOL for i in range(3))


def discover() -> str | None:
    try:
        resp = httpx.get(PAGE_URL, timeout=20, follow_redirects=True, headers=HEADERS)
        resp.raise_for_status()
    except Exception:
        return None
    soup = BeautifulSoup(resp.text, "lxml")
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if ".pdf" not in href.lower():
            continue
        text = a.get_text(" ", strip=True).lower()
        if "pływalni" in text or ("harmonogram" in text and "tor" in text):
            return urljoin(BASE_URL, href) if href.startswith("/") else href
    return None


def _parse_page(page) -> tuple[str | None, list[SlotReading]]:
    # --- Detect weekday from table text ---
    weekday: str | None = None
    raw_table = page.extract_table()
    if raw_table:
        for row in raw_table[:4]:
            if not row:
                continue
            for cell in row:
                if not cell:
                    continue
                key = cell.strip().lower()
                if key in WEEKDAY_MAP:
                    weekday = WEEKDAY_MAP[key]
                    break
            if weekday:
                break

    if not weekday:
        return None, []

    # --- Find table structure ---
    tables = page.find_tables()
    if not tables:
        return weekday, []
    t = tables[0]

    # Find Od, Do and lane column x-ranges from header cells
    od_x = do_x = None
    lane_xs: dict[int, tuple[float, float]] = {}

    for cell in sorted(t.cells, key=lambda c: (c[1], c[0])):
        txt = (page.crop(cell).extract_text() or "").strip()
        if txt == "Od" and od_x is None:
            od_x = (cell[0], cell[2])
        elif txt == "Do" and do_x is None:
            do_x = (cell[0], cell[2])
        elif txt in LANE_NUMS:
            lane = int(txt)
            if lane not in lane_xs:
                lane_xs[lane] = (cell[0], cell[2])
        if od_x and do_x and len(lane_xs) == 10:
            break

    if od_x is None or do_x is None or not lane_xs:
        return weekday, []

    # Find row y-positions from Od column cells
    od_cells = sorted(
        [c for c in t.cells if abs(c[0] - od_x[0]) < 2 and abs(c[2] - od_x[1]) < 2],
        key=lambda c: c[1],
    )
    do_map = {
        c[1]: c
        for c in t.cells
        if abs(c[0] - do_x[0]) < 2 and abs(c[2] - do_x[1]) < 2
    }

    # Collect filled rects once for the page
    filled_rects = [
        r for r in page.rects
        if r.get("fill") and r.get("non_stroking_color") is not None
        and r["x1"] > r["x0"] and r["bottom"] > r["top"]
    ]

    # --- Build slots using color detection ---
    total_lanes = len(lane_xs)
    slots: list[SlotReading] = []

    for od_cell in od_cells:
        od_txt = (page.crop(od_cell).extract_text() or "").strip()
        if not TIME_RE.match(od_txt):
            continue
        do_c = do_map.get(od_cell[1])
        if not do_c:
            continue
        do_txt = (page.crop(do_c).extract_text() or "").strip()
        if not TIME_RE.match(do_txt):
            continue

        y0, y1 = od_cell[1], od_cell[3]
        free = 0
        for lane, (x0, x1) in lane_xs.items():
            cell_rects = [
                r for r in filled_rects
                if r["x0"] < x1 - 1 and r["x1"] > x0 + 1
                and r["top"] < y1 - 1 and r["bottom"] > y0 + 1
            ]
            if any(_color_is_free(r["non_stroking_color"]) for r in cell_rects):
                free += 1

        slots.append(SlotReading(
            pool="inflancka",
            weekday=weekday,
            slot_start=od_txt,
            slot_end=do_txt,
            free_lanes=free,
            total_lanes=total_lanes,
        ))

    return weekday, slots


def parse(pdf_bytes: bytes, source_url: str, source_hash: str) -> PoolSchedule:
    all_slots: list[SlotReading] = []

    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        for page in pdf.pages:
            _, slots = _parse_page(page)
            all_slots.extend(slots)

    if not all_slots:
        raise ValueError("Inflancka: parser produced no slots")

    return PoolSchedule(
        pool="inflancka",
        valid_from=None,
        fetched_at=datetime.now(),
        source_url=source_url,
        source_hash=source_hash,
        slots=all_slots,
    )
