from __future__ import annotations

import json
import random
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


TEMPLATES = {
    "zero_stock": ["show zero stock items", "which products are out of stock", "list empty inventory", "items with 0 stock", "what is sold out", "koi stock khatam hai"],
    "low_stock_threshold": ["which items are low in stock", "show reorder warnings", "below threshold products", "kam stock wala list", "items needing reorder"],
    "warehouse_capacity": ["check warehouse capacity", "how much dock space is free", "warehouse available space", "godown capacity dikhao", "capacity status"],
    "pending_reorders": ["show pending reorder records", "purchase order backlog", "what reorders are waiting", "pending reorders list", "baaki reorder"],
    "product_status": ["what is the status of SKU-", "check stock for SKU-", "product SKU- details", "tell me SKU- inventory", "is SKU- in stock"],
    "demand_forecast": ["which products run out in 14 days", "14 day demand forecast", "forecast stock risk", "kal se demand prediction", "next 14 days demand"],
    "recommendation": ["recommend products bought together", "frequently bought with SKU-", "related product suggestions", "cross sell recommendation", "recommend next item"],
    "slow_database": ["why is the database slow", "show DB latency", "is PostgreSQL delayed", "p95 database latency", "database query is slow"],
    "api_latency": ["why is the app slow right now", "check API latency", "request response slow", "backend speed", "app p95 latency"],
    "network_issues": ["any network issues", "TCP retransmits", "connection failures", "network latency", "reset and drop stats"],
    "security_events": ["any suspicious activity", "show security events", "recent high severity alerts", "did anyone access secrets", "threat events"],
    "system_health_overview": ["system health overview", "how is everything running", "overall backend health", "CPU database network status", "current system status"],
    "how_does_it_work": ["how does Bankers algorithm work", "explain row locking", "why select for update", "priority scheduling concept", "lock versus no lock"],
    "greeting": ["hello", "hi", "hey assistant", "good morning", "namaste", "helo"],
    "out_of_scope": ["tell me a joke", "what is the weather", "write a poem", "who won the match", "random unrelated question"],
}


PREFIXES = ["please ", "can you ", "could you ", "just ", "quickly ", ""]
SUFFIXES = [" now", " please", " in the dashboard", " for me", " right now", ""]


def build_data() -> list[dict[str, str]]:
    random.seed(2026)
    rows: list[dict[str, str]] = []
    for intent, templates in TEMPLATES.items():
        for index in range(40):
            base = templates[index % len(templates)]
            text = f"{random.choice(PREFIXES)}{base}{random.choice(SUFFIXES)}"
            text = text.replace("  ", " ").strip()
            if index % 7 == 0:
                text = text.replace("stock", "stok").replace("database", "datbase")
            rows.append({"text": text, "intent": intent})
    random.shuffle(rows)
    return rows


def ensure_dataset() -> list[dict[str, str]]:
    DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not DATA_PATH.exists():
        rows = build_data()
        with DATA_PATH.open("w", encoding="utf-8") as handle:
            for row in rows:
                handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    with DATA_PATH.open("r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def main() -> None:
    random.seed(2026)
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
    print("confusion_matrix:")
    print(json.dumps(metrics["confusion_matrix"]))
    print(f"saved={MODEL_PATH}")


if __name__ == "__main__":
    main()
