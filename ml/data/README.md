# Data Schema

## Raw export record (`concerts.jsonl`)

```json
{
  "id": 123,
  "source": "Elbphilharmonie",
  "source_url": "https://...",
  "external_id": "https://...",
  "name": "Max Mutzke",
  "program": "...",
  "performers": "...",
  "hall": "...",
  "date": "Thu, 1 Jan 2026",
  "date_normalized": "2026-01-01",
  "time": "20:00",
  "fetched_at": "2026-03-31T12:30:00"
}
```

## Label task record

```json
{
  "id": 123,
  "text": "<combined model text>",
  "context": {
    "name": "...",
    "program": "...",
    "performers": "...",
    "hall": "..."
  },
  "targets": {
    "performers_target": [],
    "program_target": [],
    "hall_target": [],
    "format_target": "",
    "notes": ""
  }
}
```

## Labeled example record (`labeled_examples.jsonl`)

Required keys:
- `id` (int)
- `text` (str)
- `targets.performers_target` (list[str])
- `targets.program_target` (list[str])
- `targets.hall_target` (list[str])

Optional keys:
- `targets.format_target` (str)
- `targets.notes` (str)
