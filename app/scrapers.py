from __future__ import annotations

from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor, as_completed
import logging
import re
import unicodedata
from typing import Callable
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup


logger = logging.getLogger(__name__)


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


@dataclass
class ElbDetailMetadata:
    program: str = ""
    performers: str = ""
    hall: str = ""
    date: str = ""
    time: str = ""
    ticketing: str = ""


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


def _merge_text_field(existing: str, extra: str, separator: str = " | ") -> str:
    base = (existing or "").strip()
    addon = (extra or "").strip()
    if not addon:
        return base
    if not base:
        return addon
    if _normalize_text(addon) in _normalize_text(base):
        return base
    if _normalize_text(base) in _normalize_text(addon):
        return addon
    return f"{base}{separator}{addon}"


def _append_labeled_program_context(program: str, label: str, value: str) -> str:
    base = (program or "").strip()
    addon = (value or "").strip()
    if not addon:
        return base

    tagged = f"{label}: {addon}"
    if not base:
        return tagged
    if _normalize_text(tagged) in _normalize_text(base):
        return base
    return f"{base}\n{tagged}"


def _extract_ticketing_from_soup(soup: BeautifulSoup) -> str:
    candidates: list[str] = []

    for node in soup.select(
        "[class*='ticket'], [class*='price'], [class*='booking'], [data-qa*='ticket'], [data-qa*='price']"
    ):
        text = _text(node)
        if text:
            candidates.append(text)

    for text in soup.stripped_strings:
        line = str(text or "").strip()
        if not line:
            continue
        normalized = _normalize_text(line)
        if not normalized:
            continue
        if re.search(r"\bsold\s*-?\s*out\b|\bausverkauft\b|remaining tickets|box office", normalized):
            candidates.append(line)
            continue
        if re.search(r"(?:€|\bEUR\b|\bCHF\b|\$)\s*\d|\d\s*(?:€|\bEUR\b|\bCHF\b|\$)", line):
            candidates.append(line)

    cleaned: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        compact = re.sub(r"\s+", " ", candidate).strip()
        if not compact or len(compact) > 220:
            continue
        lowered = compact.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        cleaned.append(compact)

    return " | ".join(cleaned)


def _extract_elb_detail_metadata(source_url: str) -> ElbDetailMetadata:
    logger.info("elb_detail_fetch_started source_url=%s", source_url)
    try:
        response = requests.get(source_url, timeout=30, headers=HEADERS)
        response.raise_for_status()
    except Exception:
        logger.warning("elb_detail_fetch_failed source_url=%s", source_url, exc_info=True)
        return ElbDetailMetadata()

    soup = BeautifulSoup(response.text, "html.parser")
    soup_ticketing = _extract_ticketing_from_soup(soup)
    root = soup.select_one(".event-detail-content")
    if not root:
        logger.warning("elb_detail_root_missing source_url=%s", source_url)
        return ElbDetailMetadata(
            hall=_text(soup.select_one(".date-and-place .place-cell, .place-cell")),
            date=_text(soup.select_one(".date-and-place .date, .date")),
            time=_text(soup.select_one(".date-and-place .time, .time")),
            ticketing=soup_ticketing,
        )

    detail_hall = _text(soup.select_one(".date-and-place .place-cell, .place-cell"))
    detail_date = _text(soup.select_one(".date-and-place .date, .date"))
    detail_time = _text(soup.select_one(".date-and-place .time, .time"))

    lines = [text.strip() for text in root.stripped_strings if text and text.strip()]

    current_section = ""
    performer_lines: list[str] = []
    program_lines: list[str] = []
    schedule_lines: list[str] = []
    ticket_lines: list[str] = []

    for line in lines:
        normalized = _normalize_text(line)
        if not normalized:
            continue

        if normalized.startswith("performers"):
            current_section = "performers"
            continue
        if normalized.startswith("programme") or normalized.startswith("program"):
            current_section = "program"
            continue
        if normalized.startswith("series") or normalized.startswith("find out more"):
            current_section = ""
            continue

        if normalized.startswith("location"):
            hall_match = re.search(r"location\s*[:\-]\s*(.+)$", line, flags=re.IGNORECASE)
            if hall_match:
                detail_hall = hall_match.group(1).strip()
            continue

        if normalized.startswith("start ") or normalized.startswith("end "):
            schedule_lines.append(line)
            continue

        if re.search(r"\bsold\s*-?\s*out\b|\bausverkauft\b|remaining tickets|ticket", normalized):
            ticket_lines.append(line)

        if current_section == "performers":
            cleaned = _clean_performer_line(line)
            if cleaned and not cleaned.lower().startswith("performers"):
                performer_lines.append(cleaned)
            continue

        if current_section == "program":
            if re.search(r"\b(pdf|kb)\b", normalized):
                continue
            if normalized.startswith("promoter") or normalized.startswith("supported by"):
                continue
            program_lines.append(line)

    program = "\n".join(_unique_parts(program_lines))
    performers = " / ".join(_unique_parts(performer_lines))
    schedule_text = " | ".join(_unique_parts(schedule_lines))
    ticketing = " | ".join(_unique_parts(ticket_lines))
    ticketing = _merge_text_field(ticketing, soup_ticketing)

    merged_time = _merge_text_field(detail_time, schedule_text)
    metadata = ElbDetailMetadata(
        program=program,
        performers=performers,
        hall=detail_hall,
        date=detail_date,
        time=merged_time,
        ticketing=ticketing,
    )
    logger.info(
        "elb_detail_fetch_success source_url=%s performers_lines=%s program_lines=%s has_hall=%s has_date=%s has_time=%s ticketing_entries=%s",
        source_url,
        len(performer_lines),
        len(program_lines),
        bool(metadata.hall),
        bool(metadata.date),
        bool(metadata.time),
        len([entry for entry in ticket_lines if entry.strip()]),
    )
    return metadata


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


