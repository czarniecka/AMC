# ADR 0001: Rezygnujemy z ogłoszeń KPRM (jobs)

Status: przyjęty, 2026-10-26.

## Kontekst

Hipoteza H2 mówi, że po 2023 roku ogłoszenia o pracę mają więcej wymagań kompetencyjnych, a wymagania cyfrowe i związane z AI pojawiają się częściej, zwłaszcza w zawodach bardziej narażonych na AI. Pilotaż opierał się na ogłoszeniach z nabory.kprm.gov.pl (rekrutacje w służbie cywilnej).

## Decyzja

Porzucamy dane z KPRM jako podstawę do testowania H2. Nie rozwijamy dalej kolektora ani analizy w `amc/jobs`.

## Powody

- **Sektor wolno adaptujący innowacje.** Administracja publiczna należy do sektorów, które wprowadzają zmiany technologiczne najwolniej i w najmniejszym stopniu. Wymagania w ogłoszeniach z tego sektora odzwierciedlają więc raczej utrwalone praktyki formalne niż bieżące zmiany na rynku pracy, co obniża trafność wnioskowania o wpływie AI.
- **Ogłoszenia pozorowane.** W sektorze publicznym występuje zjawisko tzw. ogłoszeń widmo: procedura wymaga publikacji ogłoszenia, choć obsada stanowiska bywa rozstrzygnięta nieformalnie, np. przez znajomości. Treść takich ogłoszeń nie musi odpowiadać faktycznemu popytowi na kompetencje, co wprowadza trudny do oszacowania szum pomiarowy.
- **Niszowy charakter wymagań związanych z AI.** Wymagania informatyczne w analizowanych ogłoszeniach sprowadzają się głównie do obsługi pakietu biurowego (np. edytora tekstu). Wymagania dotyczące AI występują marginalnie, więc zbyt rzadko, by wykryć ich zmianę w czasie.

## Alternatywa

Opieramy się na wypowiedziach użytkowników z Wykopu i komentarzach z YouTube'a. Źródła te lepiej niż ogłoszenia KPRM oddają to, jak AI jest postrzegane na rynku pracy, i obejmują dyskusje z różnych branż, także tych szybko adaptujących nowe technologie. Kwestię zmiany wymaganych kompetencji badamy w tych danych etykietą `competence_claim`.

## Konsekwencje

- H2 badamy w ujęciu percepcji: zapisujemy, co autorzy twierdzą o zmianie wymagań, a nie faktyczne wymagania w ogłoszeniach. Hipotezę trzeba sformułować odpowiednio.
- Kod i dane z KPRM zostają w historii repozytorium, ale nie są częścią dalszej analizy.
- H1 (dyskusje z Wykopu i YouTube'a) nie zależy od tej decyzji.
