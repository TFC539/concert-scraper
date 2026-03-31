import argparse
import json
from pathlib import Path

from datasets import Dataset
from transformers import (
    AutoModelForSeq2SeqLM,
    AutoTokenizer,
    DataCollatorForSeq2Seq,
    Trainer,
    TrainingArguments,
)

from common import read_jsonl


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train seq2seq transformer from JSONL")
    parser.add_argument("--train-file", required=True, help="JSONL with input_text and target_text")
    parser.add_argument("--val-file", default="", help="Optional JSONL with input_text and target_text")
    parser.add_argument("--model-name", default="google/flan-t5-small")
    parser.add_argument("--epochs", type=int, default=3)
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--lr", type=float, default=5e-5)
    parser.add_argument("--max-input-length", type=int, default=512)
    parser.add_argument("--max-target-length", type=int, default=256)
    parser.add_argument("--out-dir", required=True, help="Output model directory")
    return parser.parse_args()


def _ensure_pair_schema(rows: list[dict]) -> list[dict]:
    out: list[dict] = []
    for i, row in enumerate(rows):
        if "input_text" not in row or "target_text" not in row:
            raise ValueError(f"Row {i} missing input_text or target_text")
        out.append(
            {
                "input_text": str(row["input_text"]),
                "target_text": str(row["target_text"]),
            }
        )
    if not out:
        raise ValueError("Dataset is empty")
    return out


def main() -> None:
    args = parse_args()
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    train_rows = _ensure_pair_schema(read_jsonl(Path(args.train_file)))
    val_rows: list[dict] = []
    if args.val_file:
        val_rows = _ensure_pair_schema(read_jsonl(Path(args.val_file)))

    train_ds = Dataset.from_list(train_rows)
    val_ds = Dataset.from_list(val_rows) if val_rows else None

    tokenizer = AutoTokenizer.from_pretrained(args.model_name)
    model = AutoModelForSeq2SeqLM.from_pretrained(args.model_name)

    def preprocess(batch: dict) -> dict:
        model_inputs = tokenizer(
            batch["input_text"],
            max_length=args.max_input_length,
            truncation=True,
        )
        labels = tokenizer(
            text_target=batch["target_text"],
            max_length=args.max_target_length,
            truncation=True,
        )
        model_inputs["labels"] = labels["input_ids"]
        return model_inputs

    tokenized_train = train_ds.map(preprocess, batched=True)
    tokenized_val = val_ds.map(preprocess, batched=True) if val_ds is not None else None

    data_collator = DataCollatorForSeq2Seq(tokenizer=tokenizer, model=model)

    common_train_args = {
        "output_dir": str(out_dir),
        "learning_rate": args.lr,
        "per_device_train_batch_size": args.batch_size,
        "per_device_eval_batch_size": args.batch_size,
        "num_train_epochs": args.epochs,
        "weight_decay": 0.01,
        "save_total_limit": 2,
        "logging_steps": 25,
        "save_strategy": "epoch",
        "report_to": [],
        "fp16": False,
    }

    eval_value = "epoch" if tokenized_val is not None else "no"
    try:
        training_args = TrainingArguments(
            **common_train_args,
            evaluation_strategy=eval_value,
        )
    except TypeError:
        training_args = TrainingArguments(
            **common_train_args,
            eval_strategy=eval_value,
        )

    trainer_kwargs = {
        "model": model,
        "args": training_args,
        "train_dataset": tokenized_train,
        "eval_dataset": tokenized_val,
        "data_collator": data_collator,
    }

    try:
        trainer = Trainer(
            **trainer_kwargs,
            tokenizer=tokenizer,
        )
    except TypeError:
        trainer = Trainer(
            **trainer_kwargs,
            processing_class=tokenizer,
        )

    train_result = trainer.train()
    trainer.save_model(str(out_dir))
    tokenizer.save_pretrained(str(out_dir))

    metrics: dict = {
        "train": train_result.metrics,
    }
    if tokenized_val is not None:
        metrics["eval"] = trainer.evaluate()

    config = {
        "model_name": args.model_name,
        "epochs": args.epochs,
        "batch_size": args.batch_size,
        "lr": args.lr,
        "train_file": args.train_file,
        "val_file": args.val_file,
        "max_input_length": args.max_input_length,
        "max_target_length": args.max_target_length,
        "status": "trained",
        "metrics": metrics,
    }

    (out_dir / "model_config.json").write_text(json.dumps(config, indent=2), encoding="utf-8")
    print(f"Training complete. Artifacts in {out_dir}")


if __name__ == "__main__":
    main()
