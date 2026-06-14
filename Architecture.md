# Architecture — Warsaw Pool Schedule Tracker

## Overview

The system periodically discovers, downloads, and parses weekly lane reservation schedules from three Warsaw swimming pools, then exposes a unified free-lane count per time slot per day.

---

## Component Map

```
┌──────────────────────────────────────────────────────────────┐
│                        Scheduler                             │
│  (APScheduler, configurable interval — default 6h)           │
└────────────────────────┬─────────────────────────────────────┘
                         │ triggers
                         ▼
┌──────────────────────────────────────────────────────────────┐
│                   Discovery Layer                            │
│  FokaDiscoverer │ DelfinDiscoverer │ InflanckaDiscoverer     │
│                                                              │
│  Each: scrapes official pool page → finds PDF link           │
│        reads ?t= timestamp → compares to stored value        │
│        returns (url, timestamp, changed: bool)               │
└────────────────────────┬─────────────────────────────────────┘
                         │ if changed
                         ▼
┌──────────────────────────────────────────────────────────────┐
│                   Downloader                                 │
│  Downloads PDF bytes → computes MD5 hash                     │
│  Compares hash to stored value (second guard against re-parse│
│  on identical content behind a new timestamp)                │
│  Writes PDF to cache/                                        │
└────────────────────────┬─────────────────────────────────────┘
                         │ if new content
                         ▼
┌──────────────────────────────────────────────────────────────┐
│                   Parser Layer                               │
│  FokaParser    │ DelfinParser    │ InflanckaParser            │
│                                                              │
│  Each returns: List[SlotReading]                             │
└────────────────────────┬─────────────────────────────────────┘
                         │
                         ▼
┌──────────────────────────────────────────────────────────────┐
│                   Normalizer                                 │
│  Converts parser output → unified PoolSchedule model         │
│  Resolves weekday names → concrete dates                     │
└────────────────────────┬─────────────────────────────────────┘
                         │
                         ▼
┌──────────────────────────────────────────────────────────────┐
│                   Data Store (SQLite)                        │
│  Tables: schedules, slots, fetch_log                         │
│  Upsert on change; preserves history                         │
└──────────────────────────────────────────────────────────────┘
```

---

## Data Model

### Unified Output — `PoolSchedule`

```python
@dataclass
class SlotReading:
    pool: str           # "foka" | "delfin" | "inflancka"
    weekday: str        # "monday" … "sunday" (ISO, lowercase)
    slot_start: time    # e.g. time(8, 0)
    slot_end: time      # e.g. time(8, 30)
    free_lanes: int     # 0 … total_lanes
    total_lanes: int    # 6 for Foka/Delfin, 10 for Inflancka

@dataclass
class PoolSchedule:
    pool: str
    valid_from: date    # date the schedule takes effect
    valid_to: date | None
    fetched_at: datetime
    source_url: str
    source_hash: str    # MD5 of PDF bytes
    slots: list[SlotReading]
```

### SQLite Schema

```sql
CREATE TABLE schedules (
    id          INTEGER PRIMARY KEY,
    pool        TEXT NOT NULL,
    valid_from  TEXT NOT NULL,
    valid_to    TEXT,
    fetched_at  TEXT NOT NULL,
    source_url  TEXT NOT NULL,
    source_hash TEXT NOT NULL UNIQUE
);

CREATE TABLE slots (
    schedule_id INTEGER REFERENCES schedules(id),
    weekday     TEXT NOT NULL,
    slot_start  TEXT NOT NULL,
    slot_end    TEXT NOT NULL,
    free_lanes  INTEGER NOT NULL,
    total_lanes INTEGER NOT NULL
);

CREATE TABLE fetch_log (
    id          INTEGER PRIMARY KEY,
    pool        TEXT NOT NULL,
    checked_at  TEXT NOT NULL,
    changed     INTEGER NOT NULL,  -- 0/1
    url         TEXT,
    note        TEXT
);
```

---

## Parser Strategies

### Delfin (Easy)
The PDF already contains a plain numeric table: rows = time slots, columns = days, values = free lane count.  
**Strategy:** `pdfplumber.extract_table()` → parse integers directly.

