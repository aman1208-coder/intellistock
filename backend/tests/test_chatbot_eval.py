"""Protect the chatbot's held-out hand-written evaluation set."""

from __future__ import annotations

import json
import re
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CHATBOT_ROOT = PROJECT_ROOT / "ml_models" / "chatbot"
BACKEND_ROOT = PROJECT_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.services import chatbot


def normalize(text: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9 ]", " ", text.casefold()).split())


class HandwrittenChatbotEvaluationTests(unittest.TestCase):
    def test_eval_questions_are_not_in_training_data(self) -> None:
        training = [
            json.loads(line)
            for line in (CHATBOT_ROOT / "data" / "intents.jsonl").read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        handwritten = self.load_rows(CHATBOT_ROOT / "eval" / "handwritten.jsonl")
        blind = self.load_rows(CHATBOT_ROOT / "eval" / "blind.jsonl")
        training_text = {normalize(row["text"]) for row in training}
        self.assertGreaterEqual(len(handwritten), 60)
        self.assertEqual(len(blind), 40)
        for evaluation in (handwritten, blind):
            self.assertFalse(training_text.intersection(normalize(row["text"]) for row in evaluation))
            self.assertEqual({row["intent"] for row in evaluation}, {row["intent"] for row in training})
        self.assertFalse(
            {normalize(row["text"]) for row in handwritten}
            & {normalize(row["text"]) for row in blind}
        )

        counts = {}
        for row in training:
            counts[row["intent"]] = counts.get(row["intent"], 0) + 1
        self.assertEqual(len(counts), 15)
        self.assertTrue(all(count >= 60 for count in counts.values()), counts)
        blind_counts = {}
        for row in blind:
            blind_counts[row["intent"]] = blind_counts.get(row["intent"], 0) + 1
        self.assertEqual(set(blind_counts), set(counts))
        self.assertTrue(all(count >= 2 for count in blind_counts.values()), blind_counts)

    @staticmethod
    def load_rows(path: Path) -> list[dict[str, str]]:
        return [
            json.loads(line)
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]

    def test_model_keeps_minimum_handwritten_accuracy(self) -> None:
        import joblib
        from sklearn.metrics import accuracy_score

        artifact = joblib.load(CHATBOT_ROOT / "model.joblib")
        rows = self.load_rows(CHATBOT_ROOT / "eval" / "handwritten.jsonl")
        predictions = artifact["pipeline"].predict([row["text"] for row in rows])
        labels = [row["intent"] for row in rows]
        # Frozen round-two held-out accuracy is 0.974; retain a 3.4-point margin.
        self.assertGreaterEqual(accuracy_score(labels, predictions), 0.94)

    def test_low_confidence_gibberish_falls_back_to_help_without_metrics(self) -> None:
        with patch.object(chatbot, "_classify_intent", return_value=(None, 0.12)):
            result = chatbot.answer_stock_query(None, "qzxv blergh")
        self.assertEqual(result["kind"], "out_of_scope")
        self.assertIn("I can help with", result["answer"])
        self.assertEqual(result["items"], [])
        self.assertNotRegex(result["answer"], r"\b\d+\b")

    def test_unseen_gibberish_uses_safe_real_classifier_fallback(self) -> None:
        result = chatbot.answer_stock_query(None, "nonsense klip baz")
        self.assertEqual(result["kind"], "out_of_scope")
        self.assertIn("I can help with", result["answer"])
        self.assertEqual(result["items"], [])

    def test_low_confidence_reaches_keyword_intent_before_help(self) -> None:
        with (
            patch.object(chatbot, "_classify_intent", return_value=(None, 0.2)),
            patch.object(chatbot, "_grounded_intent", return_value={"kind": "network_issues"}) as grounded,
        ):
            result = chatbot.answer_stock_query(None, "check tcp resets")
        grounded.assert_called_once_with(None, "check tcp resets", "network_issues")
        self.assertEqual(result["kind"], "network_issues")

    def test_empty_question_returns_help_without_inventory_values(self) -> None:
        result = chatbot.answer_stock_query(None, "  ")
        self.assertEqual(result["kind"], "help")
        self.assertEqual(result["items"], [])
        self.assertNotRegex(result["answer"], r"\b\d+\b")

    def test_classifier_error_does_not_bypass_confidence_threshold(self) -> None:
        class BrokenPipeline:
            def predict_proba(self, _questions):
                raise RuntimeError("classifier unavailable")

            def predict(self, _questions):
                return ["zero_stock"]

        with patch.object(chatbot, "_load_classifier", return_value={"pipeline": BrokenPipeline()}):
            self.assertEqual(chatbot._classify_intent("asdf qwerty"), (None, 0.0))


if __name__ == "__main__":
    unittest.main()
