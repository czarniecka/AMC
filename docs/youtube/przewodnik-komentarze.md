# Komentarze z YouTube: pobieranie i przygotowanie do analizy H1

Ten dokument opisuje obecny przepływ danych w repozytorium. Jednostką analizy
jest **pojedynczy komentarz**, a `video_id` służy do ustalenia źródła i uniknięcia
ponownego pobrania tego samego filmu. Skrypty pobierają publiczne komentarze
najwyższego poziomu; nie pobierają odpowiedzi na komentarze.

## Po co zbieramy te dane

**H1:** Po premierze ChatGPT w listopadzie 2022 r. w dyskusjach internetowych
rośnie udział wypowiedzi wyrażających obawy o utrzymanie pozycji zawodowej i
stabilność zatrudnienia wobec rozwoju AI.

Chcemy znaleźć komentarze dotyczące AI i pracy, odróżnić wśród nich wypowiedzi
wyrażające obawy o bezpieczeństwo zatrudnienia, a następnie porównać ich udział
w czasie. Model ocenia treść komentarza. Data publikacji komentarza służy do
analizy okresów, ale nie jest podawana modelowi jako wskazówka do etykietowania.

**H2** dotyczy zmian wymagań kompetencyjnych w ogłoszeniach o pracę po 2023 r.,
zwłaszcza wymagań cyfrowych i związanych z AI w zawodach bardziej narażonych na
AI. Dane z YouTube nie testują H2; w repozytorium służą do tego osobne moduły
`amc/jobs/` i dokumenty w `docs/jobs/`.

## Przepływ danych

```text
zapytania YouTube → kandydaci (filmy) → wybór video_id → komentarze CSV
                                                ↓
                               paczki JSONL + manifest → mały model
                                                           ↓
                                  dobór 5–10 tys. wpisów → większy model
                                                           ↓
                                  kontrola ludzka → klasyfikator → analiza H1
```

W tym repozytorium działają pobieranie komentarzy i przygotowanie paczek JSONL.
Automatyczne wysyłanie paczek do Luny/Sol/Opus, sprawdzanie ich odpowiedzi,
dobór 5–10 tys. wpisów i trenowanie BERT-a nie są jeszcze zaimplementowane.
Dotychczasowy klasyfikator Ollama używa innego zadania (`relevance` i `impact`);
nie należy traktować jego wyników jako gotowych etykiet H1.

## 1. Przygotowanie dostępu

Uruchamiaj polecenia z katalogu głównego repozytorium. Potrzebne są `uv`, dostęp
do sieci i klucz YouTube Data API v3. Skopiuj `.env.example` do `.env` i wpisz
wartość `YOUTUBE_API_KEY`. Plik `.env` zawiera sekret, więc go nie udostępniaj.

```bash
uv sync --locked
```

Pobieranie zużywa limit żądań API. Domyślny lokalny limit to 200 żądań na
uruchomienie; można go zmienić przez `--max-api-requests`. To ograniczenie
liczby żądań skryptu, nie informacja o limicie konta YouTube.

## 2. Znalezienie filmów i wybór źródeł komentarzy

```bash
uv run --locked python scripts/youtube/discover_videos.py
```

Skrypt zapisuje metadane kandydatów do `data/youtube/yt_videos_metadata.csv`.
Na tym etapie nie pobiera komentarzy. Domyślne sześć zapytań jest po polsku i
angielsku oraz dotyczy AI, pracy i kompetencji. Aby poszerzyć pulę o przypadki
związane, graniczne i niezwiązane z tematem, można podać własne zapytania:

```bash
uv run --locked python scripts/youtube/discover_videos.py \
  --query-pl "AI a praca tłumacza" \
  --query-pl "rynek pracy bezrobocie" \
  --query-en "AI tools review" \
  --max-api-requests 300
```

Podanie dowolnego własnego zapytania **zastępuje** cały zestaw domyślny.
`--query-pl` i `--query-en` to wskazówki językowe dla wyszukiwarki, nie twarde
filtry języka filmu lub komentarza. Odkrywanie domyślnie uwzględnia filmy
opublikowane po `2023-01-01T00:00:00Z`. Dla materiałów sprzed premiery ChatGPT
ustaw wcześniejszy próg, np. `--published-after 2022-01-01T00:00:00Z`.

Kandydatów należy przejrzeć przed pobraniem komentarzy. Konfiguracja
`config/youtube/approved_videos.json` zawiera wybrane `video_ids` oraz limit
komentarzy na film. `video_id` jest kluczem filmu: kolejne wyszukiwania i
uruchomienia nie dodają drugiego rekordu tego samego filmu. **Obecny eksport nie
zapisuje jednak informacji, które zapytanie znalazło dany film**. Jeśli ta
informacja jest potrzebna do doboru próby, należy ją prowadzić osobno.

## 3. Pobranie komentarzy

```bash
uv run --locked python scripts/youtube/collect_comments.py --max-api-requests 500
```

Skrypt czyta domyślnie `config/youtube/approved_videos.json`. Aktualna lista
zawiera 20 filmów i żąda maksymalnie 1000 komentarzy z każdego. Aby użyć innej
listy, podaj `--selection ścieżka/do/pliku.json`. Maksymalny obsługiwany limit
wynosi 5000 komentarzy na film. Jeśli dany film ma mniej dostępnych komentarzy,
pobranych będzie mniej. Liczba komentarzy w metadanych filmu może zawierać
odpowiedzi, których ten skrypt nie pobiera.

Domyślne `--comment-order relevance` pobiera strony w kolejności trafności API.
Można podać `--comment-order time`. Żadna z tych opcji nie tworzy losowej próby.
Przy ograniczeniu do pierwszych 1000 komentarzy wyniki mogą być zależne od
kolejności zwracanej przez YouTube.

