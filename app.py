import logging
from datetime import datetime, time as time_

from apscheduler.schedulers.background import BackgroundScheduler
from flask import Flask, jsonify, redirect, render_template, request, send_from_directory, url_for

import downloader
import store
from pools import delfin as delfin_pool
from pools import foka as foka_pool
from pools import inflancka as inflancka_pool
from pools import potocka as potocka_pool

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

VERSION       = "1.0.0"
SITE_URL      = "https://hgawryluk.github.io/OceanMan"
FORMSPREE_ID  = "mdarrbdz"

app = Flask(__name__)
scheduler: BackgroundScheduler | None = None

DAYS = [
    ("monday",    "Pon"),
    ("tuesday",   "Wt"),
    ("wednesday", "Śr"),
    ("thursday",  "Czw"),
    ("friday",    "Pt"),
    ("saturday",  "Sob"),
    ("sunday",    "Niedz"),
]

_DAY_LABELS = {key: label for key, label in DAYS}
PL_MONTHS   = ["sty", "lut", "mar", "kwi", "maj", "cze", "lip", "sie", "wrz", "paź", "lis", "gru"]

POOL_MODULES = {
    "delfin":    delfin_pool,
    "foka":      foka_pool,
    "inflancka": inflancka_pool,
    "potocka":   potocka_pool,
}

POOL_INFO = {
    "delfin": {
        "name": "Delfin",
        "address": "ul. Kasprzaka 1/3, Warszawa",
        "maps_url": "https://maps.google.com/?q=Pływalnia+Delfin+Kasprzaka+Warszawa",
    },
    "foka": {
        "name": "Foka",
        "address": "ul. Esperanto 5, Warszawa",
        "maps_url": "https://maps.google.com/?q=Pływalnia+Foka+Esperanto+Warszawa",
    },
    "inflancka": {
        "name": "Inflancka",
        "address": "ul. Inflancka 8, Warszawa",
        "maps_url": "https://maps.google.com/?q=Ośrodek+Inflancka+Warszawa",
    },
    "potocka": {
        "name": "Potocka",
        "address": "ul. Potocka 1, Warszawa",
        "maps_url": "https://maps.google.com/?q=Pływalnia+Potocka+Warszawa",
    },
}


def _lane_class(free: int, total: int) -> str:
    if free == 0:
        return "level-0"
    ratio = free / total
    if ratio <= 1 / 6:
        return "level-1"
    if ratio <= 2 / 6:
        return "level-2"
    if ratio <= 3 / 6:
        return "level-3"
    if ratio <= 4 / 6:
        return "level-4"
    if ratio <= 5 / 6:
        return "level-5"
    return "level-6"


def _prepare_slots(raw_slots: list[dict], selected_day: str, now: datetime, is_today: bool) -> list[dict]:
    now_t = now.time()
    day_slots = sorted(
        (s for s in raw_slots if s["weekday"] == selected_day),
        key=lambda s: s["slot_start"],
    )
    result = []
    for s in day_slots:
        h1, m1 = map(int, s["slot_start"].split(":"))
        h2, m2 = map(int, s["slot_end"].split(":"))
        start = time_(h1, m1)
        end   = time_(h2, m2)
        result.append({
            **s,
            "is_current": is_today and start <= now_t < end,
            "is_past":    is_today and end <= now_t,
            "css_class":  _lane_class(s["free_lanes"], s["total_lanes"]),
        })
    return result


# ---------------------------------------------------------------------------
# Refresh logic
# ---------------------------------------------------------------------------

def _refresh_pool(key: str, module) -> None:
    label = key.capitalize()
    log.info(f"{label}: checking for updates…")
    try:
        url = module.discover()
        if not url:
            log.warning(f"{label}: no PDF URL found on page")
            store.log_fetch(key, False, "no url found")
            return
        pdf_bytes, md5 = downloader.fetch_pdf(url)
        if md5 == store.get_last_hash(key):
            log.info(f"{label}: no change")
            store.log_fetch(key, False, "no change")
            return
        schedule = module.parse(pdf_bytes, url, md5)
        store.upsert_schedule(schedule)
        store.log_fetch(key, True, f"{len(schedule.slots)} slots")
        log.info(f"{label}: updated — {len(schedule.slots)} slots stored")
        if schedule.slots and all(s.free_lanes == 0 for s in schedule.slots):
            log.warning(f"{label}: all slots report 0 free lanes — parser may be misreading the file")
    except Exception as exc:
        log.error(f"{label} refresh failed: {exc}")
        store.log_fetch(key, False, str(exc))


