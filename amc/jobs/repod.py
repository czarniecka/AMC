"""Parse an advertisement page into the RepOD civil-service dataset format.

The columns follow kprm-job-ads-raw-data (RepOD, doi:10.18150/Q23MGT), so 2024 onward can be
appended to the 2018-2023 release. `ad_result` and `ad_date_result` stay empty: results list
the names of hired candidates. `template` is the advertisement form version taken from the
PDF link; a template change can look like a change in requirements.
"""

import re
from datetime import date

from bs4 import BeautifulSoup, NavigableString

from amc.jobs.client import BASE_URL
from amc.jobs.parser import MONTHS
from amc.privacy import mask_contacts

REPOD_COLUMNS = (
    "ad_id",
    "ad_job_title",
    "ad_institution",
    "ad_city",
    "ad_address",
    "ad_work_place1",
    "ad_work_place2",
    "ad_date_announced",
    "ad_date_result",
    "ad_date_valid",
    "ad_date_documents",
    "ad_result",
    "ad_salary",
    "ad_vacancies",
    "ad_work_time",
    "ad_responsibilities",
    "ad_education",
    "ad_requirements1",
    "ad_requirements2",
    "ad_views",
)
COLUMNS = (*REPOD_COLUMNS, "url", "template", "fetched_at")
SEPARATOR = "|-|"  # list item separator used by RepOD

SECTIONS = (
    (r"^czym będziesz się zajmować|^zakres zadań", "ad_responsibilities"),
    (r"wymagania niezbędne|potrzebne ci będą", "ad_requirements1"),
    (r"wymagania dodatkowe|dodatkowym atutem", "ad_requirements2"),
    (
        r"^co oferujemy|^dostępność|^warunki pracy|^dodatkowe informacje|^planujemy następujące|"
        r"dokumenty niezbędne|^dołącz, jeśli posiadasz|^aplikuj do|^przetwarzanie danych|"
        r"^dane osobowe|^kogo poszukujemy",
        None,
    ),
)
NAVIGATION = {"ogłoszenia o naborach", "wyniki naborów", "wróć do wyników"}
NOT_A_SECTION = "none"

STREET = re.compile(r"^(ul\.|al\.|pl\.|os\.|ulica|aleja|aleje|plac|rondo|skwer)\s", re.I)
NUMBER = re.compile(r"^\d+[a-zA-Z]?(?:\s*[/-]\s*\d+[a-zA-Z]?)?$")
POSTCODE = re.compile(r"\b\d{2}-\d{3}\b")
EXPERIENCE = re.compile(r"^Doświadczenie zawodowe:")


