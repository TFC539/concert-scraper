import argparse
import shutil
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Copy trained model artifacts for app use")
    parser.add_argument("--model-dir", required=True)
    parser.add_argument("--target-dir", required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    model_dir = Path(args.model_dir)
    target_dir = Path(args.target_dir)

    if not model_dir.exists() or not model_dir.is_dir():
        raise FileNotFoundError(f"Model dir not found: {model_dir}")

    if target_dir.exists():
        shutil.rmtree(target_dir)
    shutil.copytree(model_dir, target_dir)

    print(f"Exported model from {model_dir} to {target_dir}")


if __name__ == "__main__":
    main()
