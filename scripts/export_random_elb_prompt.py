from __future__ import annotations

import argparse
import random
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urljoin
import re

import requests
from bs4 import BeautifulSoup

# Ensure imports work when running this file as: python scripts/export_random_elb_prompt.py
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.openrouter_client import _build_messages

START_URL = "https://www.elbphilharmonie.de/en/whats-on/"
HEADERS = {"User-Agent": "concert-dashboard-bot/1.0 (+https://localhost)"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Export OpenRouter prompt text using one random Elbphilharmonie concert page"
    )
    parser.add_argument(
        "--out",
        default="logs/random_elb_prompt.txt",
        help="Output TXT path (default: logs/random_elb_prompt.txt)",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=None,
        help="Optional random seed for reproducible picks",
    )
    parser.add_argument(
        "--max-paragraphs",
        type=int,
        default=4,
        help="Max detail paragraphs to include in excerpt (default: 4)",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=30,
        help="HTTP timeout in seconds (default: 30)",
    )
    return parser.parse_args()


def fetch_html(url: str, timeout: int) -> str:
    response = requests.get(url, headers=HEADERS, timeout=timeout)
    response.raise_for_status()
    return response.text


def text_or_empty(node: Any) -> str:
    return node.get_text(" ", strip=True) if node else ""


def find_event_links(index_html: str) -> list[str]:
    soup = BeautifulSoup(index_html, "html.parser")
    links: list[str] = []
    seen: set[str] = set()

    for card in soup.select(".event-item"):
        link = card.select_one("a.event-title[href], a.event-image-link[href], a[href*='/en/whats-on/']")
        if not link:
            continue

        href = (link.get("href") or "").strip()
        if not href or "/ticket/" in href:
            continue

        full_url = urljoin(START_URL, href)
        if full_url in seen:
            continue

        seen.add(full_url)
        links.append(full_url)

    return links


def extract_event_fields(event_html: str, event_url: str, max_paragraphs: int) -> dict[str, str]:
    soup = BeautifulSoup(event_html, "html.parser")

    name = text_or_empty(soup.select_one("h1, .event-title"))
    subtitle = text_or_empty(soup.select_one(".event-subtitle"))
    venue = text_or_empty(soup.select_one(".date-and-place .place-cell, .place-cell"))
    date = text_or_empty(soup.select_one(".date"))
    time = text_or_empty(soup.select_one(".time"))

    detail_root = soup.select_one(".event-detail-content")
    paragraphs: list[str] = []
    if detail_root:
        for paragraph in detail_root.select("p"):
            if paragraph.get("class"):
                continue
            text = paragraph.get_text(" ", strip=True)
            if len(text) < 40:
                continue
            paragraphs.append(text)
            if len(paragraphs) >= max(1, max_paragraphs):
                break

    excerpt = "\n\n".join(paragraphs)

    performers_lines: list[str] = []
    programme_lines: list[str] = []
    schedule_lines: list[str] = []
    ticketing_lines: list[str] = []

    # Collect ticket/price hints from broader page nodes first.
    for node in soup.select(
        "[class*='ticket'], [class*='price'], [class*='booking'], [data-qa*='ticket'], [data-qa*='price']"
    ):
        text = text_or_empty(node)
        if text:
            ticketing_lines.append(text)

    if detail_root:
        current_section = ""
        for raw_line in detail_root.stripped_strings:
            line = str(raw_line or "").strip()
            if not line:
                continue
            normalized = re.sub(r"\s+", " ", line).strip().lower()

            if normalized.startswith("performers"):
                current_section = "performers"
                continue
            if normalized.startswith("programme") or normalized.startswith("program"):
                current_section = "programme"
                continue
            if normalized.startswith("series") or normalized.startswith("find out more"):
                current_section = ""
                continue
            if normalized.startswith("location"):
                match = re.search(r"location\s*[:\-]\s*(.+)$", line, flags=re.IGNORECASE)
                if match:
                    venue = match.group(1).strip()
                continue

            if normalized.startswith("start ") or normalized.startswith("end "):
                schedule_lines.append(line)
                continue

            if re.search(r"\bsold\s*-?\s*out\b|remaining tickets|\b€\b|\beur\b|\bchf\b|\$", normalized):
                ticketing_lines.append(line)

            if current_section == "performers":
                if not normalized.startswith("performers"):
                    performers_lines.append(line)
                continue
            if current_section == "programme":
                if re.search(r"\b(pdf|kb)\b", normalized):
                    continue
                programme_lines.append(line)

    if schedule_lines:
        time = " | ".join(schedule_lines)

    # Fallback scan over full page text for price/ticket lines.
    for raw_line in soup.stripped_strings:
        line = str(raw_line or "").strip()
        if not line:
            continue
        normalized = re.sub(r"\s+", " ", line).strip().lower()
        if re.search(r"\bsold\s*-?\s*out\b|remaining tickets|box office", normalized):
            ticketing_lines.append(line)
            continue
        if re.search(r"(?:€|\beur\b|\bchf\b|\$)\s*\d|\d\s*(?:€|\beur\b|\bchf\b|\$)", line, flags=re.IGNORECASE):
            ticketing_lines.append(line)

    if not name:
        name = text_or_empty(soup.select_one("title"))

    deduped_ticketing: list[str] = []
    seen_ticketing: set[str] = set()
    for line in ticketing_lines:
        compact = re.sub(r"\s+", " ", str(line or "")).strip()
        if not compact or len(compact) > 220:
            continue
        key = compact.casefold()
        if key in seen_ticketing:
            continue
        seen_ticketing.add(key)
        deduped_ticketing.append(compact)

    return {
        "name": name,
        "subtitle": subtitle,
        "venue": venue,
        "date": date,
        "time": time,
        "excerpt": excerpt,
        "performers": "\n".join(performers_lines),
        "programme": "\n".join(programme_lines),
        "ticketing": " | ".join(deduped_ticketing),
        "source_url": event_url,
    }


