# Wstępna klasyfikacja komentarzy z YouTube'a (H1): instrukcja uruchomienia

Dokument dla osoby, która uruchamia klasyfikację na komputerze z kartą NVIDIA, oraz dla jej asystenta LLM. Idź krok po kroku. Jeśli coś się nie zgadza, zatrzymaj się i opisz problem, zamiast improwizować.

## Cel

Mały model (`qwen3:8b`, lokalnie przez Ollamę) ma nadać każdemu z około 31 tys. komentarzy dwie etykiety (`h1_related` i `job_security_concern`, wartości `yes`, `no`, `unclear`) według instrukcji zapisanej w `screening_config.json`. To wstępny filtr do wyboru komentarzy dla dalszych etapów, a nie ostateczne etykiety. Zasady są opisane w [h1-screening.md](h1-screening.md).

## Dane

Dane są na dysku wspólnym zespołu: `[WPISZ ŚCIEŻKĘ NA DYSKU]`. Potrzebny jest katalog `work_v1` z trzema plikami:

| Plik | Co to jest |
| --- | --- |
| `batches.jsonl` | 314 paczek po maksymalnie 100 komentarzy, jedna paczka na linię |
| `manifest.csv` | mapowanie krótkich ID na film, komentarz, datę i okres (przed/po) |
| `screening_config.json` | dokładna instrukcja dla modelu i opis próby |

Pliki zawierają teksty komentarzy i prawdziwe ID komentarzy YouTube'a. Trzymaj je tylko na komputerze zespołu, nie wysyłaj nigdzie poza lokalną Ollamę i nie wrzucaj do gita (`data/` jest w `.gitignore`).

## Wymagania

- Docker z obsługą GPU NVIDIA (sterownik i NVIDIA Container Toolkit). Sprawdź: `docker run --rm --gpus all ubuntu nvidia-smi`.
- Około 8 GB pamięci karty (testowano `qwen3:8b` na RTX 4060 8 GB) i około 10 GB wolnego miejsca na obraz i model.
- Klon repozytorium na gałęzi `feat/youtube-work-sampling` (po wypchnięciu zmian), albo na `main`, jeśli ta gałąź została zmergowana. Klucz YouTube (`.env`) nie jest potrzebny.

## Krok po kroku

1. Sklonuj repozytorium i przejdź na właściwą gałąź.
2. Skopiuj katalog `work_v1` z dysku do repozytorium jako `data/youtube/screening/work_v1/`.
3. **Przebuduj obraz** `classifier`, bo kod jest do niego kopiowany podczas budowania. Stary obraz (np. z wcześniejszej klasyfikacji) nie ma nowego skryptu `run_screening.py`:

   ```bash
   docker compose -f compose.yaml -f compose.gpu.yaml build classifier
   ```

   Jeśli ten Docker był już używany do klasyfikacji z GPU, model `qwen3:8b` jest w woluminie `ollama-models` i nie będzie pobierany ponownie.
4. **Test na 3 paczkach** (przy pierwszym uruchomieniu na nowym komputerze pobierany jest obraz i model, kilka GB):

   ```bash
   make docker-screen-youtube GPU=1 ARGS="--screening-dir data/youtube/screening/work_v1 --limit 3"
   ```

   Polecenie samo uruchamia Ollamę z GPU i pobiera `qwen3:8b` (`classifier` zależy od `model-init`). Sprawdź:
   - w logu 3 linie `ok b0000X (100 comments, N calls)`,
   - brak pliku `failures.jsonl` (albo jest pusty),
   - w `results.jsonl` są 3 linie,
   - zmierz czas jednej paczki i pomnóż przez 314, żeby oszacować całość.
5. Jeśli w teście są błędy, patrz sekcja „Problemy”. Nie zmieniaj instrukcji ani paczek.
6. **Pełny przebieg** (wznawialny, można przerwać `Ctrl+C` i uruchomić ponownie to samo polecenie):

   ```bash
   make docker-screen-youtube GPU=1 ARGS="--screening-dir data/youtube/screening/work_v1"
   ```

