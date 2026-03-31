from __future__ import annotations

from dataclasses import dataclass

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
    date: str
    time: str


HEADERS = {
    "User-Agent": "concert-dashboard-bot/1.0 (+https://localhost)"
}


def _text(node) -> str:
    return node.get_text(" ", strip=True) if node else ""


def scrape_elbphilharmonie() -> list[ConcertData]:
    url = "https://www.elbphilharmonie.de/en/whats-on"
    response = requests.get(url, timeout=30, headers=HEADERS)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")
    events = []

    for card in soup.select("article, .event, .event-tile"):
        name = _text(card.select_one("h2, h3, .event-title"))
        date = _text(card.select_one("time, .event-date"))
        time = _text(card.select_one(".event-time"))
        program = _text(card.select_one(".program, .event-subtitle, .description"))
        performers = _text(card.select_one(".performers, .artists"))
        link = card.select_one("a[href]")
        href = link["href"] if link else url

        if not name:
            continue

        if href.startswith("/"):
            href = f"https://www.elbphilharmonie.de{href}"

        external_id = href
        events.append(
            ConcertData(
                source="Elbphilharmonie",
                source_url=href,
                external_id=external_id,
                name=name,
                program=program,
                performers=performers,
                date=date,
                time=time,
            )
        )

    return events


def scrape_proarte() -> list[ConcertData]:
    url = "https://www.proarte.de/veranstaltungen/"
    response = requests.get(url, timeout=30, headers=HEADERS)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")
    events = []

    for card in soup.select("article, .event, .veranstaltung"):
        name = _text(card.select_one("h2, h3, .title"))
        date = _text(card.select_one("time, .date"))
        time = _text(card.select_one(".time"))
        program = _text(card.select_one(".subtitle, .description"))
        performers = _text(card.select_one(".performer, .artists"))
        link = card.select_one("a[href]")
        href = link["href"] if link else url

        if not name:
            continue

        if href.startswith("/"):
            href = f"https://www.proarte.de{href}"

        external_id = href
        events.append(
            ConcertData(
                source="ProArte",
                source_url=href,
                external_id=external_id,
                name=name,
                program=program,
                performers=performers,
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
