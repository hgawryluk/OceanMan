# OceanMan

Prywatna aplikacja webowa do śledzenia wolnych torów w warszawskich pływalniach publicznych. Zamiast sprawdzać cztery strony OSiR — jeden rzut oka i wiesz, gdzie warto pojechać.

## Obsługiwane pływalnie

| Pływalnia | Adres | Tory | Slot | Format harmonogramu |
|---|---|---|---|---|
| Delfin | ul. Kasprzaka 1/3 | 6 | 30 min | XLSX |
| Foka | ul. Esperanto 5 | 6 | 30 min | PDF (siatka kolorów, A3) |
| Inflancka | ul. Inflancka 8 | 10 | 15 min | PDF (siatka kolorów, 7 stron) |
| Potocka | ul. Potocka 1 | 8 (tory 1–6 + R + B) | 15 min | PDF (siatka kolorów, 1 strona pozioma) |

## Zrzut ekranu

Dashboard pokazuje 4 karty pływalni z listą slotów — kolory od ciemnoczerwony (0 wolnych) do zielony (wszystkie wolne). Aktualna godzina jest podświetlona, minione sloty wyszarzone. Karta podsumowania „Teraz dostępne tory" jest widoczna tylko podczas godzin otwarcia.

## Uruchomienie lokalne

```powershell
py app.py
```

Serwer startuje na `http://127.0.0.1:5000`. Przy starcie automatycznie pobiera harmonogramy ze wszystkich czterech pływalni. Kolejne odświeżenia co 6 godzin (APScheduler).

Aby zatrzymać stary proces przed restartem (Windows):

```powershell
Stop-Process -Name python -Force -ErrorAction SilentlyContinue
```

## Testy

```powershell
py -m pytest tests/ -v
```

Testy obejmują:
- Parsery wszystkich 4 pływalni (fixtures z rzeczywistymi PDF/XLSX)
- Funkcje pomocnicze (`_is_white`, `_color_is_free`, `_parse_time`)
- Warstwę danych (`store.py`) — upsert, deduplication po hashu, fetch log
- Logikę slotów (`_lane_class`, `_prepare_slots`)

## Stos technologiczny

- **Backend:** Python 3.12, Flask, APScheduler
- **Parsowanie:** pdfplumber (PDF), openpyxl (XLSX), httpx, BeautifulSoup
- **Baza danych:** SQLite (`data/pools.db`)
- **Frontend:** Jinja2, czysty CSS (Inter, Material Symbols)

## Struktura projektu

```
app.py              # trasy Flask, scheduler, logika slotów
models.py           # dataclasses: SlotReading, PoolSchedule
store.py            # SQLite: init, upsert, get, log_fetch
downloader.py       # fetch_pdf(url) → (bytes, md5)
build.py            # generator statycznej strony HTML (dist/)
generate.py         # generator danych JSON (docs/data/)
pools/
  delfin.py         # discover() + parse() — XLSX
  foka.py           # discover() + parse() — detekcja prostokątów kolorowych
  inflancka.py      # discover() + parse() — detekcja kolorów komórek
  potocka.py        # discover() + parse() — 64-kolumnowa siatka tygodniowa
templates/
  index.html        # główny widok z JS do live-update zegarów i slotów
static/
  style.css         # design tokens, siatka, karty, sloty, poziomy kolorów
tests/
  fixtures/         # prawdziwe PDF/XLSX do testów integracyjnych
  test_delfin.py
  test_foka.py
  test_inflancka.py
  test_potocka.py
  test_app_units.py
  test_store.py
  test_helper_units.py
```

## Jak działa parsowanie

Każda pływalnia ma moduł `pools/<nazwa>.py` z dwiema funkcjami:

- `discover()` — scraping strony OSiR, wybiera URL aktualnego pliku (najnowszy według daty)
- `parse(bytes, url, md5)` → `PoolSchedule` — wyciąga sloty z pliku

### Strategie detekcji

- **Delfin:** openpyxl, liczby w komórkach = wolne tory bezpośrednio
- **Foka / Potocka:** detekcja wypełnionych prostokątów w PDF. Komórka wolna = brak prostokąta lub prostokąt biały. Nakładanie się liczone przez overlap (`MIN_LANE_OVERLAP = 3 px`) zamiast centrum — bloki rezerwacji obejmujące wiele torów były błędnie zliczane metodą centrum
- **Inflancka:** detekcja konkretnego koloru niebieskiego z legendy PDF (`FREE_COLOR ≈ (0.706, 0.776, 0.906)`) — komórka wolna = zawiera prostokąt w tym kolorze

## System kolorów dostępności

7 poziomów opartych na stosunku `wolne / wszystkie` — działa jednakowo dla 6, 8 i 10 torów.

| Stosunek | CSS | Znaczenie |
|---|---|---|
| 100% | `level-6` | Swobodnie |
| ~83% | `level-5` | |
| ~67% | `level-4` | Komfortowo |
| 50% | `level-3` | |
| ~33% | `level-2` | Tłoczno |
| ~17% | `level-1` | |
| 0% | `level-0` | Brak wolnych |

## Wdrożenie (GitHub Pages)

Repozytorium zawiera gotowy workflow GitHub Actions (`.github/workflows/deploy.yml`), który codziennie o 06:00 UTC:
1. Pobiera harmonogramy ze wszystkich 4 pływalni
2. Generuje 7 statycznych stron HTML (`dist/`)
3. Wdraża na GitHub Pages

Aby włączyć: **Settings → Pages → Source: GitHub Actions**, następnie uruchom workflow ręcznie.
