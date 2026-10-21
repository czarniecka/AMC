"""Comment HTML to text and the conventional 'Company | Role | Place | ...' first line."""

import re
from datetime import date, datetime, timezone

from bs4 import BeautifulSoup

from amc import privacy

COLUMNS = (
    "ad_id",
    "thread_id",
    "thread_month",
    "ad_date",
    "header",
    "company",
    "role",
    "location",
    "remote",
    "salary",
    "ad_text",
    "url",
    "fetched_at",
)

OBFUSCATED_EMAIL = re.compile(
    r"[\w.+-]+\s*[\[(<{]\s*at\s*[\])>}]\s*[\w-]+(?:\s*(?:[\[(<{]\s*dot\s*[\])>}]|\.)\s*[\w-]+)+",
    re.I,
)
# Polish numbers plus the North American format common in these ads.
PHONE = re.compile(privacy.PHONE.pattern + r"|(\+1[\s.-]?)?\(?\b\d{3}\)?[\s.-]\d{3}[\s.-]\d{4}\b")

URL = re.compile(r"^(https?://|www\.)\S+$|^[\w-]+(\.[\w-]+)+(/\S*)?$", re.I)
SALARY = re.compile(
    r"[$€£¥₹]\s?\d|\d\s?[$€£]|\b\d{2,3}(?:[.,]\d)?\s?k\b|\b(?:usd|eur|gbp|chf|cad|aud|pln)\b"
    r"|\b(?:salary|comp(?:ensation)?|pay)\b|\d{2,3}[,.]?\d{3}\s*[-–]",
    re.I,
)
# A part made only of these words names neither a role nor a place.
WORK_MODE = re.compile(
    r"https?://\S+|www\.\S+|\b(?:full|part)[\s-]?time\b|\bfulltime\b|\bon[\s-]?site\b|\bremote\b|"
    r"\bhybrid\b|\bin[\s-](?:office|person)\b|\bcontract(?:or|s)?\b|\bpermanent\b|\bfreelance\b|"
    r"\binterns?(?:hips?)?\b|\bvisa\b|\brelocation\b|\bsponsorship\b|\bh-?1b\b|\boffered\b|"
    r"\bequity\b|\bonly\b|\bok\b|\bor\b|\band\b|\bft\b|\bpt\b",
    re.I,
)
NOT_PLACE = re.compile(r"citizen|clearance|green card|visa", re.I)
REMOTE = re.compile(r"\bremote\b", re.I)
NO_REMOTE = re.compile(r"\bno(?:t)?\s+remote\b|\bremote:?\s*no\b|\bnon-remote\b", re.I)
ONSITE = re.compile(r"\bon[\s-]?site\b|\bin[\s-]office\b|\bin[\s-]person\b|\bhybrid\b", re.I)
ROLE = re.compile(
    r"engineer|developer|\bdev\b|scientist|designer|manager|\blead\b|head of|architect|analyst|"
    r"\bsre\b|devops|research|programmer|\bcto\b|\bvp\b|director|founding|consultant|"
    r"administrator|specialist|technician|recruiter|marketer|writer|\bml\b|\bai\b|"
    r"full[\s-]?stack|front[\s-]?end|back[\s-]?end|product|staff|principal|\bsenior\b|"
    r"\bjunior\b|mobile|ios|android|data|security|support|sales|operations|qa\b|tester|"
    r"positions|roles\b|engineering",
    re.I,
)
PLACE = re.compile(
    r"\b[A-Z][a-zA-Z.' -]+,\s*(?:[A-Z]{2}\b|[A-Z][a-z]+)|\b(?:NYC|SF|SFBA|LA|USA?|UK|EU|EMEA|"
    r"APAC|Bay Area|Europe|Canada|Germany|London|Berlin|Paris|Amsterdam|Toronto|Boston|"
    r"Seattle|Austin|Chicago|Denver|New York|San Francisco|Los Angeles|Singapore|Tokyo|"
    r"Sydney|Zurich|Munich|Dublin|Stockholm|Warsaw|Worldwide|Anywhere|Global)\b"
)
MAX_PART = 120  # longer parts are the description glued to the first line


def scrub(text: str) -> str:
    """Mask e-mail addresses (also 'name [at] firm [dot] com') and phone numbers."""
    text = OBFUSCATED_EMAIL.sub("[EMAIL]", privacy.EMAIL.sub("[EMAIL]", text))
    return PHONE.sub("[TEL]", text)


def paragraphs(html: str) -> list[str]:
    """Paragraph texts; HN starts paragraphs with <p> and links are replaced by their URL."""
    found = []
    for part in re.split(r"(?i)<p>", html or ""):
        soup = BeautifulSoup(part, "html.parser")
        for link in soup.find_all("a"):
            link.replace_with(link.get("href") or link.get_text())
        lines = (re.sub(r"[ \t\r\f\v]+", " ", line).strip() for line in soup.get_text().split("\n"))
        text = "\n".join(lines).strip()
        if text:
            found.append(scrub(text))
    return found


def parse_header(header: str) -> dict[str, str]:
    """Fields from a '|'-separated first line; unrecognized fields stay empty, never guessed."""
    fields = {"company": "", "role": "", "location": "", "remote": "unknown", "salary": ""}
    if NO_REMOTE.search(header) or (ONSITE.search(header) and not REMOTE.search(header)):
        fields["remote"] = "no"
    elif REMOTE.search(header):
        fields["remote"] = "yes"

    parts = [part.strip() for part in header.split("|") if part.strip()]
    if len(parts) < 2:
        return fields
    fields["company"] = parts[0]
    places, salaries = [], []
    for part in parts[1:]:
        if (
            len(part) > MAX_PART
            or URL.match(part)
            or not re.sub(r"[\W_]+", "", WORK_MODE.sub("", part))
        ):
            continue
        new_role = ROLE.search(part) and not fields["role"]
        if re.search(r"\d", part) and SALARY.search(part) and not ROLE.search(part):
            salaries.append(part)
        elif PLACE.search(part) and not NOT_PLACE.search(part):
            # "Engineer, Berlin" is kept as the role.
            if new_role and not REMOTE.search(part) and not ONSITE.search(part):
                fields["role"] = part
            else:
                places.append(part)
        elif new_role:
            fields["role"] = part
    fields["location"] = "; ".join(places)
    fields["salary"] = "; ".join(salaries)
    return fields


def ad_row(ad_id: int, thread_id: int, month: str, created: int, html: str) -> dict[str, object]:
    """One advertisement; the author's username is never stored."""
    texts = paragraphs(html)
    header = texts[0].split("\n")[0] if texts else ""
    return {
        "ad_id": ad_id,
        "thread_id": thread_id,
        "thread_month": month,
        "ad_date": datetime.fromtimestamp(created, timezone.utc).isoformat(),
        "header": header,
        **parse_header(header),
        "ad_text": "\n\n".join(texts),
        "url": f"https://news.ycombinator.com/item?id={ad_id}",
        "fetched_at": date.today().isoformat(),
    }
