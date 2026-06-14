# Implementation Plan — Warsaw Pool Schedule Tracker

Phases are ordered by value delivered per unit of risk. Each phase is independently runnable and testable before the next begins.

---

## Phase 1 — Project Skeleton & Delfin Parser

**Goal:** End-to-end working pipeline for the easiest pool (Delfin). Validates the full stack before tackling harder parsers.

### Tasks

1. **Initialise project**
   - Create `requirements.txt` with pinned versions:  
     `httpx`, `beautifulsoup4`, `lxml`, `pdfplumber`, `apscheduler`, `pytest`
   - Create `src/models.py` — `SlotReading` and `PoolSchedule` dataclasses
   - Create `src/store.py` — SQLite initialisation, `upsert_schedule()`, `get_latest()`
   - Create `src/downloader.py` — `fetch_pdf(url) → (bytes, md5_hash)`

2. **Delfin discoverer** (`src/discovery/delfin.py`)
   - Fetch `sport.um.warszawa.pl/waw/osir-wola/-/plywalnia-kryta-delfin-kasprzaka-1-3`
   - Find `<a>` whose text matches `wolnych torów` (case-insensitive)
   - Extract URL + `?t=` timestamp
   - Return `DiscoveryResult(url, timestamp, changed)`

3. **Delfin parser** (`src/parsers/delfin.py`)
   - Open PDF with `pdfplumber`
   - `page.extract_table()` → 2D list
   - First row = column headers (time | Pon. | Wt. | Śr. | Czw. | Pt. | Sob. | Niedz.)
   - Each subsequent row → `SlotReading` × 7
   - Map Polish abbreviations to ISO weekday names
   - Handle `None` / empty cells gracefully

4. **Wire Delfin end-to-end** (`src/main.py`)
   - Discover → download if changed → parse → store
   - Print summary to stdout

5. **Tests**
   - Save Delfin sample PDF to `tests/fixtures/delfin_sample.pdf`
   - `tests/test_delfin_parser.py`: assert 30 time slots × 7 days = 210 readings, values in 0–6

**Exit criteria:** Running `python src/main.py` fetches the Delfin PDF, parses all 210 slot-day values, and writes them to SQLite.

---

## Phase 2 — Foka Parser

**Goal:** Parse the colour-coded visual grid. This is the hardest parser; isolating it in its own phase limits risk.

### Tasks

1. **Foka discoverer** (`src/discovery/foka.py`)
   - Fetch Foka official page
   - Find `<a>` whose text matches `rezerwac` or `wolnych` (Polish, case-insensitive)
   - Extract URL + timestamp

2. **Foka parser — vector graphics approach** (`src/parsers/foka.py`)
   - Open PDF with `pdfplumber`
   - Extract `page.rects` (list of rectangle objects with `x0, y0, x1, y1, fill`)
   - Detect grid geometry from header row text positions (lane numbers 1–6, day labels)
   - For each (day × time_slot) cell, check if any non-white filled rect overlaps the cell centroid → reserved
   - Count white cells per row per day → `free_lanes`

3. **Foka parser — image fallback**
   - Add `pdf2image` + `Pillow` to `requirements.txt`
   - If vector extraction produces zero coloured rects (detect via count < threshold) → fall back
   - `convert_from_bytes(pdf_bytes, dpi=150)` → single PIL image
   - Sample pixel at each cell centroid
   - White threshold: R>240 AND G>240 AND B>240 → free; else reserved

4. **Grid geometry detection** (shared utility)
   - Find day-label positions (sobota/niedziela/etc.) from text layer
   - Find time-slot label positions from leftmost column
   - Build `GridGeometry` — defines cell bounding boxes without hardcoded coordinates

5. **Tests**
   - `tests/fixtures/foka_sample.pdf`
   - `tests/test_foka_parser.py`: assert 32 time slots × 7 days = 224 readings, values in 0–6
   - Spot-check: Saturday 06:00–06:30 = 6 free (visually confirmed empty on sample)

**Exit criteria:** Foka parser returns correct free-lane counts matching a manual read of the sample PDF.

---

## Phase 3 — Inflancka Parser

**Goal:** Parse the multi-page named-reservation grid.

### Tasks

1. **Inflancka discoverer** (`src/discovery/inflancka.py`)
   - Fetch Inflancka schedule page
   - Find all `<a>` linking to `.pdf` with `"harmonogram"` in href
   - Filter out gym/fitness/brodzik links (exclude: `"siłowni"`, `"sala"`, `"brodzik"` in text or href)
   - For each remaining link, extract validity dates from visible label (regex `\d{2}\.\d{2}\.\d{4}`)
   - Pick the PDF with the latest `valid_to` date
   - Extract URL + `?t=` timestamp

