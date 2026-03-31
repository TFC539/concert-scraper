import argparse
from pathlib import Path

from common import read_jsonl, write_jsonl, split_multivalue


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run batch inference (placeholder)")
    parser.add_argument("--model-dir", required=True)
    parser.add_argument("--input", required=True, help="Input JSONL with raw records")
    parser.add_argument("--out", required=True, help="Output JSONL predictions")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    rows = read_jsonl(Path(args.input))

    preds = []
    for row in rows:
        preds.append(
            {
                "id": row.get("id"),
                "targets": {
                    "performers_target": split_multivalue(str(row.get("performers", ""))),
                    "program_target": [str(row.get("program", ""))] if row.get("program") else [],
                    "hall_target": [str(row.get("hall", ""))] if row.get("hall") else [],
                },
                "meta": {
                    "model_dir": args.model_dir,
                    "mode": "placeholder",
                },
            }
        )

    write_jsonl(Path(args.out), preds)
    print(f"Wrote {len(preds)} predictions to {args.out}")


if __name__ == "__main__":
    main()
