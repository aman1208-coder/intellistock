from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

import joblib
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import FeatureUnion, Pipeline
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix, f1_score
from sklearn.model_selection import train_test_split


ROOT = Path(__file__).resolve().parent
DATA_PATH = ROOT / "data" / "intents.jsonl"
MODEL_PATH = ROOT / "model.joblib"
METRICS_PATH = ROOT / "metrics.json"


def ensure_dataset() -> list[dict[str, str]]:
    if not DATA_PATH.exists():
        raise FileNotFoundError(f"Training data is required at {DATA_PATH}; run build_dataset.py first")
    with DATA_PATH.open("r", encoding="utf-8") as handle:
        rows = [json.loads(line) for line in handle if line.strip()]
    counts = Counter(row.get("intent") for row in rows)
    if not rows or any(not isinstance(row.get("text"), str) or not row["text"].strip() for row in rows):
        raise ValueError("Training rows must contain non-empty text and intent fields")
    below_minimum = {intent: count for intent, count in counts.items() if count < 60}
    if below_minimum:
        raise ValueError(f"Every intent needs at least 60 examples; found {below_minimum}")
    normalized = [" ".join(re.sub(r"[^a-z0-9 ]", " ", row["text"].casefold()).split()) for row in rows]
    if len(normalized) != len(set(normalized)):
        raise ValueError("Training data contains normalized duplicate text")
    return rows


def main() -> None:
    rows = ensure_dataset()
    texts = [row["text"] for row in rows]
    labels = [row["intent"] for row in rows]
    train_texts, held_texts, train_labels, held_labels = train_test_split(
        texts, labels, test_size=0.30, random_state=2026, stratify=labels
    )
    validation_texts, test_texts, validation_labels, test_labels = train_test_split(
        held_texts, held_labels, test_size=0.50, random_state=2027, stratify=held_labels
    )
    features = FeatureUnion([
        ("word", TfidfVectorizer(analyzer="word", ngram_range=(1, 2), sublinear_tf=True)),
        ("char", TfidfVectorizer(analyzer="char", ngram_range=(3, 5), sublinear_tf=True)),
    ])
    pipeline = Pipeline([
        ("features", features),
        ("classifier", LogisticRegression(max_iter=1000, random_state=2026, C=4)),
    ])
    pipeline.fit(train_texts, train_labels)
    validation_predictions = pipeline.predict(validation_texts)
    predictions = pipeline.predict(test_texts)
    accuracy = accuracy_score(test_labels, predictions)
    macro_f1 = f1_score(test_labels, predictions, average="macro")
    report = classification_report(test_labels, predictions, zero_division=0, output_dict=True)
    metrics = {
        "accuracy": accuracy,
        "macro_f1": macro_f1,
        "confusion_matrix": confusion_matrix(test_labels, predictions, labels=pipeline.classes_.tolist()).tolist(),
        "labels": pipeline.classes_.tolist(),
        "classification_report": report,
        "seed": 2026,
        "validation_accuracy": accuracy_score(validation_labels, validation_predictions),
        "validation_macro_f1": f1_score(validation_labels, validation_predictions, average="macro"),
        "train_size": len(train_texts),
        "validation_size": len(validation_texts),
        "test_size": len(test_texts),
    }
    joblib.dump({"pipeline": pipeline, "metrics": metrics}, MODEL_PATH)
    METRICS_PATH.write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    print(f"accuracy={accuracy:.4f}")
    print(f"macro_f1={macro_f1:.4f}")
    print(f"validation_accuracy={metrics['validation_accuracy']:.4f}")
    print(f"validation_macro_f1={metrics['validation_macro_f1']:.4f}")
    print("confusion_matrix:")
    print(json.dumps(metrics["confusion_matrix"]))
    print(f"saved={MODEL_PATH}")


if __name__ == "__main__":
    main()
