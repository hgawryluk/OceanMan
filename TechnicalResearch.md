# Technical Research Report — Warsaw Pool Schedules

## 1. Source Analysis

### 1.1 Foka — Pływalnia Kryta Foka (Esperanto 5)

**Official page:** `sport.um.warszawa.pl/waw/osir-wola/-/plywalnia-kryta-foka-esperanto-5`

**Schedule document found on page:** "Wykaz wolnych torów czerwiec" (June free lanes list)

**PDF structure (observed):**
- Single page, A4 landscape
- Title: "Rezerwacja torów obowiązuje od: 1 czerwiec 2026"
- A 7-day × 32-slot × 6-lane colour grid
- Time slots: 30-minute intervals, 06:00–22:00
- Days: sobota (Sat), niedziela (Sun), poniedziałek (Mon), wtorek (Tue), środa (Wed), czwartek (Thu), piątek (Fri)
- Each day column is subdivided into 6 lane sub-columns (numbered 1–6 in header/footer)
- **Coloured cell = reserved lane** (colours represent different organisations; colour identity is irrelevant — presence is what matters)
- **White/empty cell = free lane**
- Created by: Microsoft Excel for Microsoft 365, author "OW00273 Inspektor Foka"
- File size: ~207 KB

**Free lane count derivation:**  
For each (day, time_slot) pair, count how many of the 6 lane cells are NOT covered by a coloured rectangle → free_lanes = 6 − reserved_count.

**Parsing difficulty:** HIGH  
All reservation data is encoded as vector fill colours. There is no text inside cells. Requires geometric analysis of PDF graphics objects.

**Discovery approach:**  
The link on the official page carries a human-readable label ("Rezerwacje torów" or "Wykaz wolnych torów"). The URL contains a `?t=` Unix-millisecond timestamp. Matching on `rezerwac` or `wolnych` (case-insensitive, Polish) in the link text is sufficient.

**Update frequency:** Monthly (one PDF per month). No mid-month updates observed.

---

### 1.2 Delfin — Pływalnia Kryta Delfin (Kasprzaka 1/3)

**Official page:** `sport.um.warszawa.pl/waw/osir-wola/-/plywalnia-kryta-delfin-kasprzaka-1-3`

**Schedule documents:**
- Large pool: PDF — "WYKAZ WOLNYCH TORÓW NA PŁYWALNI 'DELFIN'" (~85 KB)
- Small pool (brodzik): Excel `.xlsx` file

**PDF structure (observed — large pool):**
- Single page
- Plain bordered table
- Rows: 30-minute time slots, 07:00–22:00 (30 rows)
- Columns: Pon. | Wt. | Śr. | Czw. | Pt. | Sob. | Niedz. (7 columns)
- Cell values: integers 0–6 = number of **free lanes**
- Yellow background on cells = 0 free lanes (fully booked)
- Season label: "2025/2026" — this schedule is season-wide, not week-specific
- Created by: Microsoft Excel via Acrobat PDFMaker, user "mcwikielewicz"

**Free lane count derivation:**  
Direct read — values ARE the free lane counts.

**Parsing difficulty:** LOW  
`pdfplumber.extract_table()` will produce a clean 2D array. Minor cleanup: strip whitespace, convert to int, map column headers to weekday names.

**Discovery approach:**  
Same CMS as Foka. Match on link text containing "wolnych torów" or "grafik" + "basen" in the vicinity. The XLSX link for the small pool can be ignored for the initial implementation. The `?t=` timestamp signals content changes.

**Update frequency:** Appears seasonal (covers full 2025/2026 season). May be updated mid-season if reservations change substantially.

---

### 1.3 Inflancka — Ośrodek Inflancka

**Official schedule page:** `sport.um.warszawa.pl/waw/aktywna-warszawa/-/harmonogramy-zajec-i-dostepnosci-obiektow-w-osrodku-inflancka`

**Schedule documents (pool only):**
- One PDF per week (Mon–Sun), occasionally two overlapping weeks listed simultaneously
- Filename pattern: `harmonogram++pop+2+DD-DD.pdf` / `harmonogram+DD-DD.MM.pdf`
- Size: ~760 KB (7 pages, one per day)

**PDF structure (observed):**
- 7 pages, one per weekday: Poniedziałek, Wtorek, Środa, Czwartek, Piątek, Sobota, Niedziela
- Each page:
  - Header: "Harmonogram rezerwacji torów od DD.MM.YYYYr do DD.MM.YYYYr"
  - Grid with time column (Od/Do = from/to, 15-min slots: 06:15–21:30)
  - 10 numbered lane columns (9, 8, 7, 6, 5, 4, 3, 2, 1, 0) — note: right-to-left order
  - 4 paddling pool columns (cz.1, cz.2, cz.3, cz.4)
  - Coloured cells with text labels (club/organisation names)
  - Legend per page
