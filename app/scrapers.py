from __future__ import annotations

from dataclasses import dataclass
import re
import unicodedata
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup


@dataclass
class ConcertData:
    source: str
    source_url: str
    external_id: str
    name: str
    program: str
    performers: str
    hall: str
    date: str
    time: str


HEADERS = {
    "User-Agent": "concert-dashboard-bot/1.0 (+https://localhost)"
}


def _text(node) -> str:
    return node.get_text(" ", strip=True) if node else ""


def _absolute(base_url: str, href: str) -> str:
    return urljoin(base_url, href)


def _normalize_text(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text or "")
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
    return re.sub(r"\s+", " ", ascii_text).strip().lower()


def _unique_parts(parts: list[str]) -> list[str]:
    seen: set[str] = set()
    unique: list[str] = []
    for part in parts:
        cleaned = part.strip()
        if not cleaned:
            continue
        key = _normalize_text(cleaned)
        if key in seen:
            continue
        seen.add(key)
        unique.append(cleaned)
    return unique


PROGRAM_HINTS = (
    "werke von",
    "sinfonie",
    "symphony",
    "requiem",
    "passion",
    "suite",
    "concerto",
    "concert",
    "klavierabend",
    "preis",
    "podium",
    "stabat",
)

PERFORMANCE_TYPE_HINTS = (
    "recital",
    "klavierabend",
    "liederabend",
    "songbook",
    "gala",
    "matinee",
    "soiree",
)


def _looks_like_program_text(text: str) -> bool:
    normalized = _normalize_text(text)
    if not normalized:
        return False
    if any(hint in normalized for hint in PROGRAM_HINTS):
        return True
    if len(normalized.split()) >= 9 and normalized.endswith("."):
        return True
    return False


def _looks_like_performance_type(text: str) -> bool:
    normalized = _normalize_text(text)
    if not normalized:
        return False
    return any(hint in normalized for hint in PERFORMANCE_TYPE_HINTS)


def _looks_like_performer_name(text: str) -> bool:
    normalized = _normalize_text(text)
    if not normalized:
        return False
    if ":" in text:
        return False
    if len(normalized.split()) > 8:
        return False
    if _looks_like_performance_type(text):
        return False
    return not _looks_like_program_text(text)


def _split_performer_text(text: str) -> list[str]:
    return [part.strip() for part in re.split(r"\s*[\/;|]\s*", text or "") if part.strip()]


def _extract_performer_and_format_from_text(text: str) -> tuple[str, str]:
    parts = _split_performer_text(text)
    if len(parts) < 2:
        return text.strip(), ""

    performer_parts: list[str] = []
    format_parts: list[str] = []
    for part in parts:
        if _looks_like_performance_type(part):
            format_parts.append(part)
        else:
            performer_parts.append(part)

    if not performer_parts or not format_parts:
        return text.strip(), ""

    performers = " / ".join(_unique_parts(performer_parts))
    format_text = " / ".join(_unique_parts(format_parts))
    return performers, format_text


def _looks_like_person_list_title(name: str) -> bool:
    if ";" not in name:
        return False

    parts = [part.strip() for part in name.split(";") if part.strip()]
    if len(parts) < 2:
        return False

    for part in parts:
        normalized = _normalize_text(part)
        if not normalized:
            return False
        if ":" in part:
            return False
        if _looks_like_program_text(part) or _looks_like_performance_type(part):
            return False
        tokens = normalized.split()
        if len(tokens) == 0 or len(tokens) > 5:
            return False
        if any(char.isdigit() for char in normalized):
            return False

    return True


def _merge_program_text(program: str, extra: str) -> str:
    base = (program or "").strip()
    addon = (extra or "").strip()
    if not addon:
        return base
    if not base:
        return addon

    if _normalize_text(addon) in _normalize_text(base):
        return base
    return f"{base} / {addon}"


def _split_performer_field(text: str) -> list[str]:
    return [part.strip() for part in re.split(r"\s*[\/;|]\s*", text or "") if part.strip()]


def _clean_performer_line(text: str) -> str:
    cleaned = (text or "").strip()
    cleaned = re.sub(r"^&\s*", "", cleaned)
    return cleaned.strip()


def _merge_performer_text(existing: str, extra: str) -> str:
    existing_parts = [_clean_performer_line(part) for part in _split_performer_field(existing)]
    extra_parts = [_clean_performer_line(part) for part in _split_performer_field(extra)]
    merged = _unique_parts([part for part in [*existing_parts, *extra_parts] if part])
    return " / ".join(merged)