def refresh_all() -> None:
    for key, module in POOL_MODULES.items():
        _refresh_pool(key, module)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    now = datetime.now()
    today = now.strftime("%A").lower()

    day_param = request.args.get("day", "").lower()
    valid_days = {d for d, _ in DAYS}
    selected_day = day_param if day_param in valid_days else today
    is_today = selected_day == today

    pools = []
    for key, info in POOL_INFO.items():
        data  = store.get_schedule(key)
        slots = _prepare_slots(data["slots"], selected_day, now, is_today) if data else []
        pools.append({
            "key": key,
            **info,
            "data":         data,
            "slots":        slots,
            "current_slot": next((s for s in slots if s["is_current"]), None),
        })

    now_date_pl = f"{_DAY_LABELS[today]}, {now.day} {PL_MONTHS[now.month - 1]}"

    fetch_times = [p["data"]["schedule"]["fetched_at"] for p in pools if p["data"]]
    last_updated = None
    if fetch_times:
        dt = datetime.fromisoformat(max(fetch_times))
        last_updated = f"{dt.day} {PL_MONTHS[dt.month - 1]} {dt.year}"

    return render_template(
        "index.html",
        now=now,
        now_date_pl=now_date_pl,
        today=today,
        selected_day=selected_day,
        days=DAYS,
        pools=pools,
        version=VERSION,
        site_url=SITE_URL,
        last_updated=last_updated,
    )


@app.route("/api/health")
def health():
    pools_status = {}
    any_missing = False
    for key in POOL_INFO:
        data = store.get_schedule(key)
        last = store.get_last_fetch_entry(key)
        has_data = data is not None
        if not has_data:
            any_missing = True
        last_error = None
        if last and not last["changed"] and last["note"] not in ("no change", "no url found", ""):
            last_error = last["note"]
        pools_status[key] = {
            "status": "ok" if has_data else "no_data",
            "slot_count": len(data["slots"]) if data else 0,
            "last_refresh": data["schedule"]["fetched_at"] if data else None,
            "last_checked": last["checked_at"] if last else None,
            "last_error": last_error,
        }
    return jsonify({
        "status": "degraded" if any_missing else "ok",
        "time": datetime.now().isoformat(),
        "pools": pools_status,
    })


@app.route("/refresh")
def manual_refresh():
    refresh_all()
    return redirect(url_for("index"))


@app.route("/suggest")
def suggest():
    return render_template("suggest.html", version=VERSION, site_url=SITE_URL, formspree_id=FORMSPREE_ID)


@app.route("/about")
def about():
    pools = [
        {**info, "key": key, "total_lanes": {"delfin": 6, "foka": 6, "inflancka": 10, "potocka": 8}[key]}
        for key, info in POOL_INFO.items()
    ]
    return render_template("about.html", pools=pools, version=VERSION, site_url=SITE_URL)


@app.route("/manifest.webmanifest")
def manifest():
    return send_from_directory("public", "manifest.webmanifest", mimetype="application/manifest+json")


@app.route("/robots.txt")
def robots():
    return send_from_directory("public", "robots.txt", mimetype="text/plain")


@app.route("/sitemap.xml")
def sitemap_xml():
    return send_from_directory("public", "sitemap.xml", mimetype="application/xml")


@app.errorhandler(404)
def not_found(e):
    return render_template("404.html", version=VERSION, site_url=SITE_URL, home_url="/"), 404


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    store.init_db()
    refresh_all()

    scheduler = BackgroundScheduler()
    scheduler.add_job(refresh_all, "interval", hours=6)
    scheduler.start()

    try:
        app.run(host="127.0.0.1", port=5000, debug=True, use_reloader=False)
    finally:
        scheduler.shutdown()