def build_raw_text(fields: dict[str, str]) -> str:
    performers = fields.get("performers", "").strip()
    programme = fields.get("programme", "").strip()
    subtitle = fields.get("subtitle", "").strip()
    ticketing = fields.get("ticketing", "").strip()

    performer_lines = [line for line in performers.splitlines() if line.strip()]
    programme_lines = [line for line in programme.splitlines() if line.strip()]

    performer_block = [f"- {line}" for line in performer_lines] if performer_lines else ["- "]
    if programme_lines:
        programme_block = [f"- {line}" for line in programme_lines]
    elif subtitle:
        programme_block = [f"- {subtitle}"]
    else:
        programme_block = ["- "]

    return "\n".join(
        [
            "Event Metadata:",
            f"Name: {fields.get('name', '')}",
            f"Venue: {fields.get('venue', '')}",
            f"Date: {fields.get('date', '')}",
            f"Time: {fields.get('time', '')}",
            "Source: Elbphilharmonie",
            f"Source URL: {fields.get('source_url', '')}",
            "",
            "Performers:",
        ]
        + performer_block
        + [
            "",
            "Programme:",
        ]
        + programme_block
        + [
            "",
            f"Ticketing: {ticketing}",
            "",
            "Excerpt:",
            fields.get("excerpt", ""),
        ]
    ).strip()


def write_prompt_preview(out_path: Path, source_url: str, raw_text: str, messages: list[dict[str, str]]) -> None:
    now = datetime.now(timezone.utc).isoformat()
    content = (
        f"Generated at: {now}\n"
        f"Source URL: {source_url}\n\n"
        "# System Prompt\n\n"
        f"{messages[0]['content']}\n\n"
        "# User Prompt\n\n"
        f"{messages[1]['content']}\n\n"
        "# Raw Extraction Text\n\n"
        f"{raw_text}\n"
    )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(content, encoding="utf-8")


def main() -> None:
    args = parse_args()

    if args.seed is not None:
        random.seed(args.seed)

    index_html = fetch_html(START_URL, timeout=args.timeout)
    links = find_event_links(index_html)
    if not links:
        raise SystemExit("No event links found on Elbphilharmonie whats-on page")

    selected_url = random.choice(links)
    event_html = fetch_html(selected_url, timeout=args.timeout)
    fields = extract_event_fields(event_html, selected_url, max_paragraphs=args.max_paragraphs)

    raw_text = build_raw_text(fields)
    messages = _build_messages(raw_text)

    out_path = Path(args.out)
    write_prompt_preview(out_path, selected_url, raw_text, messages)

    print(f"Selected event: {selected_url}")
    print(f"Wrote prompt preview to: {out_path.resolve()}")


if __name__ == "__main__":
    main()
