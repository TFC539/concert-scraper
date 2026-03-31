import argparse
from pathlib import Path

from common import read_jsonl


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Render prompt files for offline review")
    parser.add_argument("--input", required=True, help="Input labeled JSONL")
    parser.add_argument("--system", default="ml/prompts/system_labeler.md", help="System prompt template")
    parser.add_argument("--user", default="ml/prompts/user_label_template.md", help="User prompt template")
    parser.add_argument("--out-dir", required=True, help="Output directory for rendered prompts")
    return parser.parse_args()


def render_user_prompt(template: str, row: dict) -> str:
    fields = {
        "id": row.get("id", ""),
        "source": row.get("source", ""),
        "name": row.get("name", ""),
        "date": row.get("date", ""),
        "time": row.get("time", ""),
        "hall": row.get("hall", ""),
        "text": row.get("text", ""),
    }
    content = template
    for k, v in fields.items():
        content = content.replace("{{" + k + "}}", str(v))
    return content


def main() -> None:
    args = parse_args()
    rows = read_jsonl(Path(args.input))

    system_prompt = Path(args.system).read_text(encoding="utf-8")
    user_prompt_template = Path(args.user).read_text(encoding="utf-8")

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    for row in rows:
        row_id = row.get("id", "unknown")
        user_prompt = render_user_prompt(user_prompt_template, row)
        output = (
            "# System Prompt\n\n"
            + system_prompt
            + "\n\n# User Prompt\n\n"
            + user_prompt
            + "\n"
        )
        (out_dir / f"prompt_{row_id}.md").write_text(output, encoding="utf-8")

    print(f"Rendered {len(rows)} prompts into {out_dir}")


if __name__ == "__main__":
    main()
