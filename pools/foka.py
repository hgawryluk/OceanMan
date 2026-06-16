import io
import re
from datetime import datetime
from urllib.parse import urljoin

import httpx
import pdfplumber
from bs4 import BeautifulSoup

from models import PoolSchedule, SlotReading

PAGE_URL = "https://sport.um.warszawa.pl/waw/osir-wola/-/plywalnia-kryta-foka-esperanto-5"
BASE_URL = "https://sport.um.warszawa.pl"
HEADERS = {"User-Agent": "OceanMan/1.0 (personal pool schedule tracker)"}

WEEKDAY_MAP = {
    "sobota": "saturday",
    "niedziela": "sunday",
    "poniedziałek": "monday",
    "wtorek": "tuesday",
    "środa": "wednesday",
    "czwartek": "thursday",
    "piątek": "friday",
}

TIME_RE = re.compile(r"^(\d{1,2})[:\.](\d{2})$")
TOTAL_LANES = 6
WHITE_THRESHOLD = 0.85


def _is_white(color) -> bool:
    if color is None:
        return True
    if isinstance(color, (int, float)):
        return color >= WHITE_THRESHOLD
    if isinstance(color, (list, tuple)):
        if len(color) == 4 and all(c == 0 for c in color):
            return True  # CMYK (0,0,0,0) = white
        return all(c >= WHITE_THRESHOLD for c in color[:3])
    return True


def discover() -> str | None:
    resp = httpx.get(PAGE_URL, timeout=20, follow_redirects=True, headers=HEADERS)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "lxml")

    for a in soup.find_all("a", href=True):
        href = a["href"]
        if ".pdf" not in href.lower():
            continue
        text = a.get_text(" ", strip=True).lower()
        if "rezerwac" in text or "wykaz" in text or ("wolnych" in text and "tor" in text):
            return urljoin(BASE_URL, href) if href.startswith("/") else href

    return None


def _build_geometry(page):
    """
    Derive time-slot y-bounds and per-lane x-bounds from PDF text positions.

    Returns:
        time_slots: list of (slot_start, slot_end, y_top, y_bottom)
        day_lanes:  list of (weekday_str, [(x0, x1), ...]) — 6 lanes per day
    """
    words = page.extract_words(keep_blank_chars=False, x_tolerance=3, y_tolerance=3)
    page_w = page.width

    # --- Time label positions (leftmost 20% of page width) ---
    time_ys: dict[str, list[float]] = {}
    for w in words:
        m = TIME_RE.match(w["text"].strip())
        if not m:
            continue
        h, mn = int(m.group(1)), int(m.group(2))
        if not (0 <= h <= 23 and mn in (0, 30)):
            continue
        if w["x0"] > page_w * 0.2:
            continue
        key = f"{h:02d}:{mn:02d}"
        time_ys.setdefault(key, []).append((w["top"] + w["bottom"]) / 2)

    avg_y = {t: sum(ys) / len(ys) for t, ys in time_ys.items()}
    sorted_times = sorted(avg_y)

    time_slots = []
    for i in range(len(sorted_times) - 1):
        t0, t1 = sorted_times[i], sorted_times[i + 1]
        h0, m0 = map(int, t0.split(":"))
        h1, m1 = map(int, t1.split(":"))
        if h1 * 60 + m1 - h0 * 60 - m0 != 30:
            continue
        y0, y1 = avg_y[t0], avg_y[t1]
        time_slots.append((t0, t1, min(y0, y1) - 2, max(y0, y1) + 2))

    # --- Day header positions ---
    day_headers = []
    for w in words:
        key = w["text"].lower().strip()
        if key in WEEKDAY_MAP:
            day_headers.append({
                "weekday": WEEKDAY_MAP[key],
                "x": (w["x0"] + w["x1"]) / 2,
                "y": (w["top"] + w["bottom"]) / 2,
            })

    if not day_headers:
        return time_slots, []

    # Deduplicate: PDF has two grids (public/reservation), each with its own weekday labels.
    # Keep the rightmost occurrence of each weekday — that's the reservation grid.
    seen: dict[str, dict] = {}
    for d in day_headers:
        if d["weekday"] not in seen or d["x"] > seen[d["weekday"]]["x"]:
            seen[d["weekday"]] = d
    day_headers = sorted(seen.values(), key=lambda d: d["x"])
    header_y = sum(d["y"] for d in day_headers) / len(day_headers)

    # --- Lane number sub-headers (digits 1–6 near the header row) ---
    lane_ws = []
    for w in words:
        if w["text"].strip() not in ("1", "2", "3", "4", "5", "6"):
            continue
        wy = (w["top"] + w["bottom"]) / 2
        if abs(wy - header_y) > 60:
            continue
        lane_ws.append({"x": (w["x0"] + w["x1"]) / 2})

    lane_ws.sort(key=lambda w: w["x"])

    day_lanes = []
    n_days = len(day_headers)

    if len(lane_ws) == n_days * 6:
        for i, day in enumerate(day_headers):
            group = lane_ws[i * 6: i * 6 + 6]
            xs = [lw["x"] for lw in group]
            spacing = (xs[-1] - xs[0]) / 5 if len(xs) > 1 else 15
            lanes = [(x - spacing / 2, x + spacing / 2) for x in xs]
            day_lanes.append((day["weekday"], lanes))
    else:
        # Fallback: divide each day's x-range evenly into 6 lanes
        for i, day in enumerate(day_headers):
            if i < n_days - 1:
                half_w = (day_headers[i + 1]["x"] - day["x"]) / 2
            else:
                half_w = (day["x"] - day_headers[i - 1]["x"]) / 2
            x0 = day["x"] - half_w
            lw = half_w * 2 / 6
            lanes = [(x0 + j * lw, x0 + (j + 1) * lw) for j in range(6)]
            day_lanes.append((day["weekday"], lanes))

    return time_slots, day_lanes