2. **Inflancka parser** (`src/parsers/inflancka.py`)
   - Iterate over all 7 pages; map page index → weekday (0=Mon, 1=Tue, … 6=Sun)
   - For each page:
     - Extract words with bounding boxes via `pdfplumber`
     - Identify lane column x-boundaries from header row (lane numbers 9,8,7,…0)
     - Identify time row y-boundaries from "Od"/"Do" column
     - For each 15-min slot × 10 lanes: check if any word falls in cell bbox
     - Classify: empty or "TOR DLA KLIENTÓW INDYWIDUALNYCH" → free; any other text → reserved
   - Produce `SlotReading` per (weekday, slot, lane); `total_lanes = 10`

3. **Valid date extraction**
   - Parse "Harmonogram rezerwacji torów od DD.MM.YYYYr do DD.MM.YYYYr" from page header
   - Store as `valid_from` / `valid_to` on `PoolSchedule`
   - Resolve weekday → concrete date using `valid_from` as the Monday anchor

4. **Tests**
   - `tests/fixtures/inflancka_sample.pdf`
   - `tests/test_inflancka_parser.py`: 61 time slots × 10 lanes × 7 days = 4,270 readings
   - Spot-check: Sunday (Niedziela) shows many free lanes

**Exit criteria:** Inflancka parser returns structured free-lane counts for all 7 days with concrete dates.

---

## Phase 4 — Scheduler, Change Detection & Full Integration

**Goal:** The system runs unattended, checks for updates, and only re-parses when content changes.

### Tasks

1. **Change detection**
   - `src/store.py`: `get_last_hash(pool)` and `get_last_timestamp(pool)`
   - Discoverer returns timestamp; downloader computes hash
   - Two-level gate: skip download if `?t=` matches → skip parse if MD5 matches

2. **Full scheduler loop** (`src/main.py`)
   - `APScheduler` block scheduler, interval from `config.toml`
   - Run Foka + Delfin + Inflancka discoverers in sequence (or concurrently with `asyncio`)
   - Log each fetch attempt to `fetch_log` table
   - Catch all exceptions per-pool; one failing pool does not abort the others

3. **Config file** (`config.toml`)
   - `interval_hours`, per-pool `enabled` flags, `db_path`, `cache.dir`, `cache.keep_days`

4. **Cache cleanup**
   - On startup, delete PDFs in `cache/` older than `keep_days`

5. **CLI entry point**
   - `python -m src --once` — run one cycle and exit (useful for cron/manual invocation)
   - `python -m src --serve` — run scheduler loop indefinitely
   - `python -m src --query foka monday 08:00` — print free lanes for a given pool/day/time

6. **Integration test**
   - `tests/test_integration.py` using fixture PDFs — full pipeline from bytes to SQLite rows

**Exit criteria:** `python -m src --once` processes all three pools from fixtures, writes to DB, and `--query` returns correct values.

---

## Phase 5 — Output / API (Optional Extension)

**Goal:** Expose data to external consumers. Implement only after Phase 4 is stable.

### Options (choose one at implementation time)

**A. JSON file export**  
Write `output/schedule.json` after each parse cycle. Simple, no server needed.

**B. Minimal HTTP API**  
Add `fastapi` + `uvicorn`. Endpoints:
- `GET /pools` — list pools
- `GET /pools/{pool}/schedule` — full week schedule
- `GET /pools/{pool}/now` — free lanes at current time
- `GET /pools/{pool}/best` — time slots with most free lanes today

**C. Telegram / push notification**  
Notify when a previously fully-booked slot becomes available.

---

## Dependency Summary

```
# requirements.txt
httpx==0.27.*
beautifulsoup4==4.12.*
lxml==5.*
pdfplumber==0.11.*
pdf2image==1.17.*          # Phase 2 fallback only
Pillow==10.*               # Phase 2 fallback only
APScheduler==3.10.*
pytest==8.*
```

Python version: **3.11+** (uses stdlib `tomllib`, `zoneinfo`)

---

## Implementation Order Summary

| Phase | Delivers | Complexity |
|---|---|---|
| 1 | Delfin working end-to-end | Low |
| 2 | Foka working end-to-end | High |
| 3 | Inflancka working end-to-end | Medium |
| 4 | Scheduled auto-update, change detection | Low-Medium |
| 5 | Output/API | Optional |

Each phase produces a working, testable artefact. Do not begin Phase N+1 without verifying Phase N passes its exit criteria.
