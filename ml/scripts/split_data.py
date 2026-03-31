import argparse
import random
from pathlib import Path

from common import read_jsonl, write_jsonl


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create train/val/test split from JSONL")
    parser.add_argument("--input", required=True, help="Input JSONL")
    parser.add_argument("--out-dir", required=True, help="Output directory")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--train", type=float, default=0.8)
    parser.add_argument("--val", type=float, default=0.1)
    parser.add_argument("--test", type=float, default=0.1)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if round(args.train + args.val + args.test, 6) != 1.0:
        raise ValueError("train + val + test must equal 1.0")

    rows = read_jsonl(Path(args.input))
    random.Random(args.seed).shuffle(rows)

    n = len(rows)
    n_train = int(n * args.train)
    n_val = int(n * args.val)

    train_rows = rows[:n_train]
    val_rows = rows[n_train : n_train + n_val]
    test_rows = rows[n_train + n_val :]

    out_dir = Path(args.out_dir)
    write_jsonl(out_dir / "train.jsonl", train_rows)
    write_jsonl(out_dir / "val.jsonl", val_rows)
    write_jsonl(out_dir / "test.jsonl", test_rows)

    print(
        f"Split complete. train={len(train_rows)} val={len(val_rows)} test={len(test_rows)}"
    )


if __name__ == "__main__":
    main()
