import logging
from datetime import datetime, time as time_

from apscheduler.schedulers.background import BackgroundScheduler
from flask import Flask, redirect, render_template, request, url_for

import downloader
import store
from pools import delfin as delfin_pool

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

app = Flask(__name__)

DAYS = [
    ("monday",    "Pon"),
    ("tuesday",   "Wt"),
    ("wednesday", "Śr"),
    ("thursday",  "Czw"),
    ("friday",    "Pt"),
    ("saturday",  "Sob"),
    ("sunday",    "Niedz"),
]


def _lane_class(free: int, total: int) -> str:
    if free == 0:
        return "zero"
    ratio = free / total
    if ratio <= 0.33:
        return "bad"
    if ratio <= 0.66:
        return "warn"
    return "good"


def _prepare_slots(raw_slots: list[dict], selected_day: str, now: datetime) -> list[dict]:
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
            "is_current": start <= now_t < end,
            "is_past":    end <= now_t,
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


def refresh_all():
    refresh_delfin()
    # foka and inflancka added in later phases


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

    delfin_data = store.get_schedule("delfin")
    delfin_slots = (
        _prepare_slots(delfin_data["slots"], selected_day, now)
        if delfin_data
        else []
    )

    return render_template(
        "index.html",
        now=now,
        today=today,
        selected_day=selected_day,
        days=DAYS,
        delfin=delfin_data,
        delfin_slots=delfin_slots,
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
