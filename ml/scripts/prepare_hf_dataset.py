import argparse
from pathlib import Path

from common import read_jsonl, write_jsonl


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Prepare simple HF-style train/val/test jsonl")
    parser.add_argument("--input", required=True, help="Labeled JSONL")
    parser.add_argument("--out-dir", required=True, help="Output dir")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--train", type=float, default=0.8)
    parser.add_argument("--val", type=float, default=0.1)
    parser.add_argument("--test", type=float, default=0.1)
    return parser.parse_args()


def flatten_targets(row: dict) -> dict:
    targets = row.get("targets", {})
    return {
        "id": row.get("id"),
        "text": row.get("text", ""),
        "performers_target": targets.get("performers_target", []),
        "program_target": targets.get("program_target", []),
        "hall_target": targets.get("hall_target", []),
    }


def main() -> None:
    args = parse_args()
    rows = [flatten_targets(r) for r in read_jsonl(Path(args.input))]

    # Reuse split_data logic without importing random twice in another utility file.
    import random

    if round(args.train + args.val + args.test, 6) != 1.0:
        raise ValueError("train + val + test must equal 1.0")

    random.Random(args.seed).shuffle(rows)
    n = len(rows)
    n_train = int(n * args.train)
    n_val = int(n * args.val)

    out_dir = Path(args.out_dir)
    write_jsonl(out_dir / "train.jsonl", rows[:n_train])
    write_jsonl(out_dir / "val.jsonl", rows[n_train : n_train + n_val])
    write_jsonl(out_dir / "test.jsonl", rows[n_train + n_val :])

    print(f"Prepared dataset in {out_dir} with {n} rows")


if __name__ == "__main__":
    main()
