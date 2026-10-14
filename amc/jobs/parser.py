"""Parse a server-rendered advertisement page with the standard library only."""

import re
from html.parser import HTMLParser

from amc.jobs.models import JobAd, JobAdText

MONTHS = {
    "stycznia": 1,
    "lutego": 2,
    "marca": 3,
    "kwietnia": 4,
    "maja": 5,
    "czerwca": 6,
    "lipca": 7,
    "sierpnia": 8,
    "września": 9,
    "października": 10,
    "listopada": 11,
    "grudnia": 12,
}
BLOCK_TAGS = {"li", "p", "br", "div", "ul", "h1", "h2", "tr"}
HEADINGS = {
    "Czym będziesz się zajmować",
    "Kogo poszukujemy",
    "Potrzebne ci będą",
    "Dodatkowym atutem będzie",
    "(wymagania niezbędne)",
    "(wymagania dodatkowe)",
}
SECTION_START = re.compile(r'<div class="job-post__main-content__[\w-]+ customize-bar')


class ParseError(ValueError):
    """The page is not a recognizable advertisement."""


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._skip = 0
        self._item = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self._skip += 1
        elif tag in BLOCK_TAGS:
            self.parts.append("\n")
        if tag == "li":
            self._item += 1

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self._skip -= 1
        elif tag in BLOCK_TAGS:
            self.parts.append("\n")
        if tag == "li":
            self._item = max(0, self._item - 1)

    def handle_data(self, data):
        if not self._skip:
            # Source line wraps inside a list item are not item boundaries.
            self.parts.append(data.replace("\n", " ") if self._item else data)


def html_to_lines(fragment: str) -> list[str]:
    """Convert markup to non-empty, whitespace-normalized lines."""
    extractor = _TextExtractor()
    extractor.feed(fragment)
    text = "".join(extractor.parts).replace("\xa0", " ")
    lines = (re.sub(r"[ \t]+", " ", line).strip() for line in text.split("\n"))
    return [line.removeprefix("· ").strip() for line in lines if line]


def _text(html: str, pattern: str) -> str:
    match = re.search(pattern, html, re.S)
    return " ".join(html_to_lines(match.group(1))) if match else ""


def _section(html: str, name: str) -> str:
    """Return the HTML of one expandable section, up to the next section."""
    start = html.find(f'<div class="job-post__main-content__{name} customize-bar')
    if start < 0:
        return ""
    following = SECTION_START.search(html, start + 10)
    return html[start : following.start() if following else len(html)]


def _info_circle(html: str, modifier: str) -> str:
    return _text(html, rf'info-circle__content--{modifier}(?:\s[^"]*)?">(.*?)</div>')


def _valid_until(html: str) -> str:
    match = re.search(r"(\d{1,2}) (\w+) (\d{4})", _info_circle(html, "valid-to"))
    if not match or match.group(2) not in MONTHS:
        return ""
    return f"{match.group(3)}-{MONTHS[match.group(2)]:02d}-{int(match.group(1)):02d}"


def _body(fragment: str) -> str:
    """Section text without the heading lines the site renders around the lists."""
    lines = [line for line in html_to_lines(fragment) if line not in HEADINGS]
    return "\n".join(lines)


def parse_ad(html: str) -> tuple[JobAd, JobAdText]:
    """Extract metadata and text sections; raise ParseError for non-ad pages."""
    number = re.search(
        r'class="adv-number">(\d+)</span>\s*</span>\s*/\s*(\d{2})\.(\d{2})\.(\d{4})', html
    )
    title = _text(html, r"<h1[^>]*>(.*?)</h1>")
    if not number or not title:
        raise ParseError("Page has no advertisement number or title.")
    ad_id, day, month, year = number.groups()
    address = re.search(r"<address>(.*?)</address>", html, re.S)
    address_lines = html_to_lines(address.group(1)) if address else []
    ad = JobAd(
        ad_id=int(ad_id),
        published_at=f"{year}-{month}-{day}",
        valid_until=_valid_until(html),
        title=title,
        institution=_text(html, r"office-name\"[^>]*>(.*?)</div>"),
        unit=_text(html, r"institution-unit\">(.*?)</span>"),
        city=address_lines[1] if len(address_lines) > 1 else "",
        positions=_info_circle(html, "work-time-cnt"),
        work_time=_info_circle(html, "work-time"),
        salary_text=_info_circle(html, "salary"),
    )
    requirements = _section(html, "requirements")
    marker = requirements.find("additional-requirements")
    marker = requirements.rfind("<div", 0, marker) if marker >= 0 else marker
    required, optional = (
        (requirements, "") if marker < 0 else (requirements[:marker], requirements[marker:])
    )
    text = JobAdText(
        ad_id=ad.ad_id,
        tasks=_body(_section(html, "responsibilities")),
        requirements_required=_body(required),
        requirements_optional=_body(optional),
    )
    return ad, text