def parse(pdf_bytes: bytes, source_url: str, source_hash: str) -> PoolSchedule:
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        page = pdf.pages[0]
        time_slots, day_lanes = _build_geometry(page)

    if not time_slots:
        raise ValueError("Foka: could not detect time slots in PDF")
    if not day_lanes:
        raise ValueError("Foka: could not detect day columns in PDF")

    # Derive grid y-bounds from detected time slots to exclude header/footer decorations.
    grid_y_top = min(s[2] for s in time_slots)
    grid_y_bot = max(s[3] for s in time_slots)

    MIN_LANE_OVERLAP = 3.0  # px — avoids thin borders being counted

    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        page = pdf.pages[0]
        colored = [
            {
                "x0": r["x0"], "x1": r["x1"],
                "yc": (r["top"] + r["bottom"]) / 2,
            }
            for r in page.rects
            if (
                r.get("fill")
                and not _is_white(r.get("non_stroking_color"))
                and (r["x1"] - r["x0"]) >= 5
                and (r["bottom"] - r["top"]) >= 5
                and grid_y_top <= (r["top"] + r["bottom"]) / 2 <= grid_y_bot
            )
        ]

    slots = []
    for weekday, lanes in day_lanes:
        for slot_start, slot_end, y_top, y_bot in time_slots:
            free = 0
            for lane_x0, lane_x1 in lanes:
                reserved = any(
                    min(rc["x1"], lane_x1) - max(rc["x0"], lane_x0) >= MIN_LANE_OVERLAP
                    and y_top <= rc["yc"] <= y_bot
                    for rc in colored
                )
                if not reserved:
                    free += 1
            slots.append(SlotReading(
                pool="foka",
                weekday=weekday,
                slot_start=slot_start,
                slot_end=slot_end,
                free_lanes=free,
                total_lanes=TOTAL_LANES,
            ))

    if not slots:
        raise ValueError("Foka: parser produced no slots")

    return PoolSchedule(
        pool="foka",
        valid_from=None,
        fetched_at=datetime.now(),
        source_url=source_url,
        source_hash=source_hash,
        slots=slots,
    )
