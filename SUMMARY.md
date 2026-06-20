# OceanMan — Session Summary (2026-06-19 / 2026-06-20)

## What was built

### 1. `/api/health` endpoint + unavailable-state UI — `e9d4d8c`

- `GET /api/health` returns JSON status for all 4 pools: `ok`/`degraded`, slot count, last refresh time, last error
- `store.get_last_fetch_entry()` added to expose most recent `fetch_log` row per pool
- "Brak danych." replaced with styled warning icon + "Harmonogram tymczasowo niedostępny"

---

### 2. Architecture review — `8eda1f9`

Full analysis in `ARCHITECTURE.md`. Key findings:

**Current weaknesses:**
- APScheduler lives inside Flask — dies together, no retry, no visibility
- SQLite is hardcoded to a local path — incompatible with any cloud deployment
- `/refresh` route is open — no token protection

**Three deployment options evaluated:**

| Option | Cost | Effort | Notes |
|---|---|---|---|
| Railway | ~$10/mo | Low | Doesn't fix scheduler coupling |
| Vercel + Neon + GHA | $0 | ~16h | 3 services, Neon cold starts |
| Render + PostgreSQL | $0 → $14/mo | Medium | 90-day free DB expiry trap |

**Two better alternatives proposed:**

| Option | Cost | Effort | Key advantage |
|---|---|---|---|
| Static → GitHub Pages | $0 | ~8h | No server, no DB, no cold starts |
| Fly.io + SQLite | $0* | ~2h | Near-zero code changes |

*Fly.io free tier may change.

---

### 3. GitHub Pages PoC — HTML approach — `4e32870`

**`build.py`** — static site generator using Flask's test client:
- Renders all 7 days via `client.get('/?day=X')`
- Rewrites day-tab hrefs from `/?day=X` to `monday.html` etc.
- Rewrites `/static/` paths to relative `static/` for GitHub Pages subdirectory
- Outputs 7 HTML files + static assets to `dist/`

**`.github/workflows/deploy.yml`** — GitHub Pages deployment:
- Cron: `0 6 * * *` (06:00 UTC daily) + `workflow_dispatch`
- Runs `python build.py --refresh` → uploads `dist/` → deploys via `actions/deploy-pages`

**To activate:** Settings → Pages → Source → GitHub Actions

---

### 4. Static site JS fixes — `e5f0690`

Three features were broken in the static build (baked at 06:00, wrong by the time users view):

| Feature | Problem | Fix |
|---|---|---|
| TERAZ badge | `is_current` set at build time | JS recomputes from `data-start`/`data-end` every 60s |
| Teraz dostępne card | Not rendered if build ran outside pool hours | Always rendered (`hidden` attr), JS shows/populates it |
| Past slot dimming | `is_past` frozen at build time | JS applies `slot-row--past` dynamically as time advances |

**Template changes:**
- `<main data-day="{{ selected_day }}">` — lets JS know which day the page shows
- `data-start`, `data-end`, `data-free`, `data-total`, `data-css` on every slot row
- `data-pool-key`, `data-pool-name` on every pool card
- Summary card always rendered with `id="summary-card"` + `hidden` if no current pools
- Hero badge always rendered with `id="hero-{key}"` + `hidden` if no current slot
- JS block replaced with a 80-line time-aware updater that runs on load + every 60s

Works for **both** Flask SSR and static builds — Flask renders correct initial state, JS re-confirms it.

---

### 5. JSON data generator PoC — `b464221`

A second, parallel static architecture using JSON + client-side rendering instead of pre-baked HTML.

**`generate.py`** — standalone JSON generator:
- Runs all 4 parsers (or reads from existing SQLite)
- Writes `docs/data/availability.json` — 1335 slots across 4 pools, all 7 days
- Writes `docs/data/metadata.json` — fetch status, slot counts, last checked per pool

**`docs/index.html`** — self-contained static frontend (~19KB):
- Fetches `data/availability.json` on load
- Full day navigation (buttons, today dot)
- Pool cards with slot rows, hour dividers, Maps button
- TERAZ badge + current slot scroll (computed client-side from `new Date()`)
- Teraz dostępne summary card (computed client-side)
- Past slot dimming
- Live clock
- No Flask, no SQLite, no build step, no dependencies

**`.github/workflows/generate.yml`** — daily JSON generation:
- Cron: `0 6 * * *` + `workflow_dispatch`
- Runs parsers → generates JSON → commits `docs/data/` back to repo with `[skip ci]`

**To activate:** Settings → Pages → Source → Deploy from branch → `master` / `/docs`

---

### 6. Skeptical analysis of GitHub Pages

**Risks that are real:**
- GHA cron can be delayed 5–60 min or skipped under heavy load
- Parser failures are silent — old JSON stays, no user warning (mitigate: check `metadata.json` `last_fetched` in the UI)
- `availability.json` is 239KB uncompressed / ~60KB gzipped — grows with more pools
- Data is max 24h stale (vs 6h with APScheduler) — acceptable for weekly pool schedules
- Git history fills with daily data commits (~87MB/year) — mitigate with shallow clones or orphan branch
- `fetch()` fails on `file://` — must use local HTTP server for development

**Risks that are not real for this project:**
- Traffic scaling — GitHub Pages CDN handles it
- CORS — same-origin JSON fetch
- Server features lost — none currently exist that users depend on

---

## Current file inventory

| File | Purpose |
|---|---|
| `app.py` | Flask app, routes, APScheduler — unchanged |
| `store.py` | SQLite layer + `get_last_fetch_entry()` |
| `pools/*.py` | 4 parsers — unchanged |
| `build.py` | Static HTML generator (HTML approach) |
| `generate.py` | JSON data generator (JSON approach) |
| `docs/index.html` | Self-contained static frontend |
| `docs/data/availability.json` | Generated: 1335 slots, 4 pools |
| `docs/data/metadata.json` | Generated: fetch status per pool |
| `templates/index.html` | Jinja2 template — enhanced with data-* attrs + time-aware JS |
| `ARCHITECTURE.md` | Full architecture review + migration plan |
| `.github/workflows/tests.yml` | pytest on push/PR |
| `.github/workflows/deploy.yml` | GitHub Pages HTML deployment (HTML approach) |
| `.github/workflows/generate.yml` | Daily JSON generation + commit (JSON approach) |

---

## Commits this session

| Hash | Description |
|---|---|
| `e9d4d8c` | Add /api/health endpoint + unavailable-state UI |
| `8eda1f9` | Add architecture review and migration plan |
| `4e32870` | PoC: static site builder + GitHub Pages deploy workflow |
| `e5f0690` | Fix static site: TERAZ badge, summary card, past slots via JS |
| `b464221` | PoC: JSON data generator + static frontend + GHA generate workflow |

---

## Next steps (not yet done)

- Enable GitHub Pages in repo Settings to go live
- Add `last_fetched` staleness warning to `docs/index.html` (show "dane sprzed X dni" if `metadata.json` age > 48h)
- Decide between HTML approach (`build.py` / `deploy.yml`) and JSON approach (`generate.py` / `generate.yml`) — they are mutually exclusive as GitHub Pages sources
- Add `/refresh` token protection before any public deployment
- Consider minifying `availability.json` (removes ~180KB, reduces to ~60KB uncompressed)
