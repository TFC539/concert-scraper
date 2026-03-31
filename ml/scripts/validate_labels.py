import argparse
from pathlib import Path

from common import read_jsonl


REQUIRED_TOP = ["id", "text", "targets"]
REQUIRED_TARGETS = ["performers_target", "program_target", "hall_target"]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate labeled examples schema")
    parser.add_argument("--input", required=True, help="Labeled JSONL file")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    rows = read_jsonl(Path(args.input))

    errors: list[str] = []
    for i, row in enumerate(rows):
        for key in REQUIRED_TOP:
            if key not in row:
                errors.append(f"row {i}: missing top-level key '{key}'")

        targets = row.get("targets", {})
        if not isinstance(targets, dict):
            errors.append(f"row {i}: targets must be object")
            continue

        for key in REQUIRED_TARGETS:
            if key not in targets:
                errors.append(f"row {i}: missing targets key '{key}'")
                continue
            if not isinstance(targets[key], list):
                errors.append(f"row {i}: targets.{key} must be list")

    if errors:
        print("Validation failed:")
        for e in errors[:200]:
            print(f"- {e}")
        raise SystemExit(1)

    print(f"Validation OK for {len(rows)} rows")


if __name__ == "__main__":
    main()
