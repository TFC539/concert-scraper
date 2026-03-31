import argparse
import os
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Activate model artifacts for production")
    parser.add_argument("--model-dir", required=True)
    parser.add_argument("--active-link", required=True, help="Symlink path that points to active model")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    model_dir = Path(args.model_dir).resolve()
    active_link = Path(args.active_link)

    if not model_dir.exists() or not model_dir.is_dir():
        raise FileNotFoundError(f"Model dir not found: {model_dir}")

    active_link.parent.mkdir(parents=True, exist_ok=True)
    if active_link.exists() or active_link.is_symlink():
        if active_link.is_dir() and not active_link.is_symlink():
            raise RuntimeError(
                f"Refusing to replace directory '{active_link}'. Remove it manually first."
            )
        active_link.unlink()

    os.symlink(str(model_dir), str(active_link))
    print(f"Active model link: {active_link} -> {model_dir}")


if __name__ == "__main__":
    main()
