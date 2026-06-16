import logging
from datetime import datetime, time as time_

from apscheduler.schedulers.background import BackgroundScheduler
from flask import Flask, redirect, render_template, request, url_for

import downloader
import store
from pools import delfin as delfin_pool
from pools import foka as foka_pool
from pools import inflancka as inflancka_pool
from pools import potocka as potocka_pool

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

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

def refresh_delfin():
    log.info("Delfin: checking for updates…")
    try:
        url = delfin_pool.discover()
        if not url:
            log.warning("Delfin: no PDF URL found on page")
            store.log_fetch("delfin", False, "no url found")
            return
        pdf_bytes, md5 = downloader.fetch_pdf(url)
        if md5 == store.get_last_hash("delfin"):
            log.info("Delfin: no change")
            store.log_fetch("delfin", False, "no change")
            return
        schedule = delfin_pool.parse(pdf_bytes, url, md5)
        store.upsert_schedule(schedule)
        store.log_fetch("delfin", True, f"{len(schedule.slots)} slots")
        log.info(f"Delfin: updated — {len(schedule.slots)} slots stored")
    except Exception as exc:
        log.error(f"Delfin refresh failed: {exc}")
        store.log_fetch("delfin", False, str(exc))


def refresh_foka():
    log.info("Foka: checking for updates…")
    try:
        url = foka_pool.discover()
        if not url:
            log.warning("Foka: no PDF URL found on page")
            store.log_fetch("foka", False, "no url found")
            return
        pdf_bytes, md5 = downloader.fetch_pdf(url)
        if md5 == store.get_last_hash("foka"):
            log.info("Foka: no change")
            store.log_fetch("foka", False, "no change")
            return
        schedule = foka_pool.parse(pdf_bytes, url, md5)
        store.upsert_schedule(schedule)
        store.log_fetch("foka", True, f"{len(schedule.slots)} slots")
        log.info(f"Foka: updated — {len(schedule.slots)} slots stored")
    except Exception as exc:
        log.error(f"Foka refresh failed: {exc}")
        store.log_fetch("foka", False, str(exc))


def refresh_inflancka():
    log.info("Inflancka: checking for updates…")
    try:
        url = inflancka_pool.discover()
        if not url:
            log.warning("Inflancka: no PDF URL found on page")
            store.log_fetch("inflancka", False, "no url found")
            return
        pdf_bytes, md5 = downloader.fetch_pdf(url)
        if md5 == store.get_last_hash("inflancka"):
            log.info("Inflancka: no change")
            store.log_fetch("inflancka", False, "no change")
            return
        schedule = inflancka_pool.parse(pdf_bytes, url, md5)
        store.upsert_schedule(schedule)
        store.log_fetch("inflancka", True, f"{len(schedule.slots)} slots")
        log.info(f"Inflancka: updated — {len(schedule.slots)} slots stored")
    except Exception as exc:
        log.error(f"Inflancka refresh failed: {exc}")
        store.log_fetch("inflancka", False, str(exc))


def refresh_potocka():
    log.info("Potocka: checking for updates…")
    try:
        url = potocka_pool.discover()
        if not url:
            log.warning("Potocka: no PDF URL found on page")
            store.log_fetch("potocka", False, "no url found")
            return
        pdf_bytes, md5 = downloader.fetch_pdf(url)
        if md5 == store.get_last_hash("potocka"):
            log.info("Potocka: no change")
            store.log_fetch("potocka", False, "no change")
            return
        schedule = potocka_pool.parse(pdf_bytes, url, md5)
        store.upsert_schedule(schedule)
        store.log_fetch("potocka", True, f"{len(schedule.slots)} slots")
        log.info(f"Potocka: updated — {len(schedule.slots)} slots stored")
    except Exception as exc:
        log.error(f"Potocka refresh failed: {exc}")
        store.log_fetch("potocka", False, str(exc))


def refresh_all():
    refresh_delfin()
    refresh_foka()
    refresh_inflancka()
    refresh_potocka()


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

    delfin_data  = store.get_schedule("delfin")
    delfin_slots = _prepare_slots(delfin_data["slots"], selected_day, now, is_today) if delfin_data else []

    foka_data  = store.get_schedule("foka")
    foka_slots = _prepare_slots(foka_data["slots"], selected_day, now, is_today) if foka_data else []

    inflancka_data  = store.get_schedule("inflancka")
    inflancka_slots = _prepare_slots(inflancka_data["slots"], selected_day, now, is_today) if inflancka_data else []

    potocka_data  = store.get_schedule("potocka")
    potocka_slots = _prepare_slots(potocka_data["slots"], selected_day, now, is_today) if potocka_data else []

    pools = [
        {"key": "delfin",    **POOL_INFO["delfin"],    "data": delfin_data,    "slots": delfin_slots,    "current_slot": next((s for s in delfin_slots    if s["is_current"]), None)},
        {"key": "foka",      **POOL_INFO["foka"],      "data": foka_data,      "slots": foka_slots,      "current_slot": next((s for s in foka_slots      if s["is_current"]), None)},
        {"key": "inflancka", **POOL_INFO["inflancka"], "data": inflancka_data, "slots": inflancka_slots, "current_slot": next((s for s in inflancka_slots if s["is_current"]), None)},
        {"key": "potocka",   **POOL_INFO["potocka"],   "data": potocka_data,   "slots": potocka_slots,   "current_slot": next((s for s in potocka_slots   if s["is_current"]), None)},
    ]

    return render_template(
        "index.html",
        now=now,
        today=today,
        selected_day=selected_day,
        days=DAYS,
        pools=pools,
    )


@app.route("/refresh")
def manual_refresh():
    refresh_all()
    return redirect(url_for("index"))


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
