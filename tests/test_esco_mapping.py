"""Offline tests for the ESCO embedding index, review sheet and threshold calibration."""

import csv
import tempfile
import unittest
import zlib
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np

from amc.esco import index as index_module
from amc.esco.calibration import best_threshold, threshold_table
from amc.esco.embedder import OllamaEmbedder, normalize
from amc.esco.index import Match, build_index, entries_of, load_index
from amc.esco.review import read_verdicts, write_review

HEADER = ["uri", "preferred_label", "alt_labels", "description", "group_code"]
SKILLS = [
    ["u/1", "pracować w zespole", "współpracować z zespołem | praca zespołowa", "Opis 1", "S1.1"],
    ["u/2", "obsługiwać komputer", "", "Opis 2", "S5.1"],
    ["u/3", "prowadzić księgowość", "", "Opis 3", "S4.2"],
]


class FakeEmbedder:
    """Hashed character trigrams: similar strings get similar vectors."""

    name = "fake"

    def __init__(self):
        self.calls = 0

    def embed(self, texts):
        self.calls += 1
        matrix = np.zeros((len(texts), 64), dtype=np.float32)
        for row, text in enumerate(texts):
            padded = f"  {text.lower()}  "
            for i in range(len(padded) - 2):
                matrix[row, zlib.crc32(padded[i : i + 3].encode()) % 64] += 1
        return normalize(matrix)


def write_skills(directory: Path) -> Path:
    path = directory / "esco_skills_pl.csv"
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(
            ["uri", "preferred_label", "alt_labels", "description", "skill_type", "reuse_level"]
            + ["group_code", "group_title"]
        )
        for uri, label, alts, description, group in SKILLS:
            writer.writerow([uri, label, alts, description, "umiejętność", "", group, ""])
    return path


class EmbedderTests(unittest.TestCase):
    def test_ollama_embedder_batches_and_normalizes(self):
        session = MagicMock()
        session.__enter__.return_value = session
        session.post.side_effect = lambda url, json, timeout: MagicMock(
            json=lambda: {"embeddings": [[3.0, 4.0]] * len(json["input"])}
        )
        with patch("amc.esco.embedder.requests.Session", return_value=session):
            vectors = OllamaEmbedder("m", "http://host:1/").embed(["a"] * 40)
        self.assertEqual(vectors.shape, (40, 2))
        self.assertAlmostEqual(float(np.linalg.norm(vectors[0])), 1.0, places=5)
        self.assertEqual(session.post.call_count, 2)
        self.assertEqual(session.post.call_args[0][0], "http://host:1/api/embed")


class IndexTests(unittest.TestCase):
    def test_entries_include_alternative_labels(self):
        with tempfile.TemporaryDirectory() as directory:
            skills = index_module.read_skills(write_skills(Path(directory)))
        kinds = [(e.uri, e.kind) for e in entries_of(skills)]
        self.assertEqual(kinds.count(("u/1", "alt")), 2)
        self.assertEqual(len(kinds), 5)

    def test_top_k_returns_distinct_skills_best_first(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            embedder = FakeEmbedder()
            index = build_index(write_skills(root), root, embedder, log=lambda _: None)
            found = index.top_k(embedder.embed(["praca zespołowa"]), k=3)[0]
        self.assertEqual([m.uri for m in found][0], "u/1")
        self.assertEqual(len({m.uri for m in found}), len(found))
        self.assertEqual(found[0].kind, "alt")
        self.assertGreaterEqual(found[0].score, found[1].score)

    def test_build_resumes_from_finished_chunks_and_loads(self):
        original = index_module.CHUNK
        index_module.CHUNK = 2
        try:
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                csv_path = write_skills(root)
                embedder = FakeEmbedder()
                build_index(csv_path, root, embedder, log=lambda _: None)
                self.assertEqual(embedder.calls, 3)
                again = build_index(csv_path, root, embedder, log=lambda _: None)
                self.assertEqual(embedder.calls, 3)
                self.assertEqual(
                    len(load_index(csv_path, root, "fake").entries), len(again.entries)
                )
        finally:
            index_module.CHUNK = original

    def test_load_without_build_fails_clearly(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertRaisesRegex(FileNotFoundError, "build-index"):
                load_index(write_skills(root), root, "fake")


class CalibrationTests(unittest.TestCase):
    def test_threshold_table_and_choice(self):
        scores = [0.9, 0.8, 0.7, 0.6, 0.5, 0.4]
        correct = [True, True, True, False, True, False]
        rows = {round(r.threshold, 1): r for r in threshold_table(scores, correct)}
        self.assertEqual(rows[0.7].accepted, 3)
        self.assertEqual(rows[0.7].precision, 1.0)
        self.assertAlmostEqual(rows[0.7].recall, 0.75)
        self.assertEqual(best_threshold(list(rows.values()), min_precision=0.9).threshold, 0.7)

    def test_mismatched_inputs_are_rejected(self):
        with self.assertRaises(ValueError):
            threshold_table([0.5], [])


class ReviewTests(unittest.TestCase):
    def test_sheet_hides_scores_and_verdicts_are_read(self):
        matches = [
            Match("u/1", "pracować w zespole", 0.83, "preferred"),
            Match("u/2", "x", 0.4, "alt"),
        ]
        with tempfile.TemporaryDirectory() as directory:
            sheet, key = Path(directory) / "s.csv", Path(directory) / "k.csv"
            write_review(
                sheet,
                key,
                [("F001", "praca w zespole", "ctx", matches), ("F002", "f", "c", [])],
                {"u/1": "Opis 1"},
            )
            text = sheet.read_text(encoding="utf-8-sig")
            self.assertIn("pracować w zespole - Opis 1", text)
            self.assertNotIn("0.83", text)
            with self.assertRaises(FileExistsError):
                write_review(sheet, key, [], {})
            with self.assertRaisesRegex(ValueError, "must be one of"):
                read_verdicts(sheet, key)
            with sheet.open(encoding="utf-8-sig", newline="") as stream:
                rows = list(csv.reader(stream))
            rows[1][6], rows[2][6] = "1", "none"
            with sheet.open("w", encoding="utf-8-sig", newline="") as stream:
                csv.writer(stream).writerows(rows)
            scores, correct, hits, total = read_verdicts(sheet, key)
        self.assertEqual((scores, correct, hits, total), ([0.83], [True], 1, 1))


if __name__ == "__main__":
    unittest.main()
