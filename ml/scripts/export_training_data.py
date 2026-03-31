import argparse
import json
import sqlite3
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export concert records to JSONL")
    parser.add_argument("--db", required=True, help="Path to SQLite DB")
    parser.add_argument("--out", required=True, help="Output JSONL path")
    parser.add_argument("--limit", type=int, default=0, help="Optional row limit")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    db_path = Path(args.db)
    out_path = Path(args.out)

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row

    sql = """
    SELECT
      id,
      source,
      source_url,
      external_id,
      name,
      program,
      performers,
      hall,
      date,
      date_normalized,
      time,
      fetched_at
    FROM concerts
    ORDER BY id ASC
    """
    if args.limit and args.limit > 0:
        sql += f" LIMIT {int(args.limit)}"

    rows = conn.execute(sql).fetchall()
    out_path.parent.mkdir(parents=True, exist_ok=True)

    with out_path.open("w", encoding="utf-8") as f:
        for row in rows:
            payload = dict(row)
            f.write(json.dumps(payload, ensure_ascii=False) + "\n")

    conn.close()
    print(f"Exported {len(rows)} rows to {out_path}")


if __name__ == "__main__":
    main()
