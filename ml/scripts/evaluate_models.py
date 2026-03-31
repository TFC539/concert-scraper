import argparse
import json
from pathlib import Path

from common import read_jsonl


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate model on test set (placeholder)")
    parser.add_argument("--model-dir", required=True)
    parser.add_argument("--data", required=True, help="Test JSONL")
    parser.add_argument("--out", required=True, help="Output metrics JSON")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    rows = read_jsonl(Path(args.data))

    metrics = {
        "model_dir": args.model_dir,
        "test_rows": len(rows),
        "f1_performers_target": 0.0,
        "f1_program_target": 0.0,
        "f1_hall_target": 0.0,
        "note": "Placeholder evaluator. Replace with real inference + scoring.",
    }

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    print(json.dumps(metrics, indent=2))


if __name__ == "__main__":
    main()