- Created by: Microsoft Excel 2024
- Valid for specific date range shown in title

**Cell type classification (from legend):**

| Colour | Label | Meaning for free-lane count |
|---|---|---|
| Light blue | Tory dostępne | FREE (fully public) |
| Medium blue | Tor klient indywidualny | FREE (open to individual swimmers) |
| Pink/purple | Zajęcia Aktywna Mama | RESERVED |
| Green | Aqua aerobic | RESERVED |
| Orange | Lato/Zima w mieście | RESERVED |
| Light green | Zajęcia senior | RESERVED |
| Dark blue | Grupowa nauka pływania | RESERVED |
| Red | Trening i sportowe | RESERVED |
| Light yellow | Brodzik dostępny | Paddling pool free (separate count) |

**Key text labels in cells:**
- `"TOR DLA KLIENTÓW INDYWIDUALNYCH"` — individual customer lane, counts as free
- `"Tory dostępne"` text may also appear — free
- Organisation names (PALESTRA, UW, LO 59, etc.) — reserved

**Free lane count derivation:**  
For each (day_page, time_slot, lane_column): if no reserved-category text/colour is present → free. Lane 0 ("Tor skrócony" = short lane) may be a shortened lane; count it separately if needed.

**Parsing difficulty:** MEDIUM-HIGH  
Text extraction with `pdfplumber` works (club names ARE text in the PDF layer), but spatial mapping is required — the word bounding box must be matched to the correct lane column and time row. The reversed lane order (9→0 left-to-right in the PDF header) must be handled.

**Discovery approach:**  
Fetch schedule page HTML. Collect all PDF links whose URL contains `"harmonogram"` and whose visible date label does NOT contain "siłownia", "sala fitness", or "brodzik". Among remaining links, identify the one with the most recent end date (the `do DD.MM.YYYY` part of the title text or link label). The `?t=` timestamp also helps.

**Update frequency:** Weekly (new PDF every 7 days). Page may list the current and next week simultaneously. System must pick the latest.

---

## 2. CMS Observations

All three pools are hosted on the Liferay portal `sport.um.warszawa.pl`. Observations:
- Pages render server-side — no JavaScript execution required to see PDF links
- PDF URLs follow the pattern: `/documents/{article_id}/{folder_id}/{filename}.pdf/{uuid}?t={ms_timestamp}`
- The `?t=` millisecond timestamp in the query string changes when the document is replaced
- HTTP `Last-Modified` and `ETag` headers may also be present on PDF responses
- No authentication required; documents are publicly accessible

---

## 3. Library Selection Rationale

| Library | Purpose | Rationale |
|---|---|---|
| `httpx` | HTTP fetching | Sync + async support, good timeout handling |
| `beautifulsoup4` + `lxml` | HTML parsing | Robust against malformed HTML from Liferay |
| `pdfplumber` | PDF text + graphics | Exposes both text words (with bbox) AND graphical objects (rects with fill) in one API |
| `pdf2image` | PDF→image fallback | Only needed if Foka vector approach fails |
| `Pillow` | Image colour sampling | Used with pdf2image fallback |
| `APScheduler` | Periodic scheduling | Simple in-process scheduler, no external daemon needed |
| `sqlite3` | Data persistence | Stdlib, zero dependencies, sufficient for this scale |
| `tomllib` (stdlib 3.11+) | Config parsing | No extra deps |
| `pytest` | Testing | Standard |

---

## 4. Key Risks & Mitigations

| Risk | Likelihood | Mitigation |
|---|---|---|
| Foka PDF grid coordinates shift when new Excel template is used | Medium | Derive grid geometry dynamically from header row position, not hardcoded coords |
| Inflancka stops embedding text in PDF (switches to image-only export) | Low | Detect empty text extraction → fall back to image+OCR (tesseract) |
| Pool page HTML structure changes (link discovery breaks) | Medium | Use multiple selector strategies (link text + URL pattern); alert on zero matches |
| Inflancka posts overlapping weeks simultaneously | Already observed | Always pick PDF with the latest `valid_to` date |
| Delfin schedule is seasonal and rarely changes | — | Still re-check `?t=` timestamp; log but don't alert on stable data |
| OSiR Wola publishes schedule under different URL path | Low | Broaden discovery to search entire page, not just one section |
| Network failure / PDF temporarily unavailable | Medium | Retry with exponential backoff (3 attempts); use cached version |

---

## 5. Observed Schedule Validity

| Pool | Granularity | Scope |
|---|---|---|
| Foka | 30 min | Monthly (valid from 1st of month) |
| Delfin | 30 min | Seasonal (2025/2026 academic year) |
| Inflancka | 15 min | Weekly (Mon–Sun, updated every ~7 days) |

The application must handle these different temporal scopes when storing and querying data.
