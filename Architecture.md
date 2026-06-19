# OceanMan — Architecture Review & Migration Plan

> Generated: 2026-06-19

---

## Table of Contents

1. [Current Architecture Review](#1-current-architecture-review)
2. [Deployment Options](#2-deployment-options)
3. [Vercel Feasibility Study](#3-vercel-feasibility-study)
4. [Database Migration](#4-database-migration-sqlite--neon-postgresql)
5. [Scheduler Analysis](#5-scheduler-analysis)
6. [API Analysis](#6-api-analysis)
7. [Security Review](#7-security-review)
8. [Better Alternatives](#8-better-alternatives)
9. [Migration Roadmap](#9-migration-roadmap)
10. [Decision Recommendation](#10-decision-recommendation)

---

## 1. Current Architecture Review

### Strengths

1. **Clean module boundaries.** `app.py` (web+scheduler), `store.py` (data), `downloader.py` (HTTP), `models.py` (types), `pools/*.py` (parsers) — each has one job. Adding a 5th pool means adding one file and one entry in `POOL_MODULES`.

2. **Hash-based dedup.** The MD5 check in `_refresh_pool()` means the scheduler can run every 6h with no DB writes unless the file actually changed. Smart and cheap.

3. **Defensive parsers.** Color tolerance, overlap detection, date ranking, all-zero sanity checks, XLSX+PDF fallback for Delfin — production-grade heuristics for genuinely brittle external inputs.

4. **No ORM, no magic.** Raw `sqlite3` with `row_factory` is simple, testable, and exactly right for this workload. The queries are trivial to read.

5. **CI already exists.** GitHub Actions runs pytest with coverage on every push. This is the right foundation for cloud migration.

6. **`_refresh_pool()` refactor (Phase 9).** The 4-in-1 refactor means refresh logic is in one place — critical for extracting it to a standalone script later.

### Weaknesses

1. **APScheduler is in-process.** Lives inside the Flask process. If Flask crashes, the scheduler dies with it. No retry logic, no visibility into whether the last run succeeded, no way to scale Flask independently. On Vercel this is a hard blocker.

2. **SQLite is file-local.** `DB_PATH = Path("data/pools.db")` is hardcoded. Can't be accessed from multiple processes or machines. On Vercel's ephemeral filesystem, data doesn't survive between function invocations.

3. **`/refresh` is open.** Anyone who discovers the URL triggers 4 HTTP fetches to pool websites + a DB write. Low risk for a hobby project, but a free DoS vector against `sport.um.warszawa.pl`.

4. **No retry or back-off.** If `discover()` or `fetch_pdf()` throws, the pool silently shows stale data. No retry, no alerting.

5. **`downloader.py` creates `cache/` but writes nothing.** `CACHE_DIR.mkdir(exist_ok=True)` runs on every fetch but bytes are never persisted. Dead code — confusing.

6. **`datetime.now()` in parsers.** Each parser sets `fetched_at=datetime.now()` internally. Couples the parse step to wall-clock time in a way that's hard to test.

### Tightly Coupled Parts

| Coupling | Location | Problem |
|---|---|---|
| APScheduler ↔ Flask process | `app.py:212-223` | Can't separate them |
| SQLite path hardcoded | `store.py:7` | No env var override |
| `store.init_db()` in Flask startup | `app.py:213` | Schema management mixed into web server |
| `datetime.now()` in parsers | `pools/*.py` | Parse step owns its own timestamp |
| `CACHE_DIR` exists but does nothing | `downloader.py:6` | Dead dir creation on every fetch |

### What Would Be Difficult on Vercel

1. **APScheduler** — impossible. Vercel is serverless: functions are stateless, short-lived, killed after the request completes. No threads survive between invocations.

2. **SQLite** — impossible for persistent data. Vercel's filesystem is read-only outside `/tmp`, and `/tmp` is ephemeral (wiped between cold starts, not shared between instances).

3. **Heavy dependencies at parse time.** `pdfplumber`, `openpyxl`, `pillow` are CPU and memory intensive. Vercel free tier: 1024MB RAM, 10s timeout, 250MB uncompressed bundle. Running a parser inside a Vercel function is technically possible but risky.

4. **`timeout=30` on HTTP fetches.** `downloader.fetch_pdf()` allows 30s. Vercel free tier hard-caps serverless functions at 10s. A slow pool server would timeout.

5. **Runtime directory creation.** `data/` and `cache/` are created on startup. No writable persistent directory exists on Vercel.

### What Already Fits Serverless

- `index()` and `health()` routes — pure DB reads, stateless, fast
- All 4 parser modules — pure functions: `discover() → str`, `parse() → PoolSchedule`
- `models.py` — plain dataclasses, no side effects
- `downloader.py` — stateless HTTP fetch, works anywhere
- Hash dedup logic — naturally serverless-safe (idempotent)
- Jinja2 templates — work fine on Vercel

---

## 2. Deployment Options

### Option A: Railway

Setup: Flask + PostgreSQL + APScheduler or Railway Cron Job.

| Dimension | Assessment |
|---|---|
| **Cost** | ~$10/month (Hobby $5 + PostgreSQL $5). $5 credit/month exists but unreliable for always-on. Not free. |
| **Complexity** | Low — minimal code changes. Replace SQLite with psycopg2, point at Railway's PostgreSQL. |
| **Migration effort** | ~4h. `store.py` rewrite, deploy config, done. |
| **Scalability** | Adequate. Single container, vertical scaling. Railway auto-restarts on crash. |
| **Risks** | Not free. Railway has changed pricing twice in 2 years. APScheduler still in-process (same reliability problem). |

**Verdict:** Easiest migration but costs real money and doesn't fix the scheduler coupling problem.

---

### Option B: Vercel + Neon PostgreSQL + GitHub Actions

Setup: Vercel serverless (Flask via WSGI adapter) + Neon for data + GHA cron for daily parsing.

| Dimension | Assessment |
|---|---|
| **Cost** | **$0/month.** Vercel Hobby (free), Neon free tier (0.5GB — you'll use ~1MB), GHA public repo (unlimited minutes). |
| **Complexity** | High — significant architecture change. APScheduler removed, SQLite replaced, parsers moved to GHA. |
| **Migration effort** | ~12-16h across 4-5 sessions. |
| **Scalability** | Excellent. Vercel auto-scales. Neon handles concurrent reads fine. |
| **Risks** | Neon cold start latency (1-3s after idle), GHA cron jitter, psycopg binary on Amazon Linux needs testing. |

**Verdict:** Correct long-term architecture if cloud deployment is desired. The effort is real.

---

### Option C: Render + PostgreSQL

Setup: Render web service + Render PostgreSQL + Render Cron Jobs.

| Dimension | Assessment |
|---|---|
| **Cost** | Free for 90 days, then $14/month. Or free tier with 30s cold starts. |
| **Complexity** | Medium — similar to Railway. |
| **Migration effort** | ~6h. `store.py` + deploy config + cron job config. |
| **Scalability** | Adequate. |
| **Risks** | Free tier 15-min sleep = 30s cold start (terrible UX). PostgreSQL free tier hard-expires after 90 days (data loss risk). |

**Verdict:** Worse than both A and B. The 90-day PostgreSQL expiry is a trap.

---

## 3. Vercel Feasibility Study

### What needs to change

**Must change:**
- APScheduler removed from `app.py` — replaced by GHA cron
- `store.py` rewritten from `sqlite3` to `psycopg` with `DATABASE_URL` from env
- `store.init_db()` call removed from Flask startup
- `data/` + `cache/` directory creation removed

**Should change:**
- Parsers should not run on Vercel at all — they run in GitHub Actions. The Vercel deployment does not need pdfplumber, openpyxl, httpx, or BeautifulSoup. **Vercel bundle size drops dramatically as a result.**

**Stays unchanged:**
- `models.py`, `downloader.py`, all 4 `pools/*.py` — zero changes
- `templates/` + `static/` — zero changes
- `_prepare_slots()`, `_lane_class()` — zero changes
- `index()` and `health()` routes — minor: remove scheduler startup
- Existing test suite — zero changes

### Can Flask remain?

Yes. Vercel supports Python via WSGI. A `vercel.json` + thin `api/index.py` entry point wraps the Flask `app` object. Flask itself is unaware it's on Vercel.

### Should API routes be separated?

No. At this project size, separating `/api/*` from page routes adds CORS config, two deployment targets, a JS build step, and auth tokens — for zero benefit with one developer and one browser client.

### Can GitHub Actions replace the scheduler?

Yes, and it's the right call. A GHA workflow with `schedule: cron: '0 6 * * *'` runs the parsers, writes to Neon, and exits. The Flask app only reads.

**Advantages over APScheduler:**
- Failure is visible — GHA red X + email notification
- Logs are persistent and searchable
- No "is the scheduler still running?" uncertainty
- Retries are configurable per-step

**Disadvantages:**
- ±5-15min cron jitter under GitHub load (irrelevant for weekly pool schedules)
- Manual trigger requires `workflow_dispatch` (trivial to add)
- GHA runner cold start + pip install adds ~60s overhead

### Daily refresh flow on GHA

```
cron: "0 6 * * *"  (06:00 UTC)
    ↓
GHA runner spins up
    ↓
pip install -r requirements.txt (cached)
    ↓
scripts/refresh.py:
  for each pool:
    discover() → URL
    fetch_pdf(url) → bytes + md5
    if md5 == get_last_hash(pool): skip
    else: parse() → PoolSchedule → upsert_schedule()
    log_fetch()
    ↓
GHA exits — Neon has fresh data
    ↓
Vercel Flask on next request: reads from Neon → renders HTML
```

---

## 4. Database Migration: SQLite → Neon PostgreSQL

### Difficulty

**Medium-low.** The schema is 3 tables, ~10 columns, no complex types. The queries are trivial (no JOINs beyond schedule→slots via schedule_id).

### Required code changes

`store.py` — full rewrite (~130 lines, ~2h of work):
- `sqlite3` → `psycopg` (psycopg3)
- `?` placeholders → `%s`
- `INTEGER PRIMARY KEY` → `SERIAL PRIMARY KEY`
- `Path("data/pools.db")` → `os.environ["DATABASE_URL"]`
- `con.executescript()` → individual `execute()` calls

`app.py` — remove `store.init_db()` from startup, remove APScheduler import and startup code.

Everything else — zero changes.

### Recommended database layer

**Raw psycopg3 (`psycopg[binary]`). No ORM.**

- Same mental model as the current `sqlite3` code
- 5 total queries — SQLAlchemy adds 10MB of dependencies for nothing
- Direct translation: replace `sqlite3.connect(DB_PATH)` with `psycopg.connect(DATABASE_URL)`, change `?` to `%s`, done

### Is migration worth doing now?

**Only if committing to cloud deployment. Otherwise no.**

SQLite is not a weakness — it's perfectly suited to local single-process use. Don't migrate speculatively.

---

## 5. Scheduler Analysis

| Concern | APScheduler (current) | GitHub Actions cron |
|---|---|---|
| Reliability | Dies with Flask process | Independent, auto-retried |
| Visibility | Log file only | Dashboard + email on failure |
| Cost | Free (in-process) | Free (public repo) |
| Latency | Runs exactly at interval | ±5-15min jitter |
| Retry on failure | No | Configurable |
| Credentials | In process env | GHA Secrets (isolated) |
| Trigger manually | `/refresh` route | `workflow_dispatch` |

Monthly GHA consumption: parsers take ~30s total per run, once daily = **15 minutes/month** against a 2000min/month budget for private repos. Negligible.

---

## 6. API Analysis

**Keep the Flask SSR monolith. No API separation.**

The argument for a REST API + SPA split only makes sense with multiple clients, multiple developers, or client-side interactivity needs beyond what Jinja2 handles. None apply here.

The existing `/api/health` endpoint is sufficient for programmatic access. Add more API routes if and when a mobile client is actually being built.

---

## 7. Security Review

| Issue | Risk | Recommendation |
|---|---|---|
| `/refresh` is open | Low-Medium | Add `?token=` check against an env var |
| No rate limiting | Low | Neon's pgBouncer pooler handles connection limits; optional 60s in-memory cache on index route |
| Database credentials | Medium if mishandled | `DATABASE_URL` from env only — never in code. GHA: Repository Secret. Vercel: Environment Variable. |
| PDF source validation | Low | Validate discovered URL's domain is `sport.um.warszawa.pl` before fetching |
| GHA action pinning | Low | Pin `actions/checkout` etc. to SHA instead of floating tags to prevent supply chain attacks |
| Scraping ToS | Very low | One request/day per pool, honest User-Agent. City-run public service. |

---

## 8. Better Alternatives

### Alternative 1: Static Site Generation → GitHub Pages ⭐ Best overall

**The insight:** data changes once a day. There is no user interaction that requires a live server. The page could be pre-built HTML served from a CDN.

**Architecture:**

```
GHA cron (06:00 daily):
  1. checkout repo
  2. run parsers (discover + fetch + parse, exactly as now)
  3. render Jinja2 templates with all 7 days of data baked in
  4. git push rendered HTML to gh-pages branch

GitHub Pages: serves static files, no server
```

**What moves to JavaScript (small, vanilla JS):**
- Day tab switching — show/hide panels (~15 lines)
- "Teraz dostępne" summary — compute from `new Date()` using slot data embedded as JSON in HTML (~25 lines)
- Current slot highlighting — compute locally from `new Date()` (~10 lines)
- Polish date in header — `new Date().toLocaleDateString('pl-PL', ...)` (~5 lines)

**What stays unchanged:**
- All 4 parsers — zero changes
- `models.py`, `downloader.py` — zero changes
- `store.py` — used during GHA build step; SQLite stays local, discarded after build
- Visual design — identical output

**What's eliminated entirely:**
- Flask (no web server)
- SQLite as persistent infrastructure
- Neon / any cloud database
- APScheduler
- Vercel
- Cold starts
- Credential management

**Why it beats Vercel + Neon + GHA:**

Vercel + Neon + GHA is three separate services with credentials, cold starts, and connection pooling. This is one service (GitHub Pages) with a file push. Same user experience, radically simpler infrastructure.

| | Vercel + Neon + GHA | Static → GitHub Pages |
|---|---|---|
| Services | 3 | 1 |
| Cold starts | Yes (Neon ~2s) | None (CDN) |
| Credentials | DATABASE_URL everywhere | None |
| Code changes | Large (~16h) | Medium (~8h) |
| Cost | $0 | $0 |

**Tradeoffs:**
- The "current time" features (TERAZ badge, Teraz dostępne card) shift from server to client-side JS — a few dozen lines of vanilla JS, no framework needed
- No live `/refresh` — use `workflow_dispatch` manually
- Data is always from the last daily build

---

### Alternative 2: Fly.io + SQLite (near-zero code changes)

If you want a real always-on server with minimal code changes, Fly.io is better than Railway or Render.

**Architecture:**

```
Fly.io machine (shared-CPU, 256MB RAM, always-on):
  Flask + APScheduler + SQLite on a persistent Fly volume
```

**What changes:**
- `fly.toml` deploy config (new file)
- Mount a Fly volume at `/data` for SQLite persistence
- Set `DB_PATH` from an env var pointing to the volume path
- That's it

**What stays completely unchanged:**
- `app.py`, `store.py`, all parsers, templates, CSS, tests — everything

**Cost:** $0 on Fly.io free tier (3 shared-CPU VMs, 3GB persistent volume). Risk: Fly.io has tightened its free tier before.

**Why it beats Railway/Render:**
Railway costs $10/month. Render's PostgreSQL free tier expires after 90 days. Fly.io's free tier includes persistent volumes — SQLite actually works, no database migration needed.

**Tradeoffs:**
- Fly.io free tier stability not guaranteed long-term
- 256MB RAM: pdfplumber on complex A3 PDFs needs testing
- APScheduler reliability issue remains (same as current)

---

### Full Comparison

| | Vercel + Neon + GHA | Static → GitHub Pages | Fly.io + SQLite |
|---|---|---|---|
| Cost | $0 | **$0** | $0 (risk: tier changes) |
| Code changes | Large (~16h) | Medium (~8h) | **Minimal (~2h)** |
| Cold starts | Yes (Neon ~2s) | **None (CDN)** | **None (always-on)** |
| Infrastructure pieces | 3 services | **1 service** | 1 service |
| Credential management | DATABASE_URL everywhere | **None** | None |
| Reliability | Medium (3 failure points) | **High (static CDN)** | Medium (single VM) |
| Real-time server features | Yes | JS-only | **Yes** |
| Architecture change | Big | Medium | **Tiny** |

---

## 9. Migration Roadmap

*(For the Vercel + Neon + GHA path. Static Site Generation path is shorter but different.)*

### Phase 1 — Cloud Preparation (2-3h, Risk: Low)

- Extract `refresh_all()` logic into `scripts/refresh.py` as a standalone script with no Flask dependency
- Add `DATABASE_URL` env var support to `store.py` (SQLite remains default for local dev)
- Verify `.gitignore` covers `data/`, `cache/`, `.env`
- Add token check to `/refresh` route

**Benefit:** Local behavior unchanged. GHA refresh script is ready.

---

### Phase 2 — Database Migration (3-4h, Risk: Medium)

- Create Neon project + database, get `DATABASE_URL`
- Rewrite `store.py` to use `psycopg[binary]` with `DATABASE_URL`
- Run schema creation against Neon (one-time)
- Local testing: `$env:DATABASE_URL="postgresql://..."; py app.py`
- Verify `/api/health` returns data

**Risk:** SQL syntax differences are minor. Main unknown: connection handling under Vercel's cold-start model — test before deploying at scale.

---

### Phase 3 — GitHub Actions Scheduler (2-3h, Risk: Low)

- Add `.github/workflows/refresh.yml` with `schedule: cron: '0 6 * * *'` and `workflow_dispatch`
- Wire up `scripts/refresh.py` in the workflow
- Add `DATABASE_URL` as GHA Repository Secret
- Test via manual `workflow_dispatch` trigger
- Verify Neon has fresh data post-run

**Note:** Can be done before Vercel if you want the cron running while still developing locally.

---

### Phase 4 — Vercel Deployment (3-4h, Risk: Medium)

- Add `vercel.json` + `api/index.py` WSGI entry point
- Create `requirements-vercel.txt` excluding pdfplumber/openpyxl/httpx/BeautifulSoup (parsers don't run on Vercel)
- Remove `scheduler.start()` and `store.init_db()` from `app.py` startup
- Remove APScheduler from runtime dependencies
- Set `DATABASE_URL` in Vercel Dashboard
- Deploy and smoke-test: index page, `/api/health`, day navigation

---

### Phase 5 — Monitoring (1-2h, Risk: Low)

- UptimeRobot free tier: ping `/api/health` every 5 minutes (keeps Neon warm, alerts on `"status": "degraded"`)
- Verify GHA sends email on workflow failure (GitHub does this by default)
- Add `last_refresh` staleness check to health endpoint (warn if any pool's data is >48h old)

---

## 10. Decision Recommendation

### Recommended architecture

**Static Site Generation → GitHub Pages** for maximum simplicity.

**Fly.io + SQLite** if you want zero code changes and a real always-on server.

**Vercel + Neon + GHA** if you want a conventional cloud setup and are willing to spend ~16h on the migration.

### Recommended deployment strategy

Don't deploy until you have a concrete reason: checking from your phone without the laptop on, sharing with friends, running while traveling. The app works perfectly locally. Cloud deployment adds operational overhead.

### Estimated monthly cost

**$0/month** for all three recommended options, sustainably.

### Deploy now or later?

**Later.** Plan now, deploy when you have a reason.

### Biggest technical risks

| Risk | Severity | Mitigation |
|---|---|---|
| Neon cold start adds 1-3s latency after 5min idle | Medium | UptimeRobot pings every 5min to keep Neon warm |
| Pool website structure changes break `discover()` | Medium | GHA failure email + health endpoint shows stale data |
| Fly.io free tier changes | Medium | Exit path: Railway or Render, ~1 day migration |
| GHA cron jitter (±15min) | Low | Pool schedules are weekly — irrelevant |
| pdfplumber memory on 256MB Fly.io VM | Low-Medium | Test before committing |

### Biggest business risks

| Risk | Severity | Note |
|---|---|---|
| Neon / Vercel pricing changes | Medium | Both are startups. Exit path exists (~1 day work). |
| Pool website scraping ToS | Low | One request/day per pool, honest User-Agent, city public service. |
| Hobby project motivation | Practical | The biggest risk is spending 16h migrating something that works fine locally. |
