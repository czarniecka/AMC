# Wytyczne anotacji: AI a praca (Wykop)

Oceniasz **pojedynczy tekst** (wpis lub komentarz) dwiema etykietami: `ai` i `work`.

To pierwsza, wstępna analiza: służy do przesiania tekstów niezwiązanych z AI i pracą. Ocena tego, co autor mówi o skutkach AI dla pracy, oraz pogłębiona anotacja będą osobnym etapem, już na przefiltrowanym zbiorze.

## Zasady ogólne

- Oceniasz tylko to, co autor napisał. Nie domyślaj się niewyrażonych opinii.
- Hashtagi (#ai, #programista15k), linki i same tagi nie są dowodem. Wyjątek: hashtag użyty jako słowo w zdaniu (np. podmiot) czytasz jak zwykłe słowo, patrz `ai`.
- Obrazy, filmy i linki: model ich nie widzi, więc Ty też nie. Oceniasz tylko słowa autora, a załącznik pomijasz. Wpis z samym linkiem lub obrazem, bez słów o AI i pracy, to `ai` no, `work` no.
- Model widzi tylko treść tekstu, więc Ty też oceniasz wyłącznie ją, bez zaglądania do wpisu nadrzędnego, linku czy tytułu.
- Wątpliwości rozstrzygaj najbezpieczniej: `no`.
- `ai` i `work` oceniasz niezależnie: tekst może być o AI bez pracy, o pracy bez AI, o obu albo o żadnym.

## `ai`: yes / no

- **yes**: ChatGPT, GPT, Claude, Gemini, Copilot, Midjourney, LLM, "sztuczna inteligencja", AI/SI, boty AI, generatywna AI, automatyzacja zadań takimi narzędziami.
- **no**: zwykłe oprogramowanie, skrypty, Excel, roboty przemysłowe bez wzmianki o AI, "algorytm" w ogólnym sensie (chyba że autor mówi wprost o AI), same hashtagi, nazwa narzędzia w innym znaczeniu (imię Claude).
- Samo "automatyzacja" lub "wdrożenie narzędzi" bez nazwania AI: **no**.
- "Wygenerował", "wygenerowałem", "generator" przy treści (tekst, list, obraz, kod) oznacza użycie AI, więc **yes**, nawet bez nazwy narzędzia (np. "zabawne, że mi ten list wygenerował jako kobieta").
- "Bot" albo "czat" to **yes**, jeśli z tekstu wynika, że chodzi o model AI (np. "Czy mnie bot ściemnia" przy rozmowie z ChatGPT).
- Hashtag, który jest częścią zdania, to słowo, nie tag: "#chatgpt nie chce mi powiedzieć, co zrobić z plagą myszy" to **yes** (hashtag jest podmiotem). Same tagi to **no**: "Tak to ja nie chce #chatgpt", "#sztucznainteligencja #chatgpt #ai".

## `work`: yes / no

- **yes**: praca, kariera, rekrutacja, zwolnienia, zarobki, rynek pracy, umiejętności zawodowe, konkretny zawód lub branża w kontekście zatrudnienia.
- **no**: sprzęt, oprogramowanie, hobby, nauka, rozrywka, chyba że pada wątek zawodowy.
- Tekst musi być **o pracy** (zatrudnienie, warunki, zarobki, kariera, rekrutacja, wykonywanie zadań zawodowych). Praca tylko jako tło lub miejsce akcji to **no** (np. wybór hulajnogi na dojazd do pracy, "czytam to na przerwie w robocie", wpis o związku, którego autor przy okazji jest programistą).
- Szukanie pracy to **yes**: CV (także problem z wysłaniem CV), portfolio pod rekrutację, oferta pracy, negocjacje.

## Specyfika Wykopu

- Slang, skróty i ironia są częste ("kryzysit", "januszex", "15k", "rip programiści").
- Wpis z samym linkiem lub zdjęciem, bez własnej treści: `ai` no, `work` no.
- Oceniasz tekst autora wpisu, nie nagłówek linkowanego artykułu. Wyjątek: tytuł znaleziska napisał sam autor.
- Wpisy Mirko Anonim mają nagłówek i stopkę dodane przez bota (np. link `#wsparcie-ai`). Model ich nie widzi, więc je pomiń i oceniaj tylko słowa autora.

## Rozstrzyganie wątpliwości

- Niepewność, czy tekst jest o AI: `no`.
- Niepewność, czy tekst jest o pracy: `no`.

## Kontrola jakości

Cały zbiór anotuje i filtruje (odrzuca teksty niezwiązane z AI) mały model (Qwen3 8B), więc najpierw sprawdzamy go na próbce ludzkiej. 150 tekstów zostało zanotowanych przez dwie osoby, a spory rozstrzyga osoba trzecia. Etykiety ludzi są wzorcem, z którym porównujemy etykiety modelu, zwłaszcza `ai` i `work`, bo to one decydują, które teksty zostają w zbiorze.

## Format

Dla każdego tekstu: `ai` (yes/no), `work` (yes/no).
