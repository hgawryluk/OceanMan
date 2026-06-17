import io
import re
from datetime import datetime
from urllib.parse import urljoin

import httpx
import pdfplumber
from bs4 import BeautifulSoup

from models import PoolSchedule, SlotReading

PAGE_URL = "https://sport.um.warszawa.pl/waw/osir-zoliborz/-/plywalnia-potocka"
BASE_URL = "https://sport.um.warszawa.pl"
HEADERS = {"User-Agent": "OceanMan/1.0 (personal pool schedule tracker)"}
TOTAL_LANES = 8

# Columns per day block: GODZ./TOR, 1, 2, 3, 4, 5, 6, R, B  (9 total)
COLS_PER_DAY = 9
LANE_COLS = 8  # lanes 1-6 plus R (rekreacja) and B (brodzik) — all 8 take reservations

TIME_RE = re.compile(r"^(\d{1,2})\.(\d{2})-(\d{1,2})\.(\d{2})$")
DATE_RE = re.compile(r"(\d{2})\.(\d{2})\.(\d{4})")


def _parse_time(s: str) -> tuple[str, str] | None:
    m = TIME_RE.match(s.strip())
    if not m:
        return None
    h1, m1, h2, m2 = m.groups()
    return f"{int(h1):02d}:{m1}", f"{int(h2):02d}:{m2}"


def _is_white(color) -> bool:
    if color is None:
        return True
    if isinstance(color, (int, float)):
        return color >= 0.85
    if isinstance(color, (list, tuple)):
        if len(color) == 4 and all(c == 0 for c in color):
            return True  # CMYK (0,0,0,0) = white
        return all(c >= 0.85 for c in color[:3])
    return True


def _cell_is_free(cell_rects: list) -> bool:
    if not cell_rects:
        return True
    return all(_is_white(r.get("non_stroking_color")) for r in cell_rects)


def discover() -> str | None:
    try:
        resp = httpx.get(PAGE_URL, timeout=20, follow_redirects=True, headers=HEADERS)
        resp.raise_for_status()
    except Exception:
        return None
    soup = BeautifulSoup(resp.text, "lxml")
    candidates: list[tuple[datetime, str]] = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if ".pdf" not in href.lower():
            continue
        text = a.get_text(" ", strip=True)
        text_lower = text.lower()
        if "grafik" not in text_lower or ("pływalni" not in text_lower and "tor" not in text_lower):
            continue
        # Extract the latest DD.MM.YYYY date from link text to rank schedules
        dates = DATE_RE.findall(text)
        if dates:
            d, mo, y = int(dates[-1][0]), int(dates[-1][1]), int(dates[-1][2])
            full_url = urljoin(BASE_URL, href) if href.startswith("/") else href
            candidates.append((datetime(y, mo, d), full_url))
    if not candidates:
        return None
    return max(candidates, key=lambda x: x[0])[1]


def parse(pdf_bytes: bytes, source_url: str, source_hash: str) -> PoolSchedule:
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        slots = _parse_page(pdf.pages[0])

    if not slots:
        raise ValueError("Potocka: parser produced no slots")

    return PoolSchedule(
        pool="potocka",
        valid_from=None,
        fetched_at=datetime.now(),
        source_url=source_url,
        source_hash=source_hash,
        slots=slots,
    )


def _parse_page(page) -> list[SlotReading]:
    tables = page.find_tables()
    if not tables:
        return []
    t = tables[0]

    # --- Find the column-header row (contains "GODZ./TOR") ---
    header_y: float | None = None
    for cell in sorted(t.cells, key=lambda c: (c[1], c[0])):
        if (page.crop(cell).extract_text() or "").strip() == "GODZ./TOR":
            header_y = cell[1]
            break
    if header_y is None:
        return []

    header_cells = sorted(
        [c for c in t.cells if abs(c[1] - header_y) < 2],
        key=lambda c: c[0],
    )
    if len(header_cells) < COLS_PER_DAY * 7:
        return []

    # --- Build day structure from header cells ---
    # Each 9-cell block: [GODZ./TOR, 1, 2, 3, 4, 5, 6, R, B]
    day_structures: list[dict] = []
    for day_idx in range(7):
        base = day_idx * COLS_PER_DAY
        godz_cell = header_cells[base]
        lane_cells = header_cells[base + 1: base + 1 + LANE_COLS]
        day_structures.append({
            "godz_x": (godz_cell[0], godz_cell[2]),
            "lane_xs": [(c[0], c[2]) for c in lane_cells],
        })

    # --- Detect weekday for each day from date in the day-name row ---
    # Day-name cells are above the header row
    day_name_row = sorted(
        [c for c in t.cells if c[1] < header_y - 2 and c[3] > header_y - 20],
        key=lambda c: c[0],
    )
    weekdays: list[str] = []
    for cell in day_name_row:
        txt = (page.crop(cell).extract_text() or "").strip()
        m = DATE_RE.search(txt)
        if m:
            d, mo, y = int(m[1]), int(m[2]), int(m[3])
            weekdays.append(datetime(y, mo, d).strftime("%A").lower())
    if len(weekdays) < 7:
        # Fallback: fixed Mon–Sun order
        weekdays = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]

    # --- Find time-row y-positions from first GODZ./TOR column ---
    gx0, gx1 = day_structures[0]["godz_x"]
    time_cells = sorted(
        [c for c in t.cells if abs(c[0] - gx0) < 2 and abs(c[2] - gx1) < 2],
        key=lambda c: c[1],
    )

    # --- Collect filled rects once ---
    filled_rects = [r for r in page.rects if r.get("fill")]

    # --- Build slots ---
    slots: list[SlotReading] = []

    for tc in time_cells:
        time_txt = (page.crop(tc).extract_text() or "").strip()
        parsed = _parse_time(time_txt)
        if not parsed:
            continue
        slot_start, slot_end = parsed
        y0, y1 = tc[1], tc[3]

        for day_idx, weekday in enumerate(weekdays):
            if day_idx >= len(day_structures):
                break
            free = 0
            for lx0, lx1 in day_structures[day_idx]["lane_xs"]:
                cell_rects = [
                    r for r in filled_rects
                    if r["x0"] < lx1 - 0.5 and r["x1"] > lx0 + 0.5
                    and r["top"] < y1 - 0.5 and r["bottom"] > y0 + 0.5
                ]
                if _cell_is_free(cell_rects):
                    free += 1

            slots.append(SlotReading(
                pool="potocka",
                weekday=weekday,
                slot_start=slot_start,
                slot_end=slot_end,
                free_lanes=free,
                total_lanes=TOTAL_LANES,
            ))

    return slots
