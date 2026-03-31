from pathlib import Path
from typing import Any


def load_model(model_dir: str | Path) -> dict[str, Any]:
    model_path = Path(model_dir)
    if not model_path.exists():
        raise FileNotFoundError(f"Model path not found: {model_dir}")
    return {"model_dir": str(model_path), "mode": "placeholder"}


def _split_values(value: str) -> list[str]:
    if not value:
        return []
    normalized = value.replace(";", ",")
    return [v.strip() for v in normalized.split(",") if v.strip()]


def enrich_record(record: dict[str, Any], bundle: dict[str, Any]) -> dict[str, Any]:
    # Placeholder behavior mirrors current rule-based fields until real model inference is wired.
    performers = _split_values(str(record.get("performers", "")))
    program = [str(record.get("program", ""))] if record.get("program") else []
    hall = [str(record.get("hall", ""))] if record.get("hall") else []

    return {
        "id": record.get("id"),
        "predictions": {
            "performers_target": performers,
            "program_target": program,
            "hall_target": hall,
        },
        "meta": bundle,
    }
