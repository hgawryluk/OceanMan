# OceanMan — Opcje wdrożenia

## Wymagania aplikacji

| Wymaganie | Uwaga |
|---|---|
| Python 3.12 | |
| Proces ciągły | APScheduler odświeża dane co 6h |
| Zapis na dysk | SQLite (`data/pools.db`) |
| Wychodzący HTTP | Pobieranie PDF/XLSX z OSiR |
| Zawsze włączony | Nie serverless |

Vercel w trybie serverless **nie spełnia** tych wymagań bez zmiany architektury.

---

## Opcja 1 — GitHub Pages (statyczna strona)

**Status: gotowe — wymaga tylko włączenia**

Workflow `.github/workflows/deploy.yml` już istnieje. Codziennie o 06:00 UTC:
1. Pobiera harmonogramy ze wszystkich 4 pływalni
2. Generuje 7 statycznych stron HTML
3. Wdraża na GitHub Pages

| | |
|---|---|
| Koszt | **Darmowe** na zawsze |
| Świeżość danych | Max 24h opóźnienia |
| URL | `hgawryluk.github.io/OceanMan` |
| Własna domena | Tak (ustawienie w repo) |
| Co trzeba zrobić | Settings → Pages → Source: GitHub Actions → uruchomić workflow |

✅ Zalety: zero kosztu, zero utrzymania, już zbudowane  
⚠️ Wady: dane odświeżane raz dziennie (wystarczy dla harmonogramów tygodniowych)

---

## Opcja 2 — Vercel + JSON frontend

**Status: wymaga przepisania frontendu (~1 sesja pracy)**

GitHub Actions uruchamia `generate.py` → commituje `docs/data/availability.json` → Vercel automatycznie wdraża frontend JS, który czyta dane z tego pliku.

| | |
|---|---|
| Koszt | **Darmowe** na zawsze |
| Świeżość danych | Max 24h opóźnienia (tak samo jak GitHub Pages) |
| URL | `oceanman.vercel.app` lub własna domena |
| Własna domena | Tak (łatwe w panelu Vercel) |
| Co trzeba zrobić | Zbudować standalone HTML+JS czytający z JSON, podpiąć repo do Vercel |

✅ Zalety: ładniejszy URL, łatwa własna domena, auto-deploy przy każdym commicie  
⚠️ Wady: trzeba przepisać frontend jako standalone JS (bez Jinja2)

---

## Opcja 3 — Railway (pełna aplikacja Flask)

**Status: wymaga ~30 min konfiguracji**

Podpięcie repozytorium GitHub do Railway, ustawienie komendy startowej `python app.py`. Aplikacja działa dokładnie tak jak lokalnie — z APSchedulerem, SQLite, live danymi.

| | |
|---|---|
| Koszt | ~$5/miesiąc (trial darmowy) |
| Świeżość danych | **Real-time** (APScheduler działa normalnie) |
| URL | `oceanman.up.railway.app` lub własna domena |
| Własna domena | Tak |
| Co trzeba zrobić | Konto Railway, podpięcie repo, `railway.json` + `Procfile` |

✅ Zalety: zero zmian w kodzie, live dane, pełna aplikacja  
⚠️ Wady: $5/miesiąc, płatne

---

## Opcja 4 — Render (pełna aplikacja Flask, darmowa)

**Status: wymaga ~30 min konfiguracji**

Podobnie do Railway, ale darmowy tier istnieje. Wada: aplikacja zasypia po 15 min bezczynności i potrzebuje ~30s na cold start.

| | |
|---|---|
| Koszt | **Darmowe** (z cold startami) lub $7/miesiąc (always-on) |
| Świeżość danych | Real-time |
| URL | `oceanman.onrender.com` lub własna domena |
| Co trzeba zrobić | Konto Render, podpięcie repo, ustawienie komendy startowej |

✅ Zalety: darmowe, zero zmian w kodzie  
⚠️ Wady: cold start ~30s jeśli nikt nie odwiedził przez 15 min

---

## Porównanie

| | GitHub Pages | Vercel + JSON | Railway | Render |
|---|---|---|---|---|
| Koszt | Darmowe | Darmowe | ~$5/mies. | Darmowe* |
| Świeżość danych | 24h | 24h | Real-time | Real-time |
| Praca do zrobienia | Minimalnie | Średnio | Minimalnie | Minimalnie |
| Własna domena | Tak | Tak | Tak | Tak |
| Zmiany w kodzie | Brak | Frontend JS | Brak | Brak |

*z cold startami

---

## Rekomendacja

**Teraz (5 minut):** GitHub Pages — włączyć w Settings → Pages  
**Jeśli chcesz ładniejszy URL:** Vercel + przepisanie frontendu na JSON  
**Jeśli chcesz live dane i nie chcesz pisać kodu:** Railway ($5/mies.)

Harmonogramy pływalni zmieniają się tygodniowo, więc 24h opóźnienie jest w praktyce nieodczuwalne. GitHub Pages pokrywa 95% potrzeb za $0.
