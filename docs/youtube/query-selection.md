# Dobór fraz wyszukiwania YouTube (testy z października 2026)

Cel: wybrać frazy do `config/youtube/work_queries.txt`, które dają filmy związane z pracą, z dużą liczbą komentarzy i z mierzalnym udziałem komentarzy o AI po premierze ChatGPT, bez słów o AI w samych frazach.

## Metoda

- Jedno wyszukiwanie na frazę i okno: III kwartał 2021 (przed) i III kwartał 2024 (po), sortowanie po trafności, losowo 10 filmów z 50 wyników.
- Filtry jak w kolektorze: minimum 10 tys. wyświetleń, język angielski, od tury 3 także minimum 50 komentarzy. Daty publikacji filmów zweryfikowano osobno (po jednym błędzie w oknie przed 2022 wszystkie filmy z okna po 2022 okazały się w oknie).
- Dla filmów, które przeszły filtry, pobrano jedną stronę (do 100) najnowszych komentarzy z maksymalnie 3 filmów. Odsetek wzmianek o AI liczono listą słów: `AI`, `ChatGPT`, `GPT`, `LLM`, `Copilot`, `artificial intelligence`, `machine learning`.
- Tytuły filmów oceniano ręcznie pod kątem związku z pracą.

## Wybrane frazy (9)

| Fraza | Komentarze o AI, po 2022 | Przed 2022 | Uwagi |
| --- | --- | --- | --- |
| `will robots take our jobs` | 47/161 (29%) | 9/89 (10%) | filmy na temat |
| `jobs that will disappear` | 67/300 (22%) | 5/75 (7%) | jeden film nie na temat |
| `automation unemployment` | 37/100 (37%) | 1/62 (2%) | tylko 1 film przeszedł filtry |
| `is computer science still worth it` | 30/236 (13%) | 0/60 | na temat |
| `junior developer jobs` | 41/279 (15%)\* | brak filmów w III 2021 | |
| `software engineer jobs` | 30/255 (12%)\* | | |
| `data analyst jobs` | 23/240 (10%)\* | | |
| `how to get a job` | 11/279 (4%)\* | | tło, dużo komentarzy |
| `entry level jobs` | nie mierzono | | tło, 6 z 10 filmów przechodzi filtry |

\* Lista słów w turach 2-3 była szersza (zawierała „automat”, „robot”), więc wartości są lekko zawyżone.

## Odrzucone frazy

| Powód | Frazy |
| --- | --- |
| Webinary i filmy korporacyjne, prawie bez komentarzy | `workplace automation`, `future of work`, `workplace changes`, `job security` (wyciąga strażników i bezpieczeństwo lotnisk) |
| Mało filmów po filtrach lub 0 | `paralegal jobs`, `content writer jobs`, `call center jobs`, `voice actor jobs`, `junior developer layoffs`, `jobs at risk of automation`, `will programmers be replaced` |
| Szum i rozrywka | `unemployed`, `careers to avoid`, `what career should I choose`, `white collar jobs disappearing`, `bootcamp graduates can't find jobs`, `best jobs for the future`, `tech layoffs` |
| Prawie brak komentarzy o AI (do 1,5%) | `career change`, `laid off`, `customer service jobs`, `graphic designer jobs`, `truck driver jobs`, `self driving trucks jobs`, `accountant jobs`, `bookkeeping jobs`, `software engineer layoffs`, `tech job market` |
| Te same filmy co frazy wybrane (nic nowego) | `jobs automation will replace`, `most in demand jobs`, `dying careers`, `is programming a dying career`, `factory automation jobs` |

## Do sprawdzenia, jeśli będzie potrzeba

Frazy z wysokim odsetkiem AI po 2022, ale bez sprawdzonego okresu przed 2022 w wielu kwartałach: `is software engineering dead` (16%), `jobs of the future` (33%), `safe jobs from automation` (32%), `universal basic income` (11%), `learn to code still worth it` (8%). W III 2021 nie dały filmów po filtrach, co dla jednego kwartału nie rozstrzyga.

## Ograniczenia

- Jedno okno kwartalne na okres, 3 filmy i jedna strona komentarzy na frazę: odsetki są orientacyjne.
- Lista słów jest przybliżona (nie jest klasyfikatorem AI i może łapać słowa w innym znaczeniu).
- Frazy o „przyszłości pracy” z założenia wybierają filmy o obawach, więc odsetek obaw w próbce będzie wysoki w obu okresach. Porównanie przed i po dotyczy zmiany udziału AI w tej samej dyskusji, a nie ogólnego wzrostu obaw. Frazy tła (`entry level jobs`, `how to get a job`) mają to równoważyć.
- Frazy sprawdzono tylko w jednym kwartale na okres. Są dość specyficzne i część z nich odpowiada tematom z lat 2023-2025 (`is computer science still worth it`, `jobs that will disappear`), więc w okresie przed 2022 mogą dawać inne filmy albo ich brak (w III 2021 `junior developer jobs` dało 0 filmów po filtrach). Różny skład fraz w obu okresach mógłby zakłócić porównanie, dlatego trzeba sprawdzić wydajność fraz w kilku kwartałach każdego okresu i analizować wyniki w obrębie fraz.
- Wybór sprzyja zawodom IT, więc `sector` będzie głównie `it`.
- Skrypty sondujące nie są w repozytorium.

## Szacowany wolumen

Około 800 filmów po filtrach i 120-500 tys. komentarzy po filtrach języka i długości, przy kosztach rzędu 30-40 tys. jednostek API (3-4 dni limitu). Domyślny cel 10 000 komentarzy mieści się w jednym dniu.
