import argparse
import json
from pathlib import Path

from common import read_jsonl


def normalize_list(values: list[str]) -> set[str]:
    return {" ".join(v.lower().split()) for v in values if isinstance(v, str) and v.strip()}


def f1(pred: set[str], gold: set[str]) -> float:
    if not pred and not gold:
        return 1.0
    if not pred or not gold:
        return 0.0
    tp = len(pred & gold)
    p = tp / len(pred) if pred else 0.0
    r = tp / len(gold) if gold else 0.0
    if p + r == 0:
        return 0.0
    return 2 * p * r / (p + r)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Score prompt outputs against gold labels")
    parser.add_argument("--gold", required=True, help="Gold labeled JSONL")
    parser.add_argument(
        "--pred",
        required=True,
        help="Predicted JSONL (id + targets with performers_target/program_target/hall_target)",
    )
    parser.add_argument("--out", required=True, help="Output metrics JSON path")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    gold_rows = {r["id"]: r for r in read_jsonl(Path(args.gold))}
    pred_rows = {r["id"]: r for r in read_jsonl(Path(args.pred))}

    fields = ["performers_target", "program_target", "hall_target"]
    sums = {k: 0.0 for k in fields}
    n = 0

    for row_id, gold in gold_rows.items():
        if row_id not in pred_rows:
            continue
        pred = pred_rows[row_id]
        n += 1
        for field in fields:
            g = normalize_list(gold.get("targets", {}).get(field, []))
            p = normalize_list(pred.get("targets", {}).get(field, []))
            sums[field] += f1(p, g)

    metrics = {"count": n}
    for field in fields:
        metrics[f"f1_{field}"] = sums[field] / n if n else 0.0

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    print(json.dumps(metrics, indent=2))


if __name__ == "__main__":
    main()
