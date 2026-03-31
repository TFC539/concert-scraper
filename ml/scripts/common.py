import json
from pathlib import Path
from typing import Any, Iterable

import yaml


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows


def write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def load_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def normalize_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return " ".join(value.split())
    return str(value)


def split_multivalue(value: str) -> list[str]:
    if not value:
        return []
    normalized = value.replace(";", ",")
    parts = [p.strip() for p in normalized.split(",")]
    return [p for p in parts if p]


def build_model_text(record: dict[str, Any]) -> str:
    chunks = [
        f"Name: {normalize_text(record.get('name'))}",
        f"Program: {normalize_text(record.get('program'))}",
        f"Performers: {normalize_text(record.get('performers'))}",
        f"Hall: {normalize_text(record.get('hall'))}",
        f"Source: {normalize_text(record.get('source'))}",
    ]
    return "\n".join(chunks)