### Foka (Hard — Visual Grid)
The PDF is a colour-coded Excel export. Coloured cells = reserved lane, white cells = free.  
No text exists inside grid cells.  
**Primary strategy:** Extract PDF vector graphics objects via `pdfplumber`. Each coloured reservation block is a filled rectangle. For each (row = time-slot, column = lane) position, check whether a non-white filled rectangle overlaps it. Count white positions = free lanes.  
**Fallback strategy:** Convert the PDF page to a raster image (`pdf2image`), sample pixel colour at each grid intersection, classify as reserved (coloured) or free (white/very-light).

### Inflancka (Medium — Named Grid)
The PDF has one page per day. Grid cells contain club/organisation names as text. Lanes are numbered 0–9.  
**Strategy:**  
1. Use `pdfplumber` to extract words with bounding-box coordinates.  
2. Identify header row (lane numbers 0–9) and time-slot column to build a coordinate grid.  
3. For each 15-min slot × lane: check if any word falls within the cell bbox.  
4. Cell content classification:
   - `"TOR DLA KLIENTÓW INDYWIDUALNYCH"` → individual/public (counts as free)
   - `"Tory dostępne"` or empty cell with light-blue background → free
   - Club name (any other text) → reserved

---

## Discovery Strategies

### Foka & Delfin (same CMS site — OSiR Wola)
- Fetch official pool page HTML
- Find `<a>` tags whose `href` or link text matches keywords:
  - Foka: `"Rezerwacje torów"` / `"wolnych torów"` / `"rezerwacja"`
  - Delfin: `"wolnych torów"` / `"grafik zajętości"` / `"duzy basen"`
- Extract URL and `?t=` timestamp parameter
- No JavaScript rendering needed — links are in static HTML

### Inflancka (dedicated schedule page)
- Fetch schedule page HTML
- Find all `<a>` tags linking to `.pdf` files with `"harmonogram"` in the URL
- Filter for pool (pływalnia) schedule: exclude "siłownia" (gym), "sala" (fitness), "brodzik" (paddling)
- Among remaining links, pick the one whose displayed validity date range is most recent
- Extract URL and `?t=` timestamp

---

## Directory Layout

```
warsaw-pools/
├── src/
│   ├── discovery/
│   │   ├── base.py          # DiscovererBase ABC
│   │   ├── foka.py
│   │   ├── delfin.py
│   │   └── inflancka.py
│   ├── parsers/
│   │   ├── base.py          # ParserBase ABC
│   │   ├── delfin.py        # table extraction
│   │   ├── foka.py          # vector graphics + image fallback
│   │   └── inflancka.py     # coordinate-mapped text extraction
│   ├── models.py            # SlotReading, PoolSchedule dataclasses
│   ├── store.py             # SQLite read/write
│   ├── downloader.py        # HTTP fetch + MD5 + cache
│   ├── normalizer.py        # weekday name → date resolution
│   └── main.py              # wires everything; APScheduler loop
├── cache/                   # downloaded PDFs (gitignored)
├── data/
│   └── pools.db             # SQLite database
├── tests/
│   ├── fixtures/            # sample PDFs for offline tests
│   ├── test_delfin_parser.py
│   ├── test_foka_parser.py
│   └── test_inflancka_parser.py
├── Architecture.md
├── TechnicalResearch.md
├── ImplementationPlan.md
└── requirements.txt
```

---

## Error Handling Policy

| Situation | Behaviour |
|---|---|
| Pool page fetch fails | Log to fetch_log, skip pool this cycle, retry next cycle |
| No PDF link found on page | Log warning, skip pool |
| PDF download fails | Log error, retain last parsed data |
| Parser raises exception | Log traceback, emit partial results if any, skip pool |
| Hash unchanged | Skip re-parse, update fetch_log only |
| Inflancka page has no current PDF | Pick the most recently posted PDF, log stale warning |

---

## Configuration

`config.toml` (runtime, not committed):

```toml
[scheduler]
interval_hours = 6

[pools.foka]
enabled = true

[pools.delfin]
enabled = true

[pools.inflancka]
enabled = true

[store]
db_path = "data/pools.db"

[cache]
dir = "cache/"
keep_days = 7
```
