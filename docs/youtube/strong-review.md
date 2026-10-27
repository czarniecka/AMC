# Mocniejsza anotacja komentarzy YouTube

## Szybki start

1. Otwórz `strong_review_8k_v3/prompts/review_0001.md` i przekaż **cały** plik
   wybranemu mocniejszemu modelowi. Każdy z 200 plików zawiera instrukcję oraz
   40 komentarzy; pliki wykonuj niezależnie.
2. Zapisz odpowiedź jako czysty JSON w
   `strong_review_8k_v3/responses/review_0001.json`. Zachowaj nazwę pliku i
   `batch_id`; analogicznie postępuj dla następnych promptów.
3. Wczytaj zapisane odpowiedzi do SQLite:

   ```bash
   uv run --locked python scripts/youtube/import_strong_review.py \
     --review-dir data/youtube/screening/work_v3_50k_stage1_v1/strong_review_8k_v3 \
     --model NAZWA_MODELU
   ```

Import można powtarzać po każdym ukończonym pliku. Skrypt nie wysyła żadnych
zapytań do modelu.

## Zamrożona próba

`scripts/youtube/prepare_strong_review.py` łączy przygotowane komentarze,
`manifest.csv` i trzy katalogi wyników Luny w osobnej bazie SQLite.
Sprawdza identyfikatory, hash tekstu, brak duplikatów i kompletność każdej
odpowiedzi. Nie wywołuje modelu i nie zmienia bazy zebranych komentarzy.

Obecny eksport znajduje się w
`data/youtube/screening/work_v3_50k_stage1_v1/strong_review_8k_v3/`.
Wersja v1 pozostaje archiwum pierwszego doboru; zawierała za mało komentarzy
`ai=yes, work=no`. V2 ma ten sam dobór co v3, ale prompt zawierał niepotrzebne
fragmenty metodologii Wykopu. Do anotacji używamy v3.
Powstał z 50 000 komentarzy, z których 49 800 ma poprawną etykietę Luny.
Dwie brakujące grupy (200 komentarzy) pozostają w `comments` bez wpisu w
`stage1_luna` i nie weszły do tej wersji próby. Po ich uzupełnieniu można
utworzyć *nową* wersję próby, bez nadpisywania v3.

Próba 8 000 obejmuje pięć rozłącznych pul według **wstępnej** etykiety Luny:

| Pula | Wybór | Liczba w v3 |
| --- | --- | ---: |
| `ai_work_concern` | `ai=yes`, `work=yes`, `stance=threat/mixed` | 1 029 (wszystkie) |
| `ai_work_other` | pozostałe `ai=yes`, `work=yes` | 975 (wszystkie) |
| `ai_only` | `ai=yes`, `work=no` | 1 594 (wszystkie) |
| `work_no_ai` | `ai=no`, `work=yes` | 2 935 (losowo, prawie po połowie pre/post) |
| `unrelated` | `ai=no`, `work=no` | 1 467 (losowo, prawie po połowie pre/post) |

To jest próba wzbogacona na potrzeby trenowania, nie reprezentatywna próba do
prostego liczenia częstości H1. `review_sample.inclusion_probability` zachowuje
prawdopodobieństwo doboru w puli i okresie. Jeśli będziemy estymować udział
obaw w populacji pobranych komentarzy, trzeba uwzględnić ten dobór oraz błędy
pierwszego pasa. Okres `pre/post` jest zapisany w bazie, ale ukryty przed modelem.

Polecenie odtwarzające eksport (wymaga nowego `--output`):

```bash
uv run --locked python scripts/youtube/prepare_strong_review.py \
  --source data/youtube/screening/work_v3_50k_stage1_v1 \
  --output data/youtube/screening/work_v3_50k_stage1_v1/strong_review_8k_v4 \
  --target 8000 --seed 20261027 --batch-size 40 --allow-incomplete
```

Bez `--allow-incomplete` skrypt wymaga etykiet Luny dla całych 50 000.

## Pliki do mocniejszego modelu

`prompts/review_0001.md` do `prompts/review_0200.md` zawierają samodzielną
instrukcję i po 40 komentarzy. Jeden plik jest jednym zadaniem. Otwórz plik,
przekaż jego **całą** zawartość wybranemu modelowi i zapisz wyłącznie zwrócony
obiekt JSON pod tą samą nazwą w `responses/`, np.
`responses/review_0001.json`. Katalog `responses/` jest na razie pusty.
Nie przekazuj modelowi `annotations.sqlite3` ani `manifest.json`: zawierają
daty, etykiety Luny i pochodzenie komentarzy, które mogłyby sugerować ocenę.

Model ocenia `ai`, `work` i `stance` niezależnie od Luny. Dla każdego `work=yes`
dodaje `job_insecurity=yes/no`, również przy `ai=no`. Dla własnych wyników
`ai=yes` i `work=yes` dodaje `attitude`, `threat_type`, `competence_claim` i
`sector`; w innych przypadkach pola etapu 2 to JSON `null`.

Fragment poprawnego formatu odpowiedzi (rzeczywisty plik musi zawierać
**wszystkie** ID z danego promptu, w tej samej kolejności):

```json
{
  "batch_id": "review_0001",
  "labels": [
    {
      "id": "c00000001",
      "ai": "no",
      "work": "yes",
      "stance": "none",
      "job_insecurity": "yes",
      "attitude": null,
      "threat_type": null,
      "competence_claim": null,
      "sector": null
    }
  ]
}
```

Po zapisaniu odpowiedzi uruchom import lokalny:

```bash
uv run --locked python scripts/youtube/import_strong_review.py \
  --review-dir data/youtube/screening/work_v3_50k_stage1_v1/strong_review_8k_v3 \
  --model NAZWA_MODELU
```

Importer sprawdza kompletność i kolejność ID, dozwolone etykiety, reguły pól
warunkowych oraz zgodność promptu z zamrożoną instrukcją. Zapisuje etap 1 i
etap 2 w osobnych tabelach, bez nadpisywania Luny. Można uruchamiać go po
każdym ukończonym pliku; ponowny import tych samych etykiet jest bezpieczny,
zmiana wcześniej zaimportowanej odpowiedzi powoduje błąd. Pliki `responses/`
pozostają surowym śladem odpowiedzi modelu.

Przed treningiem klasyfikatora trzeba jeszcze ręcznie przejrzeć próbę z obu
okresów i rozbieżności między Luną a mocniejszym modelem. Podział trening/test
powinien grupować komentarze według `video_id`.
