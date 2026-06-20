#!/usr/bin/env python3
"""
JSON data generator for OceanMan static site.

Usage:
    py generate.py             # generate from existing SQLite data
    py generate.py --refresh   # run parsers first, then generate

Output:
    docs/data/availability.json  — slot data for all 4 pools, all 7 days
    docs/data/metadata.json      — fetch status per pool
"""
import json
import sys
from datetime import datetime
from pathlib import Path

import store
from app import POOL_INFO, POOL_MODULES, _refresh_pool

OUTPUT_DIR = Path("docs/data")

SLOT_KEYS = ("weekday", "slot_start", "slot_end", "free_lanes", "total_lanes")


def generate(run_parsers: bool = False) -> None:
    store.init_db()

    if run_parsers:
        print("Running parsers…")
        for key, module in POOL_MODULES.items():
            _refresh_pool(key, module)

    generated_at = datetime.now().isoformat()

    # ── availability.json ──────────────────────────────────────────────────
    schedules: dict = {}
    for key in POOL_INFO:
        data = store.get_schedule(key)
        if not data:
            continue
        schedules[key] = {
            "fetched_at": data["schedule"]["fetched_at"],
            "source_url": data["schedule"]["source_url"],
            # Strip schedule_id (internal FK); keep only the 5 public keys
            "slots": [{k: s[k] for k in SLOT_KEYS} for s in data["slots"]],
        }

    availability = {
        "generated_at": generated_at,
        "schedules": schedules,
    }

    # ── metadata.json ──────────────────────────────────────────────────────
    meta_pools: dict = {}
    for key, info in POOL_INFO.items():
        data = store.get_schedule(key)
        last = store.get_last_fetch_entry(key)
        meta_pools[key] = {
            "name": info["name"],
            "status": "ok" if data else "no_data",
            "slot_count": len(data["slots"]) if data else 0,
            "last_fetched": data["schedule"]["fetched_at"] if data else None,
            "last_checked": last["checked_at"] if last else None,
            "last_error": last["note"] if last and not last["changed"] and last["note"] not in ("no change", "no url found", "") else None,
        }

    metadata = {
        "generated_at": generated_at,
        "pools": meta_pools,
    }

    # ── write files ────────────────────────────────────────────────────────
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    avail_path = OUTPUT_DIR / "availability.json"
    avail_path.write_text(
        json.dumps(availability, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    total_slots = sum(len(s["slots"]) for s in schedules.values())
    print(f"  Wrote {avail_path}  ({len(schedules)} pools, {total_slots} slots)")

    meta_path = OUTPUT_DIR / "metadata.json"
    meta_path.write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"  Wrote {meta_path}")

    print(f"\nDone. Generated at {generated_at}")


if __name__ == "__main__":
    generate(run_parsers="--refresh" in sys.argv)
