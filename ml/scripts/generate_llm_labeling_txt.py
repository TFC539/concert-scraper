import argparse
import json
from pathlib import Path

from common import build_model_text, normalize_text, read_jsonl


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate one TXT containing full labeling prompt and all records"
    )
    parser.add_argument("--input", required=True, help="Input raw concerts JSONL")
    parser.add_argument("--out", required=True, help="Output TXT path")
    parser.add_argument("--limit", type=int, default=0, help="Optional max records")
    return parser.parse_args()


def build_header() -> str:
    schema = {
        "id": 123,
        "performers_target": ["..."],
        "program_target": ["..."],
        "hall_target": ["..."],
    }
    parts = [
        "You are a data labeling assistant for concert metadata extraction.",
        "",
        "Return ONLY valid JSON as an array. No markdown. No explanation.",
        "",
        "Required output item schema:",
        json.dumps(schema, ensure_ascii=False, indent=2),
        "",
        "Rules:",
        "1) performers_target: people, orchestras, ensembles, choirs, bands.",
        "2) program_target: works, repertoire, recital/program themes, event descriptions.",
        "3) hall_target: venue/hall/location only.",
        "4) Use only provided text. No hallucinations.",
        "",
        "Process all records below and return one JSON array with one item per record id.",
        "",
    ]
    return "\n".join(parts)


def build_record_block(row: dict) -> str:
    record = {
        "id": row.get("id"),
        "source": normalize_text(row.get("source")),
        "date": normalize_text(row.get("date")),
        "time": normalize_text(row.get("time")),
        "text": build_model_text(row),
    }
    return json.dumps(record, ensure_ascii=False, indent=2)


def main() -> None:
    args = parse_args()
    rows = read_jsonl(Path(args.input))
    if args.limit and args.limit > 0:
        rows = rows[: args.limit]

    chunks = [build_header()]
    for row in rows:
        chunks.append(build_record_block(row))
        chunks.append("")

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(chunks), encoding="utf-8")

    print(f"Wrote prompt TXT with {len(rows)} records to {out_path}")


if __name__ == "__main__":
    main()