def _extract_elb_events(soup: BeautifulSoup, page_url: str, max_events: int | None = None) -> list[ConcertData]:
    events: list[ConcertData] = []
    seen_ids: set[str] = set()

    card_count = len(soup.select(".event-item"))
    logger.info("elb_list_parse_started page_url=%s card_count=%s", page_url, card_count)

    for card in soup.select(".event-item"):
        if max_events is not None and len(events) >= max_events:
            logger.info("elb_list_parse_limit_reached page_url=%s max_events=%s", page_url, max_events)
            break

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
            logger.warning("elb_event_skipped_missing_name page_url=%s event_url=%s", page_url, full_href)
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

        detail = _extract_elb_detail_metadata(full_href)
        if detail.program:
            if not program.strip() or len(detail.program) > len(program):
                program = detail.program
            else:
                program = _append_labeled_program_context(program, "Programme Notes", detail.program)
        if detail.performers:
            if performers.strip() == name.strip() and _normalize_text(name) in _normalize_text(detail.performers):
                performers = detail.performers
            else:
                performers = _merge_performer_text(performers, detail.performers)
        if detail.ticketing:
            program = _append_labeled_program_context(program, "Ticketing", detail.ticketing)

        hall = _merge_text_field(_text(card.select_one(".date-and-place .place-cell, .place-cell")), detail.hall)
        date = _merge_text_field(_text(card.select_one(".date")), detail.date)
        time = _merge_text_field(_text(card.select_one(".time")), detail.time)

        seen_ids.add(external_id)
        events.append(
            ConcertData(
                source="Elbphilharmonie",
                source_url=full_href,
                external_id=external_id,
                name=name,
                program=program,
                performers=performers,
                hall=hall,
                date=date,
                time=time,
            )
        )

        logger.info(
            "elb_event_enriched event_url=%s name=%s performers_len=%s program_len=%s hall=%s date=%s time=%s",
            full_href,
            name,
            len(performers or ""),
            len(program or ""),
            hall,
            date,
            time,
        )

    logger.info("elb_list_parse_complete page_url=%s events=%s", page_url, len(events))
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


def scrape_elbphilharmonie(max_events: int | None = None) -> list[ConcertData]:
    max_events = _normalize_limit(max_events)
    start_url = "https://www.elbphilharmonie.de/en/whats-on/"
    events: list[ConcertData] = []
    seen_ids: set[str] = set()
    visited_pages: set[str] = set()
    current_url = start_url

    logger.info("scrape_source_started source=Elbphilharmonie start_url=%s", start_url)

    for _ in range(40):
        if max_events is not None and len(events) >= max_events:
            logger.info("scrape_source_limit_reached source=Elbphilharmonie max_events=%s", max_events)
            break

        if current_url in visited_pages:
            break
        visited_pages.add(current_url)

        logger.info("scrape_page_fetch_started source=Elbphilharmonie page_url=%s", current_url)
        try:
            response = requests.get(current_url, timeout=30, headers=HEADERS)
            response.raise_for_status()
        except Exception:
            logger.exception("scrape_page_fetch_failed source=Elbphilharmonie page_url=%s", current_url)
            raise
        soup = BeautifulSoup(response.text, "html.parser")

        remaining_for_page = None if max_events is None else max(max_events - len(events), 0)
        page_events = _extract_elb_events(soup, current_url, remaining_for_page)
        for event in page_events:
            if event.external_id in seen_ids:
                continue
            seen_ids.add(event.external_id)
            events.append(event)
            if max_events is not None and len(events) >= max_events:
                break

        next_page = _find_elb_next_page(soup, current_url)
        logger.info(
            "scrape_page_processed source=Elbphilharmonie page_url=%s page_events=%s accumulated_events=%s next_page=%s",
            current_url,
            len(page_events),
            len(events),
            next_page or "",
        )
        if not next_page:
            break
        current_url = next_page

    logger.info("scrape_source_complete source=Elbphilharmonie events=%s pages=%s", len(events), len(visited_pages))
    return events


