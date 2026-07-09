import hashlib

import httpx

HEADERS = {"User-Agent": "OceanMan/1.0 (personal pool schedule tracker)"}


def fetch_pdf(url: str) -> tuple[bytes, str]:
    resp = httpx.get(url, timeout=30, follow_redirects=True, headers=HEADERS)
    resp.raise_for_status()
    content = resp.content
    md5 = hashlib.md5(content).hexdigest()
    return content, md5
