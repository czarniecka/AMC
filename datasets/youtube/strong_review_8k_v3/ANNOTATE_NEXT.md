# Zadanie dla modelu z dostępem do plików repozytorium

Pracuj w katalogu głównym repozytorium. Wykonaj poniższe kroki samodzielnie;
użytkownik nie musi wklejać treści komentarzy do rozmowy.

1. Przeczytaj **cały** plik
   `datasets/youtube/strong_review_8k_v3/instructions.md`. To obowiązujący
   schemat i zasady anotacji.
2. Jeśli użytkownik podał numer batcha albo zakres, użyj tych plików. W innym
   przypadku wybierz pierwszy plik `batches/review_XXXX.json`, który nie ma
   odpowiednika w `responses/`. Rozpatruj każdy batch osobno.
3. Przeczytaj wybrany plik JSON. Skopiuj jego `batch_id` do odpowiedzi. Dla
   każdego obiektu z `comments` skopiuj `id`, zachowując kolejność, i uzupełnij
   pola `ai`, `work`, `stance`, `job_insecurity`, `attitude`, `threat_type`,
   `competence_claim`, `sector` według `instructions.md`. Oceniaj wyłącznie
   `text` bieżącego komentarza. Nie korzystaj z nazw plików, innych batchy,
   wyników Luny ani metadanych do odgadywania etykiet.
4. Zapisz **sam obiekt JSON**, bez Markdownu, w
   `datasets/youtube/strong_review_8k_v3/responses/review_XXXX.json` pod
   tym samym numerem co wejście. Struktura odpowiedzi to
   `{ "batch_id": "review_XXXX", "labels": [ ... ] }` — nie kopiuj tekstów
   komentarzy do `labels` i nie modyfikuj pliku wejściowego.
5. Zweryfikuj zapisany plik:

   ```bash
   uv run --locked python scripts/youtube/validate_strong_review_json.py \
     --batch datasets/youtube/strong_review_8k_v3/batches/review_XXXX.json \
     --response datasets/youtube/strong_review_8k_v3/responses/review_XXXX.json
   ```

   Jeśli walidacja nie przejdzie, popraw odpowiedź i uruchom ją ponownie.
   Na koniec zgłoś liczbę ukończonych batchy i błędy, jeśli wystąpiły.

Nie uruchamiaj płatnego API ani nie trenuj klasyfikatora. Jeden batch zawiera
40 komentarzy; przy dużym zakresie zapisuj i waliduj każdą odpowiedź osobno,
zamiast trzymać wszystkie odpowiedzi w kontekście rozmowy.