def _extract_elb_detail_metadata(source_url: str) -> tuple[str, str]:
    try:
        response = requests.get(source_url, timeout=30, headers=HEADERS)
        response.raise_for_status()
    except Exception:
        return "", ""

    soup = BeautifulSoup(response.text, "html.parser")
    root = soup.select_one(".event-detail-content")
    if not root:
        return "", ""

    program_paragraphs: list[str] = []
    for paragraph in root.select("p"):
        if paragraph.get("class"):
            continue
        text = paragraph.get_text(" ", strip=True)
        if len(text) >= 80:
            program_paragraphs.append(text)

    performer_lines: list[str] = []
    for paragraph in root.select("p.artists"):
        text = _clean_performer_line(paragraph.get_text(" ", strip=True))
        if text:
            performer_lines.append(text)

    program = "\n\n".join(_unique_parts(program_paragraphs))
    performers = " / ".join(_unique_parts(performer_lines))
    return program, performers


def _extract_elb_program_and_performers(subtitle: str) -> tuple[str, str]:
    text = subtitle.strip()
    if not text:
        return "", ""

    split_patterns = (
        r"\s+[–-]\s+with\s+",
        r"\s+[–-]\s+mit\s+",
    )

    for pattern in split_patterns:
        parts = re.split(pattern, text, maxsplit=1, flags=re.IGNORECASE)
        if len(parts) != 2:
            continue

        program_part = parts[0].strip(" -–")
        performers_part = parts[1].strip(" -–")
        if not program_part or not performers_part:
            continue

        return program_part, performers_part

    return text, ""


ELB_PERFORMER_TOKENS = (
    "philharmonie",
    "orchester",
    "orchestra",
    "ensemble",
    "quartett",
    "quartet",
    "choir",
    "chor",
    "band",
    "trio",
    "duo",
)


ELB_EVENT_PREFIXES = (
    "workshop",
    "school concert",
    "family concert",
    "teatime classics",
    "insight",
)

NON_PERSON_NAME_TOKENS = (
    "concert",
    "workshop",
    "fairytale",
    "classics",
    "festival",
    "presents",
    "academy",
    "family",
    "school",
    "songs",
    "stories",
)


def _looks_like_elb_performer_title(name: str) -> bool:
    normalized = _normalize_text(name)
    if not normalized:
        return False

    if any(normalized.startswith(prefix) for prefix in ELB_EVENT_PREFIXES):
        return False

    if ":" in normalized and " / " not in normalized:
        return False

    if " / " in name:
        return True

    if any(token in normalized for token in ELB_PERFORMER_TOKENS):
        return True

    return bool(re.search(r",\s*[a-z]{2,20}$", normalized))


def _looks_like_person_name_title(name: str) -> bool:
    normalized = _normalize_text(name)
    if not normalized:
        return False
    if any(normalized.startswith(prefix) for prefix in ELB_EVENT_PREFIXES):
        return False
    if any(token in normalized for token in NON_PERSON_NAME_TOKENS):
        return False
    if any(separator in name for separator in ["/", ":", ";"]):
        return False
    if any(char.isdigit() for char in normalized):
        return False

    tokens = [token for token in normalized.split() if token]
    if len(tokens) < 2 or len(tokens) > 3:
        return False
    if any(len(token) < 2 or len(token) > 18 for token in tokens):
        return False
    return True


def _extract_proarte_performers_and_program(name: str, cast: str) -> tuple[str, str]:
    cast_parts = [part.strip() for part in cast.split("|") if part.strip()]

    performer_parts: list[str] = []
    program_parts: list[str] = []
    for part in cast_parts:
        if _looks_like_program_text(part):
            program_parts.append(part)
        else:
            performer_parts.append(part)

    if not performer_parts and _looks_like_performer_name(name):
        performer_parts.append(name)

    if ":" in name and not program_parts:
        program_parts.append(name)

    performers = " | ".join(_unique_parts(performer_parts))
    program = " | ".join(_unique_parts(program_parts))
    return performers, program


