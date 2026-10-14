"""Typed records for parsed job advertisements."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class JobAd:
    """Structured advertisement fields; missing values are empty strings."""

    ad_id: int
    published_at: str
    valid_until: str
    title: str
    institution: str
    unit: str
    city: str
    positions: str
    work_time: str
    salary_text: str


@dataclass(frozen=True, slots=True)
class JobAdText:
    """Free-text sections kept separate from metadata for classification."""

    ad_id: int
    tasks: str
    requirements_required: str
    requirements_optional: str
