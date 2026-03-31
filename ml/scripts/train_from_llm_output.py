import argparse
import json
import random
from pathlib import Path

from common import build_model_text, read_jsonl, write_jsonl


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build supervised training pairs from LLM JSON output and start training"
    )
    parser.add_argument("--raw-input", required=True, help="Raw concerts JSONL")
    parser.add_argument("--llm-json", required=True, help="LLM output JSON file")
    parser.add_argument("--work-dir", default="data/processed/llm_supervised")
    parser.add_argument("--out-dir", required=True, help="Model output directory")
    parser.add_argument("--model-name", default="google/flan-t5-small")
    parser.add_argument("--epochs", type=int, default=3)
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--lr", type=float, default=5e-5)
    parser.add_argument("--train-ratio", type=float, default=0.9)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--max-input-length", type=int, default=512)
    parser.add_argument("--max-target-length", type=int, default=256)
    return parser.parse_args()


def _load_llm_json(path: Path) -> list[dict]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, dict):
        if "records" in payload and isinstance(payload["records"], list):
            return payload["records"]
        raise ValueError("If LLM JSON is an object, it must contain 'records': [...]")
    if isinstance(payload, list):
        return payload
    raise ValueError("LLM JSON must be either an array or an object with 'records'")


def _normalize_label_item(item: dict) -> dict:
    if "id" not in item:
        raise ValueError("Each label item must include 'id'")

    def as_list(key: str) -> list[str]:
        value = item.get(key, [])
        if value is None:
            return []
        if not isinstance(value, list):
            raise ValueError(f"Field '{key}' must be a list")
        out: list[str] = []
        for part in value:
            text = str(part).strip()
            if text:
                out.append(text)
        return out

    return {
        "id": int(item["id"]),
        "performers_target": as_list("performers_target"),
        "program_target": as_list("program_target"),
        "hall_target": as_list("hall_target"),
    }


def _prompt_input(text: str) -> str:
    return (
        "Extract performers_target, program_target and hall_target as JSON from this concert record.\n"
        "Return structured JSON fields only.\n\n"
        f"{text}"
    )


def _target_json(item: dict) -> str:
    payload = {
        "performers_target": item["performers_target"],
        "program_target": item["program_target"],
        "hall_target": item["hall_target"],
    }
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def _build_pairs(raw_rows: list[dict], labels: list[dict]) -> list[dict]:
    by_id = {int(r["id"]): r for r in raw_rows if r.get("id") is not None}
    pairs: list[dict] = []

    for label in labels:
        row = by_id.get(label["id"])
        if row is None:
            continue

        input_text = _prompt_input(build_model_text(row))
        target_text = _target_json(label)
        pairs.append(
            {
                "id": label["id"],
                "input_text": input_text,
                "target_text": target_text,
            }
        )

    if not pairs:
        raise ValueError("No trainable pairs created. Check ID overlap between raw and LLM JSON.")
    return pairs


def main() -> None:
    args = parse_args()

    raw_rows = read_jsonl(Path(args.raw_input))
    llm_items_raw = _load_llm_json(Path(args.llm_json))
    llm_items = [_normalize_label_item(item) for item in llm_items_raw]

    pairs = _build_pairs(raw_rows, llm_items)
    random.Random(args.seed).shuffle(pairs)

    n_train = max(1, int(len(pairs) * args.train_ratio))
    n_train = min(n_train, len(pairs) - 1) if len(pairs) > 1 else len(pairs)

    train_rows = pairs[:n_train]
    val_rows = pairs[n_train:] if len(pairs) > 1 else []

    work_dir = Path(args.work_dir)
    train_file = work_dir / "train.jsonl"
    val_file = work_dir / "val.jsonl"

    write_jsonl(train_file, train_rows)
    if val_rows:
        write_jsonl(val_file, val_rows)

    from train_transformer_ner import main as train_main
    import sys

    argv = [
        "train_transformer_ner.py",
        "--train-file",
        str(train_file),
        "--out-dir",
        args.out_dir,
        "--model-name",
        args.model_name,
        "--epochs",
        str(args.epochs),
        "--batch-size",
        str(args.batch_size),
        "--lr",
        str(args.lr),
        "--max-input-length",
        str(args.max_input_length),
        "--max-target-length",
        str(args.max_target_length),
    ]
    if val_rows:
        argv.extend(["--val-file", str(val_file)])

    old_argv = sys.argv[:]
    try:
        sys.argv = argv
        train_main()
    finally:
        sys.argv = old_argv

    print(
        "Prepared and trained from LLM output. "
        f"pairs={len(pairs)} train={len(train_rows)} val={len(val_rows)} out={args.out_dir}"
    )


if __name__ == "__main__":
    main()