def _extract_elb_events(soup: BeautifulSoup, page_url: str) -> list[ConcertData]:
    events: list[ConcertData] = []
    seen_ids: set[str] = set()

    for card in soup.select(".event-item"):
        link = card.select_one("a.event-title[href], a.event-image-link[href], a[href*='/en/whats-on/']")
        if not link:
            continue

        href = link.get("href", "").strip()
        if not href or "/ticket/" in href:
            continue

        full_href = _absolute(page_url, href)
        external_id = full_href
        if external_id in seen_ids:
            continue

        name = _text(card.select_one(".event-title")) or _text(link)
        if not name:
            continue

        subtitle = _text(card.select_one(".event-subtitle"))
        program, performers = _extract_elb_program_and_performers(subtitle)
        if not performers and _looks_like_elb_performer_title(name):
            performers = name
        if not performers and _looks_like_person_list_title(name):
            performers = " / ".join(_unique_parts([part.strip() for part in name.split(";") if part.strip()]))
        if not performers and _looks_like_person_name_title(name):
            performers = name

        performers, performer_format = _extract_performer_and_format_from_text(performers)
        program = _merge_program_text(program, performer_format)

        needs_detail_enrichment = (not program.strip()) or (not performers.strip())
        if needs_detail_enrichment:
            detail_program, detail_performers = _extract_elb_detail_metadata(full_href)
            if detail_program:
                if not program.strip():
                    program = detail_program
                elif len(detail_program) > len(program):
                    program = detail_program
            if detail_performers:
                if performers.strip() == name.strip() and _normalize_text(name) in _normalize_text(detail_performers):
                    performers = detail_performers
                else:
                    performers = _merge_performer_text(performers, detail_performers)

        seen_ids.add(external_id)
        events.append(
            ConcertData(
                source="Elbphilharmonie",
                source_url=full_href,
                external_id=external_id,
                name=name,
                program=program,
                performers=performers,
                hall=_text(card.select_one(".date-and-place .place-cell, .place-cell")),
                date=_text(card.select_one(".date")),
                time=_text(card.select_one(".time")),
            )
        )

    return events


def _find_elb_next_page(soup: BeautifulSoup, page_url: str) -> str | None:
    for anchor in soup.select("a[href]"):
        href = (anchor.get("href") or "").strip()
        if not href:
            continue
        if "/en/whats-on/" not in href:
            continue

        text = _text(anchor).lower()
        if text in {"next", "weiter"}:
            return _absolute(page_url, href)

    return None


def scrape_elbphilharmonie() -> list[ConcertData]:
    start_url = "https://www.elbphilharmonie.de/en/whats-on/"
    events: list[ConcertData] = []
    seen_ids: set[str] = set()
    visited_pages: set[str] = set()
    current_url = start_url

    for _ in range(40):
        if current_url in visited_pages:
            break
        visited_pages.add(current_url)

        response = requests.get(current_url, timeout=30, headers=HEADERS)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")

        page_events = _extract_elb_events(soup, current_url)
        for event in page_events:
            if event.external_id in seen_ids:
                continue
            seen_ids.add(event.external_id)
            events.append(event)

        next_page = _find_elb_next_page(soup, current_url)
        if not next_page:
            break
        current_url = next_page

    return events


def scrape_proarte() -> list[ConcertData]:
    url = "https://www.proarte.de/de/konzerte"
    response = requests.get(url, timeout=30, headers=HEADERS)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")
    events: list[ConcertData] = []
    seen_ids: set[str] = set()

    for card in soup.select("li.event-list-item"):
        link = card.select_one("a.h3[href], a.event-item__image-link[href], a[href*='/de/konzerte/']")
        if not link:
            continue

        href = (link.get("href") or "").strip()
        if not href:
            continue

        full_href = _absolute(url, href)
        external_id = full_href
        if external_id in seen_ids:
            continue

        name = _text(card.select_one("a.h3, .h3")) or _text(link)
        if not name:
            continue

        cast = _text(card.select_one(".cast"))
        venue = _text(card.select_one(".venue"))
        performers, program = _extract_proarte_performers_and_program(name, cast)
        performers, performer_format = _extract_performer_and_format_from_text(performers)
        program = _merge_program_text(program, performer_format)

        preline = _text(card.select_one(".event-item__preline"))
        raw_date_time = _text(card.select_one(".date-time"))
        date = ""
        time = ""
        if raw_date_time:
            date_time_parts = [part.strip() for part in raw_date_time.split("|")]
            if date_time_parts:
                date = date_time_parts[0]
            if len(date_time_parts) > 1:
                time = date_time_parts[1]
        if not date and preline:
            preline_parts = [part.strip() for part in preline.split("|")]
            if preline_parts:
                date = preline_parts[0]
            if len(preline_parts) > 1:
                time = preline_parts[1]

        seen_ids.add(external_id)

        events.append(
            ConcertData(
                source="ProArte",
                source_url=full_href,
                external_id=external_id,
                name=name,
                program=program,
                performers=performers,
                hall=venue,
                date=date,
                time=time,
            )
        )

    return events


def scrape_all() -> list[ConcertData]:
    events = []
    for scraper in (scrape_elbphilharmonie, scrape_proarte):
        try:
            events.extend(scraper())
        except Exception:
            continue
    return events
