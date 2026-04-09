from __future__ import annotations

import argparse
import random
import sys
from datetime import datetime, timezone
from pathlib import Path

# Ensure imports work when running this file as: python scripts/export_random_elb_prompts.py
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.openrouter_client import _build_messages
from scripts.export_random_elb_prompt import (
    START_URL,
    build_raw_text,
    extract_event_fields,
    fetch_html,
    find_event_links,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Export multiple OpenRouter prompt texts from random Elbphilharmonie event pages"
    )
    parser.add_argument(
        "--out",
        default="logs/random_elb_prompts.txt",
        help="Output TXT path (default: logs/random_elb_prompts.txt)",
    )
    parser.add_argument(
        "--count",
        type=int,
        default=10,
        help="Number of prompts to export (default: 10)",
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
        help="Max detail paragraphs to include in excerpt per prompt (default: 4)",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=30,
        help="HTTP timeout in seconds (default: 30)",
    )
    return parser.parse_args()


def _pick_event_urls(links: list[str], count: int) -> tuple[list[str], bool]:
    if count <= len(links):
        return random.sample(links, count), False

    selected = random.sample(links, len(links))
    selected.extend(random.choices(links, k=count - len(links)))
    return selected, True


def _render_prompt_block(index: int, total: int, source_url: str, raw_text: str, messages: list[dict[str, str]]) -> str:
    generated_at = datetime.now(timezone.utc).isoformat()
    return (
        f"=== Prompt {index}/{total} ===\n"
        f"Generated at: {generated_at}\n"
        f"Source URL: {source_url}\n\n"
        "# System Prompt\n\n"
        f"{messages[0]['content']}\n\n"
        "# User Prompt\n\n"
        f"{messages[1]['content']}\n\n"
        "# Raw Extraction Text\n\n"
        f"{raw_text}\n"
    )


def main() -> None:
    args = parse_args()

    count = max(1, int(args.count))
    if args.seed is not None:
        random.seed(args.seed)

    index_html = fetch_html(START_URL, timeout=args.timeout)
    links = find_event_links(index_html)
    if not links:
        raise SystemExit("No event links found on Elbphilharmonie whats-on page")

    selected_urls, used_replacement = _pick_event_urls(links, count)

    blocks: list[str] = []
    failed_urls: list[str] = []

    for idx, url in enumerate(selected_urls, start=1):
        try:
            event_html = fetch_html(url, timeout=args.timeout)
            fields = extract_event_fields(event_html, url, max_paragraphs=args.max_paragraphs)
            raw_text = build_raw_text(fields)
            messages = _build_messages(raw_text)
            blocks.append(_render_prompt_block(idx, count, url, raw_text, messages))
        except Exception:
            failed_urls.append(url)

    if not blocks:
        raise SystemExit("Failed to build prompts: all selected event pages failed to export")

    header_lines = [
        f"Batch generated at: {datetime.now(timezone.utc).isoformat()}",
        f"Requested prompts: {count}",
        f"Exported prompts: {len(blocks)}",
        f"Selection source: {START_URL}",
    ]
    if used_replacement:
        header_lines.append("Note: Requested count exceeded available unique links; sampling used replacement.")
    if failed_urls:
        header_lines.append(f"Failed URLs: {len(failed_urls)}")

    separator = "\n\n" + ("=" * 90) + "\n\n"
    content = "\n".join(header_lines) + separator + separator.join(blocks)

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(content, encoding="utf-8")

    print(f"Wrote {len(blocks)} prompts to: {out_path.resolve()}")
    if failed_urls:
        print("Some URLs failed during export:")
        for failed in failed_urls:
            print(f"- {failed}")


if __name__ == "__main__":
    main()
