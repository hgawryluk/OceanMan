import io
import re
from datetime import datetime
from urllib.parse import urljoin

import httpx
import openpyxl
import pdfplumber
from bs4 import BeautifulSoup

from models import PoolSchedule, SlotReading

PAGE_URL = "https://sport.um.warszawa.pl/waw/osir-wola/-/plywalnia-kryta-delfin-kasprzaka-1-3"
BASE_URL = "https://sport.um.warszawa.pl"
HEADERS = {"User-Agent": "OceanMan/1.0 (personal pool schedule tracker)"}

WEEKDAY_MAP = {
    "pon.": "monday",
    "wt.": "tuesday",
    "śr.": "wednesday",
    "czw.": "thursday",
    "pt.": "friday",
    "sob.": "saturday",
    "niedz.": "sunday",
}

TIME_RE = re.compile(r"(\d{2})[.\:](\d{2})-(\d{2})[.\:](\d{2})")
DATE_RE = re.compile(r"(\d{2})\.(\d{2})\.(\d{4})")


def discover() -> str | None:
    resp = httpx.get(PAGE_URL, timeout=20, follow_redirects=True, headers=HEADERS)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "lxml")

    candidates: list[tuple[datetime, str]] = []
    fallback: str | None = None

    for a in soup.find_all("a", href=True):
        href = a["href"]
        href_lower = href.lower()
        is_doc = (
            href_lower.endswith(".pdf") or ".pdf/" in href_lower
            or href_lower.endswith(".xlsx") or ".xlsx/" in href_lower
        )
        if not is_doc:
            continue
        text = a.get_text(" ", strip=True)
        text_lower = text.lower()
        is_match = (
            ("grafik" in text_lower and "tor" in text_lower and "brodzik" not in text_lower and "niecki" not in text_lower)
            or ("wolnych" in text_lower and "tor" in text_lower)
        )
        if not is_match:
            continue
        full_url = urljoin(BASE_URL, href) if href.startswith("/") else href
        dates = DATE_RE.findall(text)
        if dates:
            d, mo, y = int(dates[-1][0]), int(dates[-1][1]), int(dates[-1][2])
            candidates.append((datetime(y, mo, d), full_url))
        else:
            fallback = full_url

    if candidates:
        return max(candidates, key=lambda x: x[0])[1]
    return fallback


def parse(file_bytes: bytes, source_url: str, source_hash: str) -> PoolSchedule:
    if ".xlsx" in source_url.lower():
        return _parse_xlsx(file_bytes, source_url, source_hash)
    return _parse_pdf(file_bytes, source_url, source_hash)


def _parse_xlsx(file_bytes: bytes, source_url: str, source_hash: str) -> PoolSchedule:
    wb = openpyxl.load_workbook(io.BytesIO(file_bytes))
    ws = wb.active

    slots = []
    col_to_day: dict[int, str] = {}

    for row in ws.iter_rows(values_only=True):
        if not col_to_day:
            for i, cell in enumerate(row):
                if isinstance(cell, str) and cell.strip().lower() in WEEKDAY_MAP:
                    col_to_day[i] = WEEKDAY_MAP[cell.strip().lower()]
            continue

        time_cell = row[1] if len(row) > 1 else None
        if not isinstance(time_cell, str):
            continue
        m = TIME_RE.match(time_cell.strip())
        if not m:
            continue
        h1, m1, h2, m2 = m.groups()
        slot_start = f"{h1}:{m1}"
        slot_end = f"{h2}:{m2}"

        for col_idx, weekday in col_to_day.items():
            if col_idx >= len(row):
                continue
            try:
                free = int(row[col_idx])
            except (ValueError, TypeError):
                continue
            slots.append(SlotReading(
                pool="delfin",
                weekday=weekday,
                slot_start=slot_start,
                slot_end=slot_end,
                free_lanes=free,
                total_lanes=6,
            ))

    if not slots:
        raise ValueError("XLSX parser produced no slots — structure may have changed")

    return PoolSchedule(
        pool="delfin",
        valid_from=None,
        fetched_at=datetime.now(),
        source_url=source_url,
        source_hash=source_hash,
        slots=slots,
    )


def _parse_pdf(pdf_bytes: bytes, source_url: str, source_hash: str) -> PoolSchedule:
    slots = []
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        page = pdf.pages[0]
        table = page.extract_table()

    if not table:
        raise ValueError("No table found in Delfin PDF")

    header_row: list | None = None
    for row in table:
        if row is None:
            continue
        cleaned = [c.strip() if c else "" for c in row]
        if any(c.lower() in WEEKDAY_MAP for c in cleaned):
            header_row = cleaned
            break

    if not header_row:
        raise ValueError("Could not find day-header row in Delfin PDF")

    col_to_day: dict[int, str] = {}
    for i, cell in enumerate(header_row):
        key = cell.lower().strip()
        if key in WEEKDAY_MAP:
            col_to_day[i] = WEEKDAY_MAP[key]

    time_col = min(col_to_day.keys()) - 1 if col_to_day else 1

    for row in table:
        if row is None:
            continue
        cells = [c.strip() if c else "" for c in row]
        if len(cells) <= time_col or not cells[time_col]:
            continue
        m = TIME_RE.match(cells[time_col])
        if not m:
            continue
        h1, m1, h2, m2 = m.groups()
        slot_start = f"{h1}:{m1}"
        slot_end = f"{h2}:{m2}"

        for col_idx, weekday in col_to_day.items():
            if col_idx >= len(cells):
                continue
            try:
                free = int(cells[col_idx])
            except (ValueError, TypeError):
                continue
            slots.append(SlotReading(
                pool="delfin",
                weekday=weekday,
                slot_start=slot_start,
                slot_end=slot_end,
                free_lanes=free,
                total_lanes=6,
            ))

    if not slots:
        raise ValueError("Parser produced no slots — table structure may have changed")

    return PoolSchedule(
        pool="delfin",
        valid_from=None,
        fetched_at=datetime.now(),
        source_url=source_url,
        source_hash=source_hash,
        slots=slots,
    )