7. Po zakończeniu skrypt sam scala wyniki z `manifest.csv` do `labels.csv`. Jeśli były przerwy, można to odtworzyć: `ARGS="--screening-dir data/youtube/screening/work_v1 --merge-only"`.

Bez Dockera i bez GPU Ollama działa też natywnie (`ollama pull qwen3:8b`, potem `make screen-youtube ARGS="..."`), ale na procesorze jest wielokrotnie wolniejsza.

## Co skrypt sprawdza

Każda odpowiedź modelu jest walidowana: zgodne `batch_id`, każde wejściowe ID dokładnie raz (bez brakujących, zbędnych i powtórzonych), tylko wartości `yes`, `no`, `unclear` oraz reguła „`h1_related` = no wymaga `job_security_concern` = no”. Błędna odpowiedź jest ponawiana (domyślnie 3 razy), a jeśli nadal się nie udaje, paczka jest dzielona na połowy aż do 10 komentarzy. Paczka, której nie da się zaetykietować, trafia do `failures.jsonl` i zostaje bez etykiet. Wyniki są dopisywane do `results.jsonl` na bieżąco, więc przerwanie niczego nie gubi. Skrypt odmawia dopisywania do wyników z innym modelem lub instrukcją.

## Problemy

| Objaw | Co zrobić |
| --- | --- |
| Błąd braku pamięci lub restart Ollamy | uruchom z mniejszym kontekstem: `--num-ctx 12288` (albo 8192 i mniejsze paczki, patrz niżej) |
| Wiele paczek w `failures.jsonl` | uruchom polecenie jeszcze raz (ponowi tylko brakujące); jeśli dalej, zmniejsz paczki: wygeneruj nowe (`scripts/youtube/prepare_screening.py --database ... --batch-size 30 --max-batch-chars 10000` do nowego katalogu) i zgłoś to |
| `Ollama request failed` | sprawdź, czy kontener `ollama` działa i ma model: `docker compose ps`, `docker compose exec ollama ollama list` |
| Bardzo wolno | zmierz czas paczki i zgłoś; nie zmieniaj modelu |

## Co oddać

Skopiuj z `data/youtube/screening/work_v1/` na dysk wspólny, do podkatalogu `results`: `results.jsonl`, `labels.csv` i `failures.jsonl` (jeśli istnieje). Dołącz krótką notatkę z:

- modelem i jego skrótem (`docker compose exec ollama ollama list`, kolumna ID), wersją Ollamy, kartą GPU,
- łącznym czasem i średnim czasem paczki,
- liczbą komentarzy z etykietami i bez (komunikat `Merged: {...}` na końcu),
- rozkładem etykiet (`yes`/`no`/`unclear` dla obu pól) osobno dla `pre` i `post`,
- wszystkimi błędami i tym, co z nimi zrobiono.

Wynik jest poprawny, gdy `labels.csv` ma tyle wierszy, ile `manifest.csv` (31 315), a `failures.jsonl` jest pusty.

## Zasady dla asystenta LLM

- Nie zmieniaj `batches.jsonl`, `manifest.csv`, instrukcji w `screening_config.json` ani modelu (`qwen3:8b`) bez zgody osoby prowadzącej.
- Nie poprawiaj ręcznie etykiet i nie usuwaj `results.jsonl`, żeby „naprawić” błąd. Błędy zgłaszaj.
- Nie commituj danych ani wyników (to jest w `.gitignore`) i nie dodawaj kluczy ani plików `.env`.
- Nie wysyłaj komentarzy do żadnej usługi zewnętrznej. Jedyny odbiorca to lokalna Ollama.
- Przed pełnym przebiegiem zawsze wykonaj test na 3 paczkach i podaj zmierzony czas.
- Jeśli instrukcja tu nie wystarcza, zatrzymaj się i zapytaj, zamiast zgadywać.