Skrypt zapamiętuje, które próbki zostały ukończone. Ponowne uruchomienie bez
opcji `--refresh-comments` pomija ukończone filmy, nawet gdy w konfiguracji
zwiększono limit. Aby sięgnąć po dalsze strony komentarzy:

```bash
uv run --locked python scripts/youtube/collect_comments.py \
  --refresh-comments --max-api-requests 500
```

Już zapisane komentarze zachowują swoje lokalne ID. Usuwanie duplikatów opiera się na
`video_id`, oczyszczonym tekście i dacie publikacji; ten sam film nie jest
zapisywany drugi raz. Przy przerwaniu przez limit lub błąd API zapisane strony
pozostają w CSV, a następny przebieg może kontynuować pracę. Jeden błąd 403/429
zatrzymuje cały przebieg. Stan ukończenia jest w `yt_collection_state.csv`.

## 4. Pliki po pobraniu

| Plik | Zawartość i zastosowanie |
| --- | --- |
| `data/youtube/yt_videos_metadata.csv` | Jedna pozycja na `video_id`; tytuł, kanał, data publikacji filmu, statystyki. |
| `data/youtube/yt_comments_anonymized.csv` | Tekst, lokalne `comment_id`, `video_id`, data publikacji komentarza i liczba polubień. To główne wejście dla H1. |
| `data/youtube/yt_collection_state.csv` | Stan pobierania i limit dla poszczególnych filmów; zachowaj go przy przenoszeniu danych. |
| `data/youtube/yt_transcripts.csv` | Opcjonalne napisy; nie są potrzebne do klasyfikacji komentarzy. |

Pobieranie nie żąda nazw autorów ani oryginalnych ID komentarzy. Nazwa pliku
`anonymized` oznacza brak metadanych autora, lecz sam tekst może zawierać dane
osobowe. Przejrzyj go przed udostępnieniem poza zespołem.

## 5. Paczki dla małego modelu

Po zakończeniu lub wznowieniu pobierania przygotuj **nową, wersjonowaną** paczkę:

```bash
uv run --locked python scripts/youtube/prepare_screening.py \
  --output data/youtube/screening/v2
```

Katalog wynikowy nie może już istnieć; dzięki temu nie nadpisuje się raz
zamrożonej próby. Skrypt domyślnie tasuje wpisy z ziarnem `42` i tworzy jeden
obiekt JSON na linię w `batches.jsonl`. Każdy obiekt ma `batch_id` i tablicę
`comments` z polami `id` oraz `text`. Paczka ma najwyżej 100 komentarzy i
najwyżej 30 000 znaków tekstu; można zmienić to przez `--batch-size` (1–100)
i `--max-batch-chars`. Identyczne teksty z różnych komentarzy pozostają osobnymi
obserwacjami, bo H1 pyta o udział wypowiedzi.

`screening_config.json` zawiera instrukcję dla modelu, przykładowy format
odpowiedzi, hash pliku wejściowego i liczebności. Instrukcję należy przekazać
jako komunikat systemowy, a **jedną linię** `batches.jsonl` jako komunikat
użytkownika. Model powinien zwrócić jeden JSON z tym samym `batch_id` i po jednej
etykiecie na każde wejściowe `id`:

```json
{
  "batch_id": "b00001",
  "labels": [
    {
      "id": "c00000001",
      "h1_related": "yes",
      "job_security_concern": "yes"
    }
  ]
}
```

Przykład pokazuje schemat, a nie pełną odpowiedź dla rzeczywistej paczki.
Oba pola etykiety dopuszczają `yes`, `no` i `unclear`. Wynik trzeba sprawdzić:
zgodność `batch_id`, dokładnie jeden wynik na każde wejściowe `id`, dozwolone
wartości i zasadę `h1_related=no` → `job_security_concern=no`. Odpowiedzi
niekompletne lub błędne trzeba ponowić. Obecnie nie ma skryptu, który automatycznie
wyśle paczki do modelu lub wykona tę walidację.

`manifest.csv` pozwala połączyć krótkie ID z `comment_id`, `video_id`, datą
publikacji, okresem `pre`/`post` i hashem tekstu. Tych metadanych nie ma w
wiadomości dla modelu. Po dodaniu nowych komentarzy utwórz kolejny katalog,
ponieważ stary manifest odnosi się do starej wersji źródłowego CSV.

## 6. Co dalej z etykietami

Wyniki małego modelu mają służyć **wyborowi** przykładów dla dużego modelu,
nie być ostateczną odpowiedzią na H1. Planowany zbiór 5–10 tys. ocen powinien
zawierać wyraźnie związane, wyraźnie niezwiązane, niepewne oraz losowo wybrane
komentarze. Losowa część jest ważna, bo próba celowo wzbogacona w określone
klasy nie odzwierciedla ich częstości w całej kolekcji. Etykiety dużego modelu
również wymagają kontroli przez ludzi przed użyciem jako dane treningowe.

Na 26 października 2026 r. pobrano 4913 komentarzy i utworzono 50 paczek w
`data/youtube/screening/v1`. **Wszystkie te komentarze są z okresu po premierze
ChatGPT.** Sama obecna kolekcja nie pozwala przetestować wzrostu udziału obaw
przed i po listopadzie 2022 r. Do tego potrzeba komentarzy opublikowanych
przed premierą oraz porównywalnego sposobu doboru danych dla obu okresów.
Komentarze opisują wypowiedzi użytkowników YouTube; nie mierzą bezpośrednio
zmian zatrudnienia i same nie ustalają przyczyny tych zmian.

Szczegóły techniczne i ograniczenia doboru opisują [collector](youtube-collector.md),
[próbkowanie](comment-sampling.md) oraz [paczki H1](h1-screening.md).
