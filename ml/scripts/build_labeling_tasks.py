import argparse
from pathlib import Path

from common import build_model_text, normalize_text, split_multivalue, read_jsonl, write_jsonl


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build labeling task JSONL from records")
    parser.add_argument("--input", required=True, help="Input JSONL")
    parser.add_argument("--out", required=True, help="Output task JSONL")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    rows = read_jsonl(Path(args.input))

    tasks = []
    for row in rows:
        task = {
            "id": row.get("id"),
            "source": normalize_text(row.get("source")),
            "name": normalize_text(row.get("name")),
            "date": normalize_text(row.get("date")),
            "time": normalize_text(row.get("time")),
            "hall": normalize_text(row.get("hall")),
            "text": build_model_text(row),
            "context": {
                "name": normalize_text(row.get("name")),
                "program": normalize_text(row.get("program")),
                "performers": normalize_text(row.get("performers")),
                "hall": normalize_text(row.get("hall")),
            },
            "targets": {
                "performers_target": split_multivalue(normalize_text(row.get("performers"))),
                "program_target": [normalize_text(row.get("program"))] if normalize_text(row.get("program")) else [],
                "hall_target": [normalize_text(row.get("hall"))] if normalize_text(row.get("hall")) else [],
                "format_target": "",
                "notes": "",
            },
        }
        tasks.append(task)

    write_jsonl(Path(args.out), tasks)
    print(f"Created {len(tasks)} label tasks")


if __name__ == "__main__":
    main()