def scrape_proarte(max_events: int | None = None) -> list[ConcertData]:
    max_events = _normalize_limit(max_events)
    url = "https://www.proarte.de/de/konzerte"
    logger.info("scrape_source_started source=ProArte start_url=%s", url)
    try:
        response = requests.get(url, timeout=30, headers=HEADERS)
        response.raise_for_status()
    except Exception:
        logger.exception("scrape_page_fetch_failed source=ProArte page_url=%s", url)
        raise

    soup = BeautifulSoup(response.text, "html.parser")
    events: list[ConcertData] = []
    seen_ids: set[str] = set()

    for card in soup.select("li.event-list-item"):
        if max_events is not None and len(events) >= max_events:
            logger.info("scrape_source_limit_reached source=ProArte max_events=%s", max_events)
            break

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

        logger.info(
            "proarte_event_collected event_url=%s name=%s performers_len=%s program_len=%s hall=%s date=%s time=%s",
            full_href,
            name,
            len(performers or ""),
            len(program or ""),
            venue,
            date,
            time,
        )

    logger.info("scrape_source_complete source=ProArte events=%s", len(events))
    return events


SCRAPER_REGISTRY: dict[str, Callable[[int | None], list[ConcertData]]] = {
    "Elbphilharmonie": scrape_elbphilharmonie,
    "ProArte": scrape_proarte,
}


def list_scrape_sources() -> list[str]:
    return list(SCRAPER_REGISTRY.keys())


def _normalize_requested_sources(sources: list[str] | None) -> list[str]:
    if not sources:
        return list_scrape_sources()

    available = set(list_scrape_sources())
    normalized: list[str] = []
    for source in sources:
        value = (source or "").strip()
        if not value:
            continue
        if value not in available:
            continue
        if value in normalized:
            continue
        normalized.append(value)

    return normalized or list_scrape_sources()


def _normalize_limit(limit: int | None) -> int | None:
    if limit is None:
        return None
    if limit <= 0:
        return None
    return limit


def scrape_all(
    sources: list[str] | None = None,
    max_per_source: int | None = None,
    max_total: int | None = None,
) -> list[ConcertData]:
    selected_sources = _normalize_requested_sources(sources)
    per_source_limit = _normalize_limit(max_per_source)
    total_limit = _normalize_limit(max_total)

    events: list[ConcertData] = []
    results_by_source: dict[str, list[ConcertData]] = {}

    # Bound each source so a small global max_total does not trigger full-source retrieval.
    source_limit = per_source_limit
    if source_limit is None and total_limit is not None:
        source_limit = total_limit

    logger.info(
        "scrape_all_dispatch_started selected_sources=%s source_limit=%s max_total=%s",
        selected_sources,
        source_limit,
        total_limit,
    )

    with ThreadPoolExecutor(max_workers=max(1, len(selected_sources))) as executor:
        future_to_source = {
            executor.submit(SCRAPER_REGISTRY[source], source_limit): source for source in selected_sources
        }

        for future in as_completed(future_to_source):
            source = future_to_source[future]
            scraper = SCRAPER_REGISTRY[source]
            try:
                source_events = future.result()
                results_by_source[source] = source_events
                logger.info(
                    "scrape_source_future_complete source=%s fetched=%s",
                    source,
                    len(source_events),
                )
            except Exception:
                logger.exception("scrape_source_failed scraper=%s", scraper.__name__)
                results_by_source[source] = []

    for source in selected_sources:
        source_events = results_by_source.get(source, [])

        if per_source_limit is not None:
            source_events = source_events[:per_source_limit]

        if total_limit is not None:
            remaining = max(total_limit - len(events), 0)
            if remaining == 0:
                break
            source_events = source_events[:remaining]

        events.extend(source_events)
        logger.info(
            "scrape_source_collected source=%s selected=%s total_so_far=%s",
            source,
            len(source_events),
            len(events),
        )

        if total_limit is not None and len(events) >= total_limit:
            break

    logger.info(
        "scrape_all_complete total_events=%s selected_sources=%s max_per_source=%s max_total=%s",
        len(events),
        selected_sources,
        per_source_limit,
        total_limit,
    )
    return events
