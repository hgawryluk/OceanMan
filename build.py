#!/usr/bin/env python3
"""
Static site builder for OceanMan — GitHub Pages PoC.

Usage:
    py build.py             # build from existing SQLite data
    py build.py --refresh   # run parsers first, then build

Output: dist/index.html (today) + dist/<weekday>.html (other 6 days)
        dist/static/ (CSS + favicon copy with corrected paths)
        dist/manifest.webmanifest, robots.txt, sitemap.xml, 404.html
"""
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

import store
from app import app, POOL_MODULES, VERSION, SITE_URL, FORMSPREE_ID, _refresh_pool
from models import PoolSchedule, SlotReading

WEEKDAYS = [
    "monday", "tuesday", "wednesday", "thursday",
    "friday", "saturday", "sunday",
]


def _today() -> str:
    return datetime.now().strftime("%A").lower()


def _load_from_json() -> None:
    """Populate SQLite from docs/data/availability.json (used in CI where pool sites are blocked)."""
    json_path = Path("docs/data/availability.json")
    if not json_path.exists():
        print("WARNING: docs/data/availability.json not found — no data to load.")
        return
    data = json.loads(json_path.read_text(encoding="utf-8"))
    for key, pool_data in data.get("schedules", {}).items():
        slots = [
            SlotReading(
                pool=key,
                weekday=s["weekday"],
                slot_start=s["slot_start"],
                slot_end=s["slot_end"],
                free_lanes=s["free_lanes"],
                total_lanes=s["total_lanes"],
            )
            for s in pool_data["slots"]
        ]
        schedule = PoolSchedule(
            pool=key,
            valid_from=None,
            fetched_at=datetime.fromisoformat(pool_data["fetched_at"]),
            source_url=pool_data["source_url"],
            source_hash=f"json-{pool_data['fetched_at']}",
            slots=slots,
        )
        store.upsert_schedule(schedule)
        print(f"  Loaded {key}: {len(slots)} slots from JSON")


def build(run_parsers: bool = False, from_json: bool = False) -> None:
    store.init_db()

    if from_json:
        print("Loading data from docs/data/availability.json…")
        _load_from_json()
    elif run_parsers:
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

    # Copy root-level public files (robots.txt, sitemap.xml, manifest.webmanifest)
    public = Path("public")
    if public.exists():
        for f in public.iterdir():
            shutil.copy(f, dist / f.name)

    def _rewrite(html: str, today_day: str) -> str:
        for d in WEEKDAYS:
            target = "index.html" if d == today_day else f"{d}.html"
            html = html.replace(f'href="/?day={d}"', f'href="{target}"')
        html = html.replace('href="/static/', 'href="static/')
        html = html.replace('src="/static/', 'src="static/')
        html = html.replace('href="/manifest.webmanifest"', 'href="manifest.webmanifest"')
        return html

    print("Rendering pages…")
    with app.test_client() as client:
        for day in WEEKDAYS:
            resp = client.get(f"/?day={day}")
            html = _rewrite(resp.data.decode("utf-8"), today)
            filename = "index.html" if day == today else f"{day}.html"
            (dist / filename).write_text(html, encoding="utf-8")
            print(f"  {filename} ({day})")

    # Render about page
    resp = client.get("/about")
    html_about = _rewrite(resp.data.decode("utf-8"), today)
    html_about = html_about.replace('href="/about"', 'href="about.html"')
    html_about = html_about.replace('href="/suggest"', 'href="suggest.html"')
    (dist / "about.html").write_text(html_about, encoding="utf-8")
    print("  about.html")

    # Render suggest page
    resp = client.get("/suggest")
    html_suggest = _rewrite(resp.data.decode("utf-8"), today)
    html_suggest = html_suggest.replace('href="/about"', 'href="about.html"')
    html_suggest = html_suggest.replace('href="/suggest"', 'href="suggest.html"')
    (dist / "suggest.html").write_text(html_suggest, encoding="utf-8")
    print("  suggest.html")

    # Rewrite about link in all day pages
    day_files = list(dist.glob("*.html"))
    for f in day_files:
        if f.name in ("about.html", "404.html"):
            continue
        txt = f.read_text(encoding="utf-8")
        if 'href="/about"' in txt:
            f.write_text(txt.replace('href="/about"', 'href="about.html"'), encoding="utf-8")

    # Render 404 page
    with app.test_request_context():
        from flask import render_template
        html_404 = render_template("404.html", version=VERSION, site_url=SITE_URL, home_url="./index.html")
        html_404 = html_404.replace('href="/static/', 'href="static/')
        html_404 = html_404.replace('src="/static/', 'src="static/')
        (dist / "404.html").write_text(html_404, encoding="utf-8")
        print("  404.html")

    print(f"\nDone — {len(WEEKDAYS) + 2} pages + root files written to dist/")


if __name__ == "__main__":
    build(
        run_parsers="--refresh" in sys.argv,
        from_json="--from-json" in sys.argv,
    )