def clean(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def polish_date(text: str) -> str:
    """'1 grudnia 2025' or '01.12.2025' -> '2025-12-01'."""
    match = re.search(r"(\d{1,2})\s+([a-ząćęłńóśźż]+)\s+(\d{4})", text.lower())
    if match and match.group(2) in MONTHS:
        return f"{match.group(3)}-{MONTHS[match.group(2)]:02d}-{int(match.group(1)):02d}"
    match = re.search(r"(\d{2})\.(\d{2})\.(\d{4})", text)
    return f"{match.group(3)}-{match.group(2)}-{match.group(1)}" if match else ""


def split_head(head: list[str]) -> tuple[str, str]:
    """Institution and address from the lines above 'Ogłoszenie nr'.

    The address starts at the postcode, or at the street when the street precedes it,
    and may span one or several lines.
    """
    k = next((n for n in range(len(head) - 1, -1, -1) if POSTCODE.search(head[n])), None)
    if k is not None:
        while k > 1 and (STREET.match(head[k - 1]) or NUMBER.match(head[k - 1])):
            k -= 1
    else:
        k = next((n for n, line in enumerate(head) if STREET.match(line)), None)
        if k is None and len(head) >= 3 and NUMBER.match(head[-1]):
            k = len(head) - 2
    if k is None or k < 1:
        return (head[-1] if head else ""), ""
    return head[k - 1], " ".join(head[k:])


def section_for(text: str) -> str | None:
    low = text.lower().strip(" :")
    if len(low) > 80:
        return NOT_A_SECTION
    for pattern, column in SECTIONS:
        if re.search(pattern, low):
            return column
    return NOT_A_SECTION


def collect_lists(soup: BeautifulSoup) -> dict[str, list[str]]:
    """List items under each section heading, in page order."""
    found: dict[str, list[str]] = {
        "ad_responsibilities": [],
        "ad_requirements1": [],
        "ad_requirements2": [],
    }
    current: list[str | None] = [None]

    def walk(node) -> None:
        for child in node.children:
            if isinstance(child, NavigableString):
                text = clean(str(child))
                if text and (column := section_for(text)) != NOT_A_SECTION:
                    current[0] = column
            elif child.name == "li":
                if current[0]:
                    # Contact persons' e-mails and phones appear in list items.
                    found[current[0]].append(mask_contacts(clean(child.get_text(" "))))
            elif child.name not in ("script", "style"):
                walk(child)

    walk(soup.body or soup)
    return found


def parse_repod(html: str, url: str, ad_id: int) -> dict[str, object]:
    """One RepOD row; fields that cannot be found are empty strings."""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    lines = [line for line in (clean(x) for x in soup.get_text("\n").split("\n")) if line]
    flat = " ".join(lines)
    row: dict[str, object] = dict.fromkeys(COLUMNS, "")
    row["ad_id"] = ad_id

    def grab(pattern: str) -> str:
        match = re.search(pattern, flat)
        return match.group(1).strip() if match else ""

    i = next((k for k, line in enumerate(lines) if line.startswith("Ogłoszenie nr")), None)
    if i is not None:
        # The date is on the number line or the next one.
        row["ad_date_announced"] = polish_date(" ".join(lines[i : i + 3]))
        head = [x for x in lines[:i] if x.lower() not in NAVIGATION and not x.startswith("![")]
        row["ad_institution"], row["ad_address"] = split_head(head)
    if not row["ad_date_announced"]:
        row["ad_date_announced"] = polish_date(
            grab(r"(?:Data (?:ogłoszenia|publikacji)|Opublikowano)\W*(.{0,25})")
        )

    j = next(
        (k for k, x in enumerate(lines) if x.lower().startswith("poszukujemy osoby na stanowisko")),
        None,
    )
    if j is not None and j + 1 < len(lines):
        row["ad_job_title"] = lines[j + 1].lower()
        match = re.search(
            r"Do spraw:\s*(.+?)\s+(?:#|Umowa|Pierwszeństwo|Dostępne|Liczba stanowisk)",
            " ".join(lines[j + 2 : j + 8]) + " Liczba stanowisk",
        )
        row["ad_work_place2"] = match.group(1) if match else ""

    row["ad_vacancies"] = grab(r"Liczba stanowisk\s+(\d+)")
    row["ad_work_time"] = grab(r"Wymiar etatu\s+([\d/,.]+)")
    place = grab(r"Miejsce pracy\s+(.+?)\s+Ważne do")
    city_match = re.search(r"\d{2}-\d{3}\s+(.+)$", place)
    city = city_match.group(1).strip() if city_match else ""
    row["ad_city"] = city
    row["ad_work_place1"] = f"{city} {place}".strip()
    row["ad_date_valid"] = polish_date(grab(r"Ważne do\s+(\d{1,2}\s+\w+\s+\d{4})"))
    row["ad_date_documents"] = polish_date(
        grab(r"Dokumenty należy złożyć do:\s*(\d{2}\.\d{2}\.\d{4})")
    )
    salary = grab(r"Wynagrodzenie\s+zasadnicze\s+(.+?(?:brutto|netto))")
    row["ad_salary"] = salary or "nie podano wynagrodzenia"
    row["ad_views"] = grab(r"Liczba odwiedzin:\s*(\d+)")

    lists = collect_lists(soup)
    required = []
    for item in lists["ad_requirements1"]:
        if item.lower().startswith("wykształcenie:") and not row["ad_education"]:
            # RepOD keeps required education in its own column.
            row["ad_education"] = item.split(":", 1)[1].strip()
        else:
            required.append(EXPERIENCE.sub("doświadczenie zawodowe:", item))
    row["ad_responsibilities"] = SEPARATOR.join(lists["ad_responsibilities"])
    row["ad_requirements1"] = SEPARATOR.join(required)
    row["ad_requirements2"] = SEPARATOR.join(
        EXPERIENCE.sub("doświadczenie zawodowe:", x) for x in lists["ad_requirements2"]
    )

    # The real address and form version come from the PDF link (for example
    # statystyk,157952,v7.pdf), because the page opens under any v7/v8 suffix.
    row["url"] = url
    pdf = soup.find("a", href=re.compile(rf",{ad_id}(?:,v\d+)?\.pdf"))
    if pdf:
        real = pdf["href"][:-4]
        row["url"] = real if real.startswith("http") else BASE_URL + "/" + real.lstrip("/")
        version = re.search(r",(v\d+)$", real)
        row["template"] = version.group(1) if version else "no version"
    row["fetched_at"] = date.today().isoformat()
    return row
