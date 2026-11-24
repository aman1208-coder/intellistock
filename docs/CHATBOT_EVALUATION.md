# Chatbot intent evaluation

The chatbot uses a small hand-curated training corpus. Metrics below measure intent classification, not whether a live database answer is correct. Results are indicative and should not be presented as a broad real-world benchmark.

## Dataset and method

- Training corpus: 980 examples across 15 intents; each intent has at least 60 examples and out-of-scope has 113.
- The deterministic train/validation/test split is made by `ml_models/chatbot/train.py` (seeds 2026 and 2027). Its validation score is measured on the training distribution and is not an independent real-world estimate.
- `eval/handwritten.jsonl` contains 76 separate questions. Normalized training overlap: **0**.
- `eval/blind.jsonl` contains 40 questions written after the final training run. Normalized overlap with training and the handwritten set: **0**. The frozen model was run on it once.
- Normalization lowercases text, strips punctuation, and collapses whitespace. Dataset construction also removes same-intent near duplicates at a 0.94 `SequenceMatcher` ratio.

## Results

| Set | Count | Accuracy | Macro-F1 | Notes |
| --- | ---: | ---: | ---: | --- |
| Validation split | 147 | 0.898 | 0.900 | Training-distribution result |
| Hand-written held-out | 76 | 0.974 | 0.972 | Fixed set; not used for training |
| Fresh blind | 40 | 0.975 | 0.975 | Evaluated once after model freeze; small indicative estimate |

### Hand-written held-out per-intent scores

| Intent | Precision | Recall | F1 | Support |
| --- | ---: | ---: | ---: | ---: |
| api_latency | 1.000 | 1.000 | 1.000 | 5 |
| demand_forecast | 1.000 | 1.000 | 1.000 | 5 |
| greeting | 1.000 | 1.000 | 1.000 | 5 |
| how_does_it_work | 1.000 | 1.000 | 1.000 | 5 |
| low_stock_threshold | 1.000 | 1.000 | 1.000 | 5 |
| network_issues | 1.000 | 1.000 | 1.000 | 5 |
| out_of_scope | 1.000 | 1.000 | 1.000 | 6 |
| pending_reorders | 1.000 | 1.000 | 1.000 | 5 |
| product_status | 1.000 | 0.600 | 0.750 | 5 |
| recommendation | 1.000 | 1.000 | 1.000 | 5 |
| security_events | 1.000 | 1.000 | 1.000 | 5 |
| slow_database | 1.000 | 1.000 | 1.000 | 5 |
| system_health_overview | 1.000 | 1.000 | 1.000 | 5 |
| warehouse_capacity | 1.000 | 1.000 | 1.000 | 5 |
| zero_stock | 0.714 | 1.000 | 0.833 | 5 |

Held-out misses (predicted → expected):

- “Is SKU-77 still in stock, or has it sold out?” — `zero_stock` → `product_status`.
- “sku 88 stock?” — `zero_stock` → `product_status`.

The service now gives a named SKU status query precedence over generic intent classification. For an unknown SKU, it reports that the item could not be identified instead of returning a generic stockout list.

### Blind set

Per-intent F1 was 1.000 for every intent except `recommendation` (0.667) and `out_of_scope` (0.960). The sole miss was:

- “What items make good add-ons to the barcode reader?” — `out_of_scope` → `recommendation`.

This is one 40-question run, not a dependable production accuracy estimate.

## Reproduction

From the repository root:

```bash
python ml_models/chatbot/build_dataset.py
python ml_models/chatbot/train.py
cd backend && python -m pytest -q
```

Do not retrain using either evaluation file. `eval/blind.jsonl` is for frozen-model reporting; do not use it to tune examples or thresholds.
