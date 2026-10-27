# Klasyfikacja komentarzy z YouTube'a według wytycznych etapu 1 (`ai`, `work`)

Dokument dla osoby, która uruchamia klasyfikację na komputerze z kartą NVIDIA, oraz dla jej asystenta LLM. Idź krok po kroku. Jeśli coś się nie zgadza, zatrzymaj się i opisz problem, zamiast improwizować.

## Cel

Model `qwen3:8b` (lokalnie przez Ollamę) ma nadać każdemu z około 31 tys. komentarzy dwie etykiety, `ai` i `work` (`yes`/`no`), według wytycznych etapu 1 ([Wykop](../wykop/annotation-guidelines.md); YouTube ma te same zasady, różnice opisuje [annotation-guidelines.md](annotation-guidelines.md)). Używamy tego samego skryptu i promptu co przy Wykopie: `scripts/wykop/classify_entries.py` i `amc/classification/job_concern.py`. Wynik to wstępny filtr (komentarze o AI i pracy), a nie ostateczne etykiety.

## Dane

Dane są na dysku wspólnym zespołu, w folderze `screening/work_v1` (obok jest `work_sample_v3` z bazą źródłową, która do tego zadania nie jest potrzebna). Jeśli nie możesz ich znaleźć, zapytaj osobę, która przekazała Ci to zadanie. Z `work_v1` potrzebne są dwa pliki:

| Plik | Co to jest |
| --- | --- |
| `batches.jsonl` | teksty komentarzy z krótkimi ID (`c00000001`, ...) |
| `manifest.csv` | mapowanie krótkich ID na film, komentarz, datę i okres (przed/po) |

Pliki zawierają teksty komentarzy i prawdziwe ID komentarzy YouTube'a (w `manifest.csv`). Model dostaje tylko tekst i krótkie ID. Trzymaj pliki tylko na komputerze zespołu i nie wrzucaj ich do gita (`data/` jest w `.gitignore`).

## Wymagania

- Docker z obsługą GPU NVIDIA (sterownik i NVIDIA Container Toolkit). Sprawdź: `docker run --rm --gpus all ubuntu nvidia-smi`.
- Około 8 GB pamięci karty (`qwen3:8b` był już testowany na RTX 4060 8 GB) i około 10 GB wolnego miejsca na obraz i model.
- Klon repozytorium na gałęzi `feat/youtube-stage1-run` (albo na `main`, jeśli ta gałąź została zmergowana). Muszą być pliki `scripts/wykop/classify_entries.py`, `amc/classification/job_concern.py` i `scripts/youtube/stage1_comments.py`. Klucz YouTube (`.env`) nie jest potrzebny.

## Krok po kroku

W poleceniach poniżej `DC` to skrót od `docker compose -f compose.yaml -f compose.gpu.yaml`.

1. Sklonuj repozytorium i przejdź na właściwą gałąź.
2. Skopiuj `batches.jsonl` i `manifest.csv` do `data/youtube/screening/work_v1/`.
3. **Przebuduj obraz** `classifier`, bo kod jest do niego kopiowany podczas budowania (stary obraz nie ma nowych skryptów):

   ```bash
   docker compose -f compose.yaml -f compose.gpu.yaml build classifier
   ```

   Jeśli ten Docker był już używany do klasyfikacji z GPU, model `qwen3:8b` jest w woluminie `ollama-models` i nie będzie pobierany ponownie.
4. **Przygotuj wejście** (tworzy `stage1_input.csv`; nie uruchamia Ollamy):

   ```bash
   docker compose -f compose.yaml -f compose.gpu.yaml run --rm --no-deps classifier scripts/youtube/stage1_comments.py export --screening-dir data/youtube/screening/work_v1
   ```

   Oczekiwany komunikat: `Wrote 31315 comments to stage1_input.csv`.
