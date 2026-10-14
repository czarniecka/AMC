"""Download the Polish ESCO skills pillar through the official public web service."""

import json
import os
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import requests

from amc.youtube.api_client import CollectionError
from amc.youtube.exporter import write_csv

API = "https://ec.europa.eu/esco/api/resource/skill"
SCHEME = "http://data.europa.eu/esco/concept-scheme/skills"
LANGUAGE = "pl"
COLUMNS = (
    "uri",
    "preferred_label",
    "alt_labels",
    "description",
    "skill_type",
    "reuse_level",
    "group_code",
    "group_title",
)


@dataclass(frozen=True, slots=True)
class EscoSkill:
    uri: str
    preferred_label: str
    alt_labels: str
    description: str
    skill_type: str
    reuse_level: str
    group_code: str
    group_title: str


def _first_title(links: dict, name: str) -> str:
    items = links.get(name) or [{}]
    return items[0].get("title", "")


def extract_skill(item: dict) -> EscoSkill:
    """Reduce one embedded concept to the Polish fields used for matching."""
    links = item.get("_links", {})
    group = (links.get("broaderHierarchyConcept") or [{}])[0]
    description = (item.get("description") or {}).get(LANGUAGE) or {}
    return EscoSkill(
        uri=item["uri"],
        preferred_label=item["title"],
        alt_labels=" | ".join((item.get("alternativeLabel") or {}).get(LANGUAGE, [])),
        description=" ".join(description.get("literal", "").split()),
        skill_type=_first_title(links, "hasSkillType"),
        reuse_level=_first_title(links, "hasReuseLevel"),
        group_code=group.get("code", ""),
        group_title=group.get("title", ""),
    )


TAXONOMY = "https://ec.europa.eu/esco/api/resource/taxonomy"
CONCEPT = "https://ec.europa.eu/esco/api/resource/concept"
BATCH = 50


class ServiceRefused(CollectionError):
    """The service answered HTTP 500 for this resource; retrying will not help."""


class _Api:
    """GET JSON with a fixed delay and retries (deep paging is rejected, so we walk the tree)."""

    def __init__(self, session, delay, retries, sleeper) -> None:
        self.session, self.delay, self.retries, self.sleeper = session, delay, retries, sleeper

    def get(self, url: str, params: dict) -> dict:
        for attempt in range(self.retries + 1):
            self.sleeper(self.delay * (2**attempt if attempt else 1))
            try:
                response = self.session.get(url, params=params, timeout=(5, 120))
            except requests.RequestException:
                continue
            if response.status_code == 200:
                return response.json()
            if response.status_code == 500 and attempt >= 1:
                raise ServiceRefused(f"ESCO answered HTTP 500 for {params.get('uri', url)}.")
        raise CollectionError(f"ESCO service unavailable ({url}); run again to resume.")


def crawl_skill_uris(api: _Api, cache: Path, log: Callable[[str], None]) -> list[str]:
    """Collect every skill URI by walking the concept tree from the four top concepts."""
    if cache.exists():
        return json.loads(cache.read_text(encoding="utf-8"))
    groups_dir = cache.parent / "groups"
    groups_dir.mkdir(parents=True, exist_ok=True)
    top = api.get(TAXONOMY, {"uri": SCHEME, "language": LANGUAGE})["_links"]["hasTopConcept"]
    queue, seen_groups, skills = [item["uri"] for item in top], set(), {}
    while queue:
        uri = queue.pop()
        if uri in seen_groups:
            continue
        seen_groups.add(uri)
        children, leaves = _group_links(api, groups_dir, uri)
        queue.extend(children)
        skills.update(dict.fromkeys(leaves, True))
        if len(seen_groups) % 50 == 0:
            log(f"{len(seen_groups)} groups, {len(skills)} skills found")
    uris = sorted(skills)
    cache.write_text(json.dumps(uris), encoding="utf-8")
    return uris


