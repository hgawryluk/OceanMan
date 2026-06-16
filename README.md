# OceanMan

Prywatna aplikacja webowa do śledzenia wolnych torów w warszawskich pływalniach publicznych. Zamiast sprawdzać cztery strony OSiR, wystarczy spojrzeć na jeden dashboard.

## Co robi

Pobiera harmonogramy PDF/XLSX z czterech pływalni OSiR Warszawa i pokazuje liczbę wolnych torów na każdy slot czasowy, w rozbiciu na dni tygodnia.

## Obsługiwane pływalnie

| Pływalnia | Adres | Tory | Slot | Format |
|---|---|---|---|---|
| Delfin | ul. Kasprzaka 1/3 | 6 | 30 min | XLSX |
| Foka | ul. Esperanto 5 | 6 | 30 min | PDF (siatka kolorów, A3) |
| Inflancka | ul. Inflancka 8 | 10 | 15 min | PDF (siatka kolorów, 7 stron) |
| Potocka | ul. Potocka 1 | 8 (1–6 + R + B) | 15 min | PDF (siatka kolorów, 1 strona pozioma) |

## Stos technologiczny

- **Backend:** Python 3.12, Flask, APScheduler
- **Parsowanie:** pdfplumber (PDF), openpyxl (XLSX), httpx, BeautifulSoup
- **Baza danych:** SQLite (`data/pools.db`)
- **Frontend:** Jinja2, czysty CSS (Material Design 3, Inter font)

## Struktura plików

```
app.py              # trasy Flask, scheduler, logika slotów
models.py           # dataclasses: SlotReading, PoolSchedule
store.py            # SQLite: init, upsert, get, log_fetch
downloader.py       # fetch_pdf(url) → (bytes, md5)
pools/
  delfin.py         # discover() + parse() — XLSX z fallbackiem PDF
  foka.py           # discover() + parse() — wykrywanie zachodzących prostokątów
  inflancka.py      # discover() + parse() — detekcja kolorów komórek
  potocka.py        # discover() + parse() — 64-kolumnowa siatka, detekcja białego
templates/
  index.html        # główny widok
static/
  style.css         # design tokens, siatka, karty, sloty
data/
  pools.db          # SQLite (tworzony przy pierwszym uruchomieniu)
```

## Uruchomienie

```powershell
py app.py
```

Serwer startuje na `http://127.0.0.1:5000`. Przy starcie automatycznie pobiera harmonogramy ze wszystkich czterech pływalni. Kolejne odświeżenia co 6 godzin (APScheduler). Ręczne odświeżenie: przycisk **↻ Odśwież** w aplikacji lub `/refresh`.

Aby zatrzymać stary proces przed restartem (Windows):

```powershell
$pids = (Get-NetTCPConnection -LocalPort 5000).OwningProcess | Sort-Object -Unique
foreach ($p in $pids) { Stop-Process -Id $p -Force }
```

## Jak działa parsowanie

Każda pływalnia ma moduł `pools/<nazwa>.py` z dwiema funkcjami:

- `discover()` — scraping strony OSiR, zwraca URL aktualnego pliku
- `parse(bytes, url, md5)` → `PoolSchedule` — wyciąga sloty z pliku

### Strategie detekcji

- **Delfin:** openpyxl, liczby w komórkach = wolne tory
- **Foka / Inflancka / Potocka:** detekcja prostokątów kolorowych w PDF. Wolny slot = brak prostokąta lub prostokąt biały/brak koloru. Detekcja nakładania się (`MIN_LANE_OVERLAP=3px`) zamiast sprawdzania centrum — szerokie bloki rezerwacji (obejmujące wiele torów) były błędnie zliczane metodą centrum.

## System kolorów dostępności (7 poziomów)

Oparty na stosunku wolnych/wszystkich torów — działa dla każdej liczby torów (6, 8, 10).

| Stosunek | Klasa CSS | Kolor |
|---|---|---|
| 100% | level-6 | Zielony `#4CAF50` |
| ~83% | level-5 | Jasnozielony `#66BB6A` |
| ~67% | level-4 | Bladozielony `#A5D6A7` |
| 50% | level-3 | Bursztynowy `#FFB300` |
| ~33% | level-2 | Pomarańczowy `#FF7043` |
| ~17% | level-1 | Czerwony `#E53935` |
| 0% | level-0 | Ciemnoczerwony `#B71C1C` |

## UI

- 4 karty pływalni w siatce (≥1100px), 2 kolumny (≤1100px), 1 kolumna (≤580px)
- Karty w dzień bieżący: auto-scroll do aktualnego slotu, wymroczenie minionych slotów
- Nagłówek karty: odznaka z aktualną liczbą wolnych torów (tylko podczas godzin otwarcia)
- Nawigacja po dniach: Pon / Wt / Śr / Czw / Pt / Sob / Niedz — aktualizuje wszystkie karty jednocześnie
- Separatory godzinowe w liście slotów (sticky, ułatwiają nawigację w pływalniach 15-minutowych)
- Pasek statusu: "Harmonogramy są aktualizowane raz w tygodniu" + przycisk ↻ Odśwież