5. **Test na 20 komentarzach** (pierwsze uruchomienie na nowym komputerze pobiera obraz i model, kilka GB):

   ```bash
   make docker-classify-wykop GPU=1 ARGS="--input data/youtube/screening/work_v1/stage1_input.csv --output data/youtube/screening/work_v1/stage1_output.csv --limit 20"
   ```

   Sprawdź: `Saved 20 predictions; 0 invalid answers`, a w logu jest szacunek czasu (`~X h left`). Sprawdź też, że model liczy na GPU: `docker compose exec ollama ollama ps` powinno pokazać `100% GPU`.
6. **Pełny przebieg** (wznawialny: można przerwać `Ctrl+C` i uruchomić to samo polecenie, już zapisane predykcje są pomijane):

   ```bash
   make docker-classify-wykop GPU=1 ARGS="--input data/youtube/screening/work_v1/stage1_input.csv --output data/youtube/screening/work_v1/stage1_output.csv"
   ```

   Na końcu jest komunikat `Saved N predictions; M invalid answers will be retried next run`. Jeśli `M` > 0, uruchom polecenie jeszcze raz, aż będzie 0. Orientacyjny czas to kilka godzin (przy wcześniejszym teście około 0,55 s na komentarz; zmierz w kroku 5).
7. **Scal z manifestem** (tworzy `stage1_labels.csv` z okresem i filmem):

   ```bash
   docker compose -f compose.yaml -f compose.gpu.yaml run --rm --no-deps classifier scripts/youtube/stage1_comments.py merge --screening-dir data/youtube/screening/work_v1
   ```

   Poprawny wynik: `Merged into stage1_labels.csv: {'manifest': 31315, 'labeled': 31315, 'missing': 0}`. Jeśli `missing` > 0, wróć do kroku 6.

Bez Dockera i bez GPU Ollama działa też natywnie (`ollama pull qwen3:8b`, potem `make classify-wykop ARGS="..."` z tymi samymi argumentami), ale na procesorze jest wielokrotnie wolniejsza.

## Co oddać

Skopiuj `stage1_output.csv` i `stage1_labels.csv` z `data/youtube/screening/work_v1/` na dysk wspólny (podkatalog `results`). Dołącz krótką notatkę z:

- modelem i jego skrótem (`docker compose exec ollama ollama list`, kolumna ID), wersją Ollamy, kartą GPU,
- łącznym czasem i średnim czasem na komentarz,
- komunikatem z kroku 7,
- rozkładem etykiet (`ai` i `work`: `yes`/`no`) osobno dla `pre` i `post`,
- wszystkimi błędami i tym, co z nimi zrobiono.

## Problemy

| Objaw | Co zrobić |
| --- | --- |
| `Ollama request failed` | sprawdź, czy kontener `ollama` działa i ma model: `docker compose ps`, `docker compose exec ollama ollama list` |
| `ollama ps` pokazuje CPU zamiast GPU | sprawdź sterownik i NVIDIA Container Toolkit, nie uruchamiaj pełnego przebiegu na CPU |
| Wiele `invalid answers` | uruchom jeszcze raz; jeśli utrzymuje się, zgłoś (nie zmieniaj promptu) |
| Za wolno | zmierz czas i zgłoś; zwiększenie `OLLAMA_NUM_PARALLEL` i `--workers` (np. do 4) może pomóc, jeśli starcza pamięci karty |

## Zasady dla asystenta LLM

- Nie zmieniaj `amc/classification/job_concern.py` (prompt), modelu (`qwen3:8b`) ani plików wejściowych bez zgody osoby prowadzącej. Zmiana promptu zmienia hash i unieważnia dotychczasowe wyniki.
- Nie poprawiaj ręcznie etykiet i nie usuwaj `stage1_output.csv`, żeby „naprawić” błąd. Błędy zgłaszaj.
- Nie commituj danych ani wyników i nie dodawaj kluczy ani plików `.env`.
- Nie wysyłaj komentarzy do żadnej usługi zewnętrznej. Jedyny odbiorca to lokalna Ollama.
- Przed pełnym przebiegiem zawsze wykonaj test na 20 komentarzach i podaj zmierzony czas.
- Jeśli instrukcja tu nie wystarcza, zatrzymaj się i zapytaj, zamiast zgadywać.
