# Wytyczne anotacji: AI a praca (Wykop)

Oceniasz **pojedynczy tekst** (wpis lub komentarz) trzema etykietami: `ai`, `work`, `stance`.

To pierwsza, wstępna analiza: służy do przesiania tekstów niezwiązanych z AI. Pogłębiona anotacja będzie osobnym etapem, już na przefiltrowanym zbiorze.

## Zasady ogólne

- Oceniasz tylko to, co autor napisał. Nie domyślaj się niewyrażonych opinii.
- Hashtagi (#ai, #programista15k), linki i same tagi nie są dowodem.
- Obrazy, filmy i linki: model ich nie widzi, więc Ty też nie. Oceniasz tylko słowa autora, a załącznik pomijasz. Wpis z samym linkiem lub obrazem, bez słów o AI i pracy, to `ai` no, `work` no, `stance` none.
- Model widzi tylko treść tekstu, więc Ty też oceniasz wyłącznie ją, bez zaglądania do wpisu nadrzędnego, linku czy tytułu.
- Wątpliwości: wybierz najbezpieczniejszą etykietę (`no` / `none`).
- Kolejność: `ai`, potem `work`, potem `stance`. Jeśli `ai` = no lub `work` = no, to `stance` = none.

## `ai`: yes / no

- **yes**: ChatGPT, GPT, Claude, Gemini, Copilot, Midjourney, LLM, "sztuczna inteligencja", AI/SI, boty AI, generatywna AI, automatyzacja zadań takimi narzędziami.
- **no**: zwykłe oprogramowanie, skrypty, Excel, roboty przemysłowe bez wzmianki o AI, "algorytm" w ogólnym sensie (chyba że autor mówi wprost o AI), same hashtagi, nazwa narzędzia w innym znaczeniu (imię Claude).
- Samo "automatyzacja" lub "wdrożenie narzędzi" bez nazwania AI: **no**.
- "Wygenerował", "wygenerowałem", "generator" przy treści (tekst, list, obraz, kod) oznacza użycie AI, więc **yes**, nawet bez nazwy narzędzia (np. "zabawne, że mi ten list wygenerował jako kobieta").

## `work`: yes / no

- **yes**: praca, kariera, rekrutacja, zwolnienia, zarobki, rynek pracy, umiejętności zawodowe, konkretny zawód lub branża w kontekście zatrudnienia.
- **no**: sprzęt, oprogramowanie, hobby, nauka, rozrywka, chyba że pada wątek zawodowy.

## `stance`: skutki AI dla pracy

Tylko gdy autor wyraźnie łączy AI z pracą.

| Etykieta | Kiedy |
| --- | --- |
| `threat` | AI odbierze pracę, ograniczy zatrudnianie (też juniorów), obniży zarobki, zdezaktualizuje zawód; strach, rezygnacja, rada zmiany zawodu. Także ironicznie. |
| `reassurance` | Prace są bezpieczne, strach przesadzony, AI za słabe, by zastąpić ludzi. |
| `opportunity` | AI pomaga pracownikom: produktywność, nowe zawody, wyższe zarobki, przewaga w karierze. |
| `mixed` | Jednocześnie zagrożenie i szansa lub uspokojenie. |
| `none` | Brak opinii o skutkach AI dla pracy. |

Co jest `none`:

- wypalenie, zarobki, szukanie pracy bez wzmianki o AI,
- newsy o produktach i cenach AI,
- tekst wygenerowany przez AI i wklejony bez komentarza (to nie jest pogląd autora),
- samo wklejenie nagłówka newsa (liczy się tylko, gdy autor się zgadza lub reaguje),
- samo "używam ChatGPT w pracy" bez oceny; "AI pomaga mi w pracy" to już `opportunity`.

## Specyfika Wykopu

- Slang, skróty i ironia są częste ("kryzysit", "januszex", "15k", "rip programiści"). Ironiczny strach to nadal `threat`.
- Wpis z samym linkiem lub zdjęciem, bez własnej treści: `ai` no, `work` no, `stance` none.
- Oceniasz tekst autora wpisu, nie nagłówek linkowanego artykułu. Wyjątek: tytuł znaleziska napisał sam autor.
- Wpisy Mirko Anonim mają nagłówek i stopkę dodane przez bota (np. link `#wsparcie-ai`). Model ich nie widzi, więc je pomiń i oceniaj tylko słowa autora.

## Rozstrzyganie wątpliwości

1. Brak jasnego związku AI z pracą: `none`.
2. Niepewność, czy tekst jest o AI: `no`.
3. Dwie sprzeczne perspektywy: `mixed`.
4. Pytanie retoryczne bez odpowiedzi autora: `none`; jeśli ton wyraźnie wyraża obawę: `threat`.
5. Opis cudzych obaw bez oceny autora: `none`; jeśli autor je potwierdza: odpowiednia etykieta.
6. Zawsze sprawdź, czyj to pogląd: autora czy cytowanej osoby.

## Kontrola jakości

Cały zbiór anotuje i filtruje (odrzuca teksty niezwiązane z AI) mały model (Qwen3 8B), więc najpierw sprawdzamy go na próbce ludzkiej. 150 tekstów zostało zanotowanych przez dwie osoby, a spory rozstrzyga osoba trzecia. Etykiety ludzi są wzorcem, z którym porównujemy etykiety modelu, zwłaszcza `ai` i `work`, bo to one decydują, które teksty zostają w zbiorze.

## Format

Dla każdego tekstu: `ai` (yes/no), `work` (yes/no), `stance` (threat/reassurance/opportunity/mixed/none).
