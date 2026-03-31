# ML Workflow (Transformer-only)

This folder contains a full ML workflow for extracting and validating `program`, `performers`, and `hall` metadata from scraped concert records.

## Scope
- Data export from SQLite (`concerts.db`)
- Train/val/test split
- Label task generation and schema validation
- Offline prompt rendering for human/LLM-assisted review
- Transformer training and evaluation scripts
- Inference and app-facing enrichment wrapper
- Production artifact export and deploy switch

## Quick Start

1. Create a dedicated venv for ML (recommended):

```bash
cd ml
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

2. Export records from DB:

```bash
python scripts/export_training_data.py --db ../concerts.db --out data/raw/concerts.jsonl
```

3. Generate one TXT file with full prompt + all records for your external LLM:

```bash
python scripts/generate_llm_labeling_txt.py \
	--input data/raw/concerts.jsonl \
	--out data/raw/llm_labeling_prompt.txt
```

4. Send that TXT to your LLM and save the LLM JSON output locally, for example:

`data/raw/llm_labels.json`

Expected format:

```json
[
	{
		"id": 123,
		"performers_target": ["..."],
		"program_target": ["..."],
		"hall_target": ["..."]
	}
]
```

5. Run one script that converts the LLM JSON into training data and starts transformer training:

```bash
python scripts/train_from_llm_output.py \
	--raw-input data/raw/concerts.jsonl \
	--llm-json data/raw/llm_labels.json \
	--out-dir models/run_001
```

6. Optional: export model for app and activate it:

```bash
python scripts/export_for_app.py --model-dir models/run_001 --target-dir models/production
python scripts/deploy_production_model.py --model-dir models/production --active-link models/active
```

## Integration Contract
`ml/scripts/ml_enricher.py` exposes:
- `load_model(model_dir)`
- `enrich_record(record, bundle)`

Record input schema is documented in `data/README.md`.

## Rollout Strategy
- Keep current rule-based extraction as fallback.
- Gate ML usage with an app-level feature flag.
- Enable shadow mode first (predict + log, no writes), then partial rollout.
