#!/usr/bin/env python3
"""
Static site builder for OceanMan — GitHub Pages PoC.

Usage:
    py build.py             # build from existing SQLite data
    py build.py --refresh   # run parsers first, then build

Output: dist/index.html (today) + dist/<weekday>.html (other 6 days)
        dist/static/ (CSS copy with corrected paths)
"""
import shutil
import sys
from datetime import datetime
from pathlib import Path

import store
from app import app, POOL_MODULES, _refresh_pool

WEEKDAYS = [
    "monday", "tuesday", "wednesday", "thursday",
    "friday", "saturday", "sunday",
]


def _today() -> str:
    return datetime.now().strftime("%A").lower()


def build(run_parsers: bool = False) -> None:
    store.init_db()

    if run_parsers:
        print("Running parsers…")
        for key, module in POOL_MODULES.items():
            _refresh_pool(key, module)

    today = _today()
    dist = Path("dist")
    if dist.exists():
        shutil.rmtree(dist)
    dist.mkdir()

    # Copy static assets so relative paths work on GitHub Pages
    shutil.copytree("static", dist / "static")

    print("Rendering pages…")
    with app.test_client() as client:
        for day in WEEKDAYS:
            resp = client.get(f"/?day={day}")
            html = resp.data.decode("utf-8")

            # Rewrite day-tab hrefs from /?day=X to relative .html files
            for d in WEEKDAYS:
                target = "index.html" if d == today else f"{d}.html"
                html = html.replace(f'href="/?day={d}"', f'href="{target}"')

            # Rewrite absolute /static/ paths to relative (required for GH Pages subdir)
            html = html.replace('href="/static/', 'href="static/')
            html = html.replace('src="/static/', 'src="static/')

            filename = "index.html" if day == today else f"{day}.html"
            (dist / filename).write_text(html, encoding="utf-8")
            print(f"  {filename} ({day})")

    print(f"\nDone — {len(WEEKDAYS)} pages written to dist/")


if __name__ == "__main__":
    build(run_parsers="--refresh" in sys.argv)
