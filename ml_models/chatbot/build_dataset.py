"""Merge independently authored chatbot data parts and guard eval separation."""

from __future__ import annotations

import json
import re
from collections import Counter
from difflib import SequenceMatcher
from pathlib import Path


ROOT = Path(__file__).resolve().parent
PARTS = ROOT / "data" / "parts"
OUTPUT = ROOT / "data" / "intents.jsonl"
EVALUATION = ROOT / "eval" / "handwritten.jsonl"
HEALTH_PART = "05_security_health.jsonl"
CHITCHAT_PART = "06_chitchat.jsonl"
# Preserve the frozen corpus row order while keeping each authored batch on-topic.
CHITCHAT_INTERLEAVE_AFTER_TEXT = "Let's kick off today's shift together."


def normalize(text: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9 ]", " ", text.casefold()).split())


def near_duplicate(left: str, right: str) -> bool:
    if left == right:
        return True
    return SequenceMatcher(None, left, right).ratio() >= 0.94


def load_jsonl(path: Path) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        row = json.loads(line)
        if not isinstance(row.get("text"), str) or not row["text"].strip():
            raise ValueError(f"{path}:{line_number}: text must be a non-empty string")
        if not isinstance(row.get("intent"), str) or not row["intent"].strip():
            raise ValueError(f"{path}:{line_number}: intent must be a non-empty string")
        rows.append({"text": row["text"].strip(), "intent": row["intent"].strip()})
    return rows


def main() -> None:
    part_paths = sorted(PARTS.glob("*.jsonl"))
    if not part_paths:
        raise SystemExit(f"No JSONL parts found under {PARTS}")

    eval_rows = load_jsonl(EVALUATION)
    eval_normalized = [normalize(row["text"]) for row in eval_rows]
    seen_by_intent: dict[str, list[str]] = {}
    accepted: list[dict[str, str]] = []
    deferred_health: list[dict[str, str]] = []
    exact_removed = near_removed = eval_near_removed = 0

    def add_row(row: dict[str, str]) -> None:
        nonlocal exact_removed, near_removed, eval_near_removed
        text = normalize(row["text"])
        if not text:
            return
        if text in eval_normalized or any(near_duplicate(text, question) for question in eval_normalized):
            eval_near_removed += 1
            return
        existing = seen_by_intent.setdefault(row["intent"], [])
        if text in existing:
            exact_removed += 1
            return
        if any(near_duplicate(text, previous) for previous in existing):
            near_removed += 1
            return
        existing.append(text)
        accepted.append(row)

    for path in part_paths:
        rows = load_jsonl(path)
        if path.name == HEALTH_PART:
            health_seen = 0
            for row in rows:
                if row["intent"] == "system_health_overview":
                    health_seen += 1
                    if health_seen > 60:
                        deferred_health.append(row)
                        continue
                add_row(row)
        elif path.name == CHITCHAT_PART:
            for row in rows:
                add_row(row)
                if row["text"] == CHITCHAT_INTERLEAVE_AFTER_TEXT:
                    for health_row in deferred_health:
                        add_row(health_row)
                    deferred_health.clear()
        else:
            for row in rows:
                add_row(row)

    if deferred_health:
        raise SystemExit("The health supplement could not be inserted into the chitchat batch order")

    counts = Counter(row["intent"] for row in accepted)
    expected = {
        "zero_stock", "low_stock_threshold", "warehouse_capacity", "pending_reorders",
        "product_status", "demand_forecast", "recommendation", "slow_database",
        "api_latency", "network_issues", "security_events", "system_health_overview",
        "how_does_it_work", "greeting", "out_of_scope",
    }
    missing = expected - counts.keys()
    below_minimum = {intent: counts[intent] for intent in expected if counts[intent] < 60}
    unexpected = counts.keys() - expected
    if missing or below_minimum or unexpected:
        raise SystemExit(
            f"Dataset count/label check failed: missing={sorted(missing)}, "
            f"below_minimum={below_minimum}, unexpected={sorted(unexpected)}"
        )

    OUTPUT.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in accepted),
        encoding="utf-8",
    )
    train_normalized = {normalize(row["text"]) for row in accepted}
    overlap = train_normalized.intersection(eval_normalized)
    print("examples per intent:")
    for intent in sorted(counts):
        print(f"  {intent}: {counts[intent]}")
    print(f"total: {len(accepted)}")
    print(f"exact duplicates removed: {exact_removed}")
    print(f"near duplicates removed: {near_removed}")
    print(f"held-out exact/near matches removed: {eval_near_removed}")
    print(f"normalized overlap with eval/handwritten.jsonl: {len(overlap)}")
    if overlap:
        raise SystemExit(f"Training/evaluation overlap: {sorted(overlap)}")


if __name__ == "__main__":
    main()
