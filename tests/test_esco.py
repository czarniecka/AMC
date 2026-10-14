"""Offline tests for ESCO record extraction and resumable paging."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from amc.esco import fetch
from amc.esco.fetch import extract_skill, fetch_all


def concept(number: int) -> dict:
    return {
        "uri": f"http://data.europa.eu/esco/skill/{number}",
        "title": f"umiejętność {number}",
        "alternativeLabel": {"pl": ["inna nazwa"], "de": ["anderer Name"]},
        "description": {"pl": {"literal": "Opis  \n umiejętności."}},
        "_links": {
            "hasSkillType": [{"title": "umiejętność"}],
            "hasReuseLevel": [{"title": "międzysektorowe"}],
            "broaderHierarchyConcept": [{"code": "S2.1.1", "title": "grupa"}],
        },
    }


class EscoTests(unittest.TestCase):
    def test_extract_keeps_polish_fields_only(self):
        skill = extract_skill(concept(1))
        self.assertEqual(skill.alt_labels, "inna nazwa")
        self.assertEqual(skill.description, "Opis umiejętności.")
        self.assertEqual((skill.group_code, skill.skill_type), ("S2.1.1", "umiejętność"))

    def test_extract_tolerates_missing_optional_fields(self):
        skill = extract_skill({"uri": "u", "title": "t", "_links": {}})
        self.assertEqual((skill.alt_labels, skill.description, skill.group_code), ("", "", ""))

    def test_fetch_all_walks_tree_batches_and_resumes_from_cache(self):
        original = fetch.BATCH
        fetch.BATCH = 2
        uris = [concept(i)["uri"] for i in (1, 2, 3)]
        top = {"_links": {"hasTopConcept": [{"uri": "top"}]}}
        group = {
            "_links": {
                "narrowerConcept": [{"uri": "child"}],
                "narrowerSkill": [{"uri": uris[0]}, {"uri": uris[1]}],
            }
        }
        child = {"_links": {"narrowerSkill": [{"uri": uris[2]}, {"uri": uris[0]}]}}

        def get(url, params, timeout):
            if url == fetch.TAXONOMY:
                payload = top
            elif url == fetch.CONCEPT:
                payload = group if params["uri"] == "top" else child
            else:
                payload = {
                    "_embedded": {u: concept(int(u.rsplit("/", 1)[1])) for u in params["uris"]}
                }
            return Mock(status_code=200, json=lambda: payload)

        try:
            with tempfile.TemporaryDirectory() as directory:
                session = Mock(headers={}, get=Mock(side_effect=get))
                options = {"session": session, "sleeper": lambda _: None, "log": lambda _: None}
                skills = fetch_all(Path(directory), **options)
                self.assertEqual(sorted(s.uri for s in skills), uris)
                calls = session.get.call_count
                self.assertEqual(len(fetch_all(Path(directory), **options)), 3)
                self.assertEqual(session.get.call_count, calls)
        finally:
            fetch.BATCH = original

    def test_defective_concept_is_isolated_and_recorded(self):
        uris = [concept(i)["uri"] for i in (1, 2, 3, 4)]
        bad = uris[2]

        def get(url, params, timeout):
            if url == fetch.API and bad in params["uris"]:
                return Mock(status_code=500, json=lambda: {})
            payload = {"_embedded": {u: concept(int(u.rsplit("/", 1)[1])) for u in params["uris"]}}
            return Mock(status_code=200, json=lambda: payload)

        with tempfile.TemporaryDirectory() as directory:
            (Path(directory) / "skill_uris.json").write_text(json.dumps(uris), encoding="utf-8")
            session = Mock(headers={}, get=Mock(side_effect=get))
            skills = fetch_all(
                Path(directory), session=session, sleeper=lambda _: None, log=lambda _: None
            )
            self.assertEqual(sorted(s.uri for s in skills), [u for u in uris if u != bad])
            recorded = json.loads((Path(directory) / "skipped_skills.json").read_text())
            self.assertEqual(recorded, [bad])

    def test_incomplete_batch_is_rejected_and_not_cached(self):
        with tempfile.TemporaryDirectory() as directory:
            session = Mock(headers={})
            session.get.side_effect = lambda url, params, timeout: Mock(
                status_code=200,
                json=lambda: {"_links": {"hasTopConcept": [], "narrowerSkill": []}}
                if url != fetch.API
                else {"_embedded": {}},
            )
            (Path(directory) / "skill_uris.json").write_text('["http://x/1"]', encoding="utf-8")
            with self.assertRaisesRegex(Exception, "Incomplete"):
                fetch_all(Path(directory), session=session, sleeper=lambda _: None, log=print)
            self.assertEqual(list((Path(directory) / "batches").glob("*.json")), [])


if __name__ == "__main__":
    unittest.main()
