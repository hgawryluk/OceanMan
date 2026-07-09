import sqlite3
from pathlib import Path
from datetime import datetime

from models import PoolSchedule

DB_PATH = Path("data/pools.db")


def init_db():
    DB_PATH.parent.mkdir(exist_ok=True)
    with sqlite3.connect(DB_PATH) as con:
        con.executescript("""
            CREATE TABLE IF NOT EXISTS schedules (
                id          INTEGER PRIMARY KEY,
                pool        TEXT NOT NULL,
                valid_from  TEXT,
                fetched_at  TEXT NOT NULL,
                source_url  TEXT NOT NULL,
                source_hash TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS slots (
                schedule_id INTEGER REFERENCES schedules(id),
                weekday     TEXT NOT NULL,
                slot_start  TEXT NOT NULL,
                slot_end    TEXT NOT NULL,
                free_lanes  INTEGER NOT NULL,
                total_lanes INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS fetch_log (
                id         INTEGER PRIMARY KEY,
                pool       TEXT NOT NULL,
                checked_at TEXT NOT NULL,
                changed    INTEGER NOT NULL,
                note       TEXT
            );
        """)


def upsert_schedule(schedule: PoolSchedule):
    with sqlite3.connect(DB_PATH) as con:
        existing = con.execute(
            "SELECT id FROM schedules WHERE source_hash = ?",
            (schedule.source_hash,),
        ).fetchone()
        if existing:
            return

        old = con.execute(
            "SELECT id FROM schedules WHERE pool = ?",
            (schedule.pool,),
        ).fetchone()
        if old:
            con.execute("DELETE FROM slots WHERE schedule_id = ?", (old[0],))
            con.execute("DELETE FROM schedules WHERE id = ?", (old[0],))

        cur = con.execute(
            "INSERT INTO schedules (pool, valid_from, fetched_at, source_url, source_hash) VALUES (?,?,?,?,?)",
            (
                schedule.pool,
                str(schedule.valid_from) if schedule.valid_from else None,
                schedule.fetched_at.isoformat(),
                schedule.source_url,
                schedule.source_hash,
            ),
        )
        sid = cur.lastrowid
        con.executemany(
            "INSERT INTO slots VALUES (?,?,?,?,?,?)",
            [
                (sid, s.weekday, s.slot_start, s.slot_end, s.free_lanes, s.total_lanes)
                for s in schedule.slots
            ],
        )


def get_schedule(pool: str) -> dict | None:
    with sqlite3.connect(DB_PATH) as con:
        con.row_factory = sqlite3.Row
        sched = con.execute(
            "SELECT * FROM schedules WHERE pool = ? ORDER BY fetched_at DESC LIMIT 1",
            (pool,),
        ).fetchone()
        if not sched:
            return None
        slots = con.execute(
            "SELECT * FROM slots WHERE schedule_id = ? ORDER BY weekday, slot_start",
            (sched["id"],),
        ).fetchall()
        return {"schedule": dict(sched), "slots": [dict(s) for s in slots]}


def get_last_hash(pool: str) -> str | None:
    with sqlite3.connect(DB_PATH) as con:
        row = con.execute(
            "SELECT source_hash FROM schedules WHERE pool = ? ORDER BY fetched_at DESC LIMIT 1",
            (pool,),
        ).fetchone()
        return row[0] if row else None


def log_fetch(pool: str, changed: bool, note: str = ""):
    with sqlite3.connect(DB_PATH) as con:
        con.execute(
            "INSERT INTO fetch_log (pool, checked_at, changed, note) VALUES (?,?,?,?)",
            (pool, datetime.now().isoformat(), int(changed), note),
        )


def get_last_fetch_entry(pool: str) -> dict | None:
    """Return the most recent fetch_log row for the pool."""
    with sqlite3.connect(DB_PATH) as con:
        con.row_factory = sqlite3.Row
        row = con.execute(
            "SELECT checked_at, changed, note FROM fetch_log WHERE pool = ? ORDER BY checked_at DESC LIMIT 1",
            (pool,),
        ).fetchone()
        return dict(row) if row else None
