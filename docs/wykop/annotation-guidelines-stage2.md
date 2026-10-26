# Wytyczne anotacji, etap 2: skutki AI dla pracy, nastawienie, rodzaj obawy, kompetencje i branża (Wykop)

Pogłębiona anotacja po pierwszej analizie ([etap 1](annotation-guidelines.md)). Oceniasz tylko teksty, które w etapie 1 mają `ai` = yes i `work` = yes. Zasady ogólne (oceniasz tylko to, co autor napisał, hashtagi nie są dowodem, wątpliwości rozstrzygasz najbezpieczniejszą etykietą) są takie same jak w etapie 1. Widzisz tylko treść tekstu.

Etykiety etapu 1 (`ai`, `work`) są już ustalone. Tutaj dodajesz, w tej kolejności: `stance`, `attitude`, `threat_type`, `competence_claim` i `sector`.

## `stance`: skutki AI dla pracy

Dla każdego tekstu z `ai` = yes i `work` = yes. Mówi, co autor twierdzi, że AI oznacza dla pracy. Etykietę inną niż `none` dajesz tylko wtedy, gdy autor wyraźnie łączy AI z pracą.

| Wartość       | Kiedy                                                                                                                                             |
| ------------- | ------------------------------------------------------------------------------------------------------------------------------------------------- |
| `threat`      | AI odbierze pracę, ograniczy zatrudnianie (też juniorów), obniży zarobki, zdezaktualizuje zawód; strach, rezygnacja, rada zmiany zawodu. Także ironicznie. |
| `reassurance` | prace są bezpieczne, strach przesadzony, AI za słabe, by zastąpić ludzi                                                                           |
| `opportunity` | AI pomaga pracownikom: produktywność, nowe zawody, wyższe zarobki, przewaga w karierze                                                            |
| `mixed`       | jednocześnie zagrożenie i szansa lub uspokojenie                                                                                                  |
| `none`        | brak opinii o skutkach AI dla pracy                                                                                                               |

Co jest `none`:

- wypalenie, zarobki, szukanie pracy bez związku z AI (etap 1 mógł przepuścić taki tekst),
- newsy o produktach i cenach AI,
- tekst wygenerowany przez AI i wklejony bez komentarza (to nie jest pogląd autora),
- samo wklejenie nagłówka newsa (liczy się tylko, gdy autor się zgadza lub reaguje),
- samo "używam ChatGPT w pracy" bez oceny; "AI pomaga mi w pracy" to już `opportunity`.

Rozstrzyganie wątpliwości przy `stance`:

1. Brak jasnego związku AI z pracą: `none`.
2. Dwie sprzeczne perspektywy: `mixed`.
3. Pytanie retoryczne bez odpowiedzi autora: `none`; jeśli ton wyraźnie wyraża obawę: `threat`.
4. Opis cudzych obaw bez oceny autora: `none`; jeśli autor je potwierdza: odpowiednia etykieta.
5. Zawsze sprawdź, czyj to pogląd: autora czy cytowanej osoby.

Na Wykopie ironia jest częsta ("kryzysit", "rip programiści"). Ironiczny strach to nadal `threat`.

## `attitude`: nastawienie do AI na rynku pracy

Dla każdego tekstu z `ai` = yes i `work` = yes. `stance` mówi, co AI oznacza dla pracy, a `attitude` ocenia nastawienie autora do obecności AI na rynku pracy: czy wyraża się o niej dobrze, czy źle.

| Wartość    | Kiedy                                                                                          |
| ---------- | ---------------------------------------------------------------------------------------------- |
| `positive` | AI na rynku pracy oceniane dobrze: pomocne, przydatne, budzi entuzjazm lub nadzieję            |
| `negative` | AI na rynku pracy oceniane źle: groźne, szkodliwe, bezwartościowe, budzi lęk, złość lub drwinę |
| `mixed`    | w tekście są jednocześnie pozytywne i negatywne oceny                                          |
| `neutral`  | autor opisuje lub komentuje AI na rynku pracy bez oceny                                        |

Ocena nie zawsze pokrywa się ze `stance`: ktoś może obawiać się utraty pracy (`threat`), a mimo to dobrze oceniać obecność AI na rynku pracy (`positive`). Ironię oceniasz według zamierzonego sensu.

## `threat_type`: rodzaj obawy

Tylko gdy `stance` to `threat` albo `mixed`. W pozostałych przypadkach pole zostaje puste.

| Wartość    | Kiedy                                                                   |
| ---------- | ----------------------------------------------------------------------- |
| `job_loss` | AI zabierze komuś pracę, zwolnienia, likwidacja stanowisk               |
| `hiring`   | trudniej znaleźć pracę lub wejść na rynek, np. mniej ofert dla juniorów |
| `pay`      | niższe zarobki lub stawki                                               |
| `skills`   | umiejętności lub zawód się zdezaktualizują                              |
| `other`    | inna obawa o pracę, której nie obejmują powyższe                        |

Jeśli tekst zawiera kilka obaw, wybierz tę, którą autor akcentuje najmocniej, a przy równorzędnych tę, która pojawia się pierwsza.

## `competence_claim`: czy AI zmienia wymagane kompetencje

Dla każdego tekstu z `ai` = yes i `work` = yes. Zapisuje, **co autor twierdzi** o wymaganiach wobec pracowników, a nie to, jak jest w rzeczywistości.

| Wartość     | Kiedy                                                                                           |
| ----------- | ----------------------------------------------------------------------------------------------- |
| `more`      | AI wymaga nowych lub dodatkowych umiejętności ("trzeba umieć obsługiwać AI", "wymagania rosną") |
| `fewer`     | AI zmniejsza wymagania lub zastępuje umiejętności ("nie trzeba już umieć kodować")              |
| `unchanged` | autor wprost twierdzi, że wymagania się nie zmieniają                                           |
| `none`      | autor nie mówi o kompetencjach lub umiejętnościach                                              |

Jeśli autor twierdzi jedno i drugie, wybierz to, co akcentuje mocniej. Samo "używam AI w pracy" bez wniosku o wymaganiach to `none`.

## `sector`: branża lub zawód, o który chodzi

Dla każdego tekstu z `ai` = yes i `work` = yes, także gdy `stance` to `opportunity`, `reassurance` albo `none`.

| Wartość       | Kiedy                                                            |
| ------------- | ---------------------------------------------------------------- |
| `it`          | programowanie, IT, testowanie, administracja systemami           |
| `creative`    | grafika, ilustracja, teksty, tłumaczenia, muzyka, film           |
| `office`      | praca biurowa, administracja, księgowość, urzędy                 |
| `service`     | obsługa klienta, sprzedaż, call center                           |
| `education`   | nauczanie, szkolnictwo, nauka                                    |
| `other`       | inna wskazana branża lub zawód                                   |
| `unspecified` | autor nie wskazuje branży ani zawodu, mówi ogólnie o rynku pracy |

Oceniasz to, co autor napisał o branży. Jeśli autor wymienia kilka branż, wybierz tę, której dotyczy główna myśl tekstu.

## Format

Dla każdego tekstu, w tej kolejności: `stance` (threat/reassurance/opportunity/mixed/none), `attitude` (positive/negative/mixed/neutral), `threat_type` (job_loss/hiring/pay/skills/other albo puste), `competence_claim` (more/fewer/unchanged/none) i `sector` (it/creative/office/service/education/other/unspecified).
