# Wytyczne anotacji, etap 2: rodzaj obawy i branża (Wykop)

Pogłębiona anotacja po pierwszej analizie ([etap 1](annotation-guidelines.md)). Oceniasz tylko teksty, które w etapie 1 mają `ai` = yes i `work` = yes. Zasady ogólne (oceniasz tylko to, co autor napisał, hashtagi nie są dowodem, wątpliwości rozstrzygasz najbezpieczniejszą etykietą) są takie same jak w etapie 1. Widzisz tylko treść tekstu.

Etykiety etapu 1 (`ai`, `work`, `stance`) są już ustalone. Tutaj dodajesz `threat_type` i `sector`.

## `threat_type`: rodzaj obawy

Tylko gdy `stance` to `threat` albo `mixed`. W pozostałych przypadkach pole zostaje puste.

| Wartość | Kiedy |
| --- | --- |
| `job_loss` | AI zabierze komuś pracę, zwolnienia, likwidacja stanowisk |
| `hiring` | trudniej znaleźć pracę lub wejść na rynek, np. mniej ofert dla juniorów |
| `pay` | niższe zarobki lub stawki |
| `skills` | umiejętności lub zawód się zdezaktualizują |
| `other` | inna obawa o pracę, której nie obejmują powyższe |

Jeśli tekst zawiera kilka obaw, wybierz tę, którą autor akcentuje najmocniej, a przy równorzędnych tę, która pojawia się pierwsza.

## `sector`: branża lub zawód, o który chodzi

Dla każdego tekstu z `ai` = yes i `work` = yes, także gdy `stance` to `opportunity`, `reassurance` albo `none`.

| Wartość | Kiedy |
| --- | --- |
| `it` | programowanie, IT, testowanie, administracja systemami |
| `creative` | grafika, ilustracja, teksty, tłumaczenia, muzyka, film |
| `office` | praca biurowa, administracja, księgowość, urzędy |
| `service` | obsługa klienta, sprzedaż, call center |
| `education` | nauczanie, szkolnictwo, nauka |
| `other` | inna wskazana branża lub zawód |
| `unspecified` | autor nie wskazuje branży ani zawodu, mówi ogólnie o rynku pracy |

Oceniasz to, co autor napisał o branży. Jeśli autor wymienia kilka branż, wybierz tę, której dotyczy główna myśl tekstu.

## Format

Dla każdego tekstu: `threat_type` (job_loss/hiring/pay/skills/other albo puste) i `sector` (it/creative/office/service/education/other/unspecified).