def _group_links(api: _Api, groups_dir: Path, uri: str) -> tuple[list[str], list[str]]:
    """Child groups and skills of one concept; cached so a crawl can resume."""
    cache = groups_dir / (uri.rsplit("/", 1)[-1] + ".json")
    if cache.exists():
        data = json.loads(cache.read_text(encoding="utf-8"))
    else:
        try:
            links = api.get(CONCEPT, {"uri": uri, "language": LANGUAGE})["_links"]
        except ServiceRefused:
            # Known upstream defect (e.g. S1.5.3): record it and continue without this group.
            skipped = groups_dir.parent / "skipped_groups.json"
            known = json.loads(skipped.read_text(encoding="utf-8")) if skipped.exists() else []
            skipped.write_text(json.dumps(sorted({*known, uri})), encoding="utf-8")
            return [], []
        data = {
            "children": [item["uri"] for item in links.get("narrowerConcept", [])],
            "skills": [item["uri"] for item in links.get("narrowerSkill", [])],
        }
        cache.write_text(json.dumps(data), encoding="utf-8")
    return data["children"], data["skills"]


def _record_skipped(path: Path, uris: list[str]) -> None:
    known = json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
    path.write_text(json.dumps(sorted({*known, *uris})), encoding="utf-8")


def _fetch_records(api: _Api, chunk: list[str]) -> tuple[list[dict], list[str]]:
    """Fetch a batch; on HTTP 500 split it to isolate the defective concepts."""
    try:
        payload = api.get(API, {"uris": chunk, "language": LANGUAGE})
    except ServiceRefused:
        if len(chunk) == 1:
            return [], chunk
        middle = len(chunk) // 2
        first, bad_first = _fetch_records(api, chunk[:middle])
        second, bad_second = _fetch_records(api, chunk[middle:])
        return first + second, bad_first + bad_second
    return [_as_dict(item) for item in payload.get("_embedded", {}).values()], []


def fetch_all(
    output_dir: Path,
    *,
    delay: float = 1.0,
    retries: int = 5,
    session: requests.Session | None = None,
    sleeper: Callable[[float], None] = time.sleep,
    log: Callable[[str], None] = print,
) -> list[EscoSkill]:
    """Fetch details in batches; batches are cached so an interrupted run resumes."""
    batches = output_dir / "batches"
    batches.mkdir(parents=True, exist_ok=True)
    owned = session is None
    session = session if session is not None else requests.Session()
    session.headers["User-Agent"] = os.getenv("KPRM_USER_AGENT", "AMC-student-research/0.1")
    api = _Api(session, delay, retries, sleeper)
    skills: list[EscoSkill] = []
    try:
        uris = crawl_skill_uris(api, output_dir / "skill_uris.json", log)
        for start in range(0, len(uris), BATCH):
            chunk = uris[start : start + BATCH]
            cache = batches / f"{start:06d}.json"
            if cache.exists():
                records = json.loads(cache.read_text(encoding="utf-8"))
            else:
                records, refused = _fetch_records(api, chunk)
                if refused:
                    _record_skipped(output_dir / "skipped_skills.json", refused)
                if {r["uri"] for r in records} | set(refused) != set(chunk):
                    raise CollectionError(f"Incomplete ESCO batch at {start}; nothing was cached.")
                cache.write_text(json.dumps(records, ensure_ascii=False), encoding="utf-8")
            skills.extend(EscoSkill(**record) for record in records)
            log(f"{len(skills)}/{len(uris)}")
    finally:
        if owned:
            session.close()
    return skills


def _as_dict(item: dict) -> dict:
    skill = extract_skill(item)
    return {name: getattr(skill, name) for name in COLUMNS}


def save_csv(path: Path, skills: list[EscoSkill]) -> None:
    write_csv(path, COLUMNS, sorted(skills, key=lambda s: s.uri), text_columns=COLUMNS)
