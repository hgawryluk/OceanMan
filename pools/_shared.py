"""Constants and helpers shared by all pool parser modules."""
import re
from datetime import datetime
from typing import Callable
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup

BASE_URL = "https://sport.um.warszawa.pl"
HEADERS = {"User-Agent": "OceanMan/1.0 (personal pool schedule tracker)"}
DATE_RE = re.compile(r"(\d{2})\.(\d{2})\.(\d{4})")
WHITE_THRESHOLD = 0.85


def is_white(color) -> bool:
    """True if a PDF fill color (grayscale float, RGB(A), or CMYK tuple) is effectively white."""
    if color is None:
        return True
    if isinstance(color, (int, float)):
        return color >= WHITE_THRESHOLD
    if isinstance(color, (list, tuple)):
        if len(color) == 4 and all(c == 0 for c in color):
            return True  # CMYK (0,0,0,0) = white
        return all(c >= WHITE_THRESHOLD for c in color[:3])
    return True


def fetch_page(url: str) -> str | None:
    """GET a page's HTML, returning None on any network/HTTP error."""
    try:
        resp = httpx.get(url, timeout=20, follow_redirects=True, headers=HEADERS)
        resp.raise_for_status()
    except Exception:
        return None
    return resp.text


def find_latest_document_link(
    html: str,
    matches: Callable[[str], bool],
    extensions: tuple[str, ...] = (".pdf",),
    base_url: str = BASE_URL,
) -> str | None:
    """
    Scan an HTML page for <a href> links to documents (whose href contains one
    of `extensions`) with visible text satisfying `matches(text_lower)`.

    Ranks candidates by the latest DD.MM.YYYY date found in the link text; if
    no candidate carries a date, falls back to the first match encountered.
    Returns None if nothing matches.
    """
    soup = BeautifulSoup(html, "lxml")
    candidates: list[tuple[datetime, str]] = []
    fallback: str | None = None

    for a in soup.find_all("a", href=True):
        href = a["href"]
        href_lower = href.lower()
        if not any(ext in href_lower for ext in extensions):
            continue
        text = a.get_text(" ", strip=True)
        if not matches(text.lower()):
            continue
        full_url = urljoin(base_url, href)
        dates = DATE_RE.findall(text)
        if dates:
            d, mo, y = int(dates[-1][0]), int(dates[-1][1]), int(dates[-1][2])
            candidates.append((datetime(y, mo, d), full_url))
        elif fallback is None:
            fallback = full_url

    if candidates:
        return max(candidates, key=lambda x: x[0])[1]
    return fallback
