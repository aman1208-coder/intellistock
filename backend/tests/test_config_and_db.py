"""Runtime secret and database fallback configuration tests."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from pydantic import SecretStr, ValidationError
from sqlalchemy.exc import OperationalError
from fastapi import FastAPI
from fastapi.testclient import TestClient

BACKEND_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = BACKEND_DIR.parent
for import_path in (str(BACKEND_DIR), str(PROJECT_ROOT)):
    if import_path not in sys.path:
        sys.path.insert(0, import_path)

from app.core.config import Settings
from app.db import session as db_session
from app.main import health_check
from app.services.observability import observability_store


class RuntimeConfigurationTests(unittest.TestCase):
    def _valid_production_settings(self, **overrides: object) -> Settings:
        values: dict[str, object] = {
            "app_env": "production",
            "secret_key": "s" * 48,
            "initial_admin_password": SecretStr("strong-admin-password-2026"),
            "observability_ingest_secret": "i" * 48,
        }
        values.update(overrides)
        return Settings(_env_file=None, **values)

    def test_production_rejects_missing_or_placeholder_secrets(self) -> None:
        cases = (
            {"secret_key": None},
            {"secret_key": "replace-with-a-production-secret-value"},
            {"initial_admin_password": SecretStr("replace-with-admin-password")},
            {"initial_admin_password": None},
            {"observability_ingest_secret": "replace-with-a-production-ingest-secret"},
            {"observability_ingest_secret": ""},
        )
        for override in cases:
            with self.subTest(field=next(iter(override))):
                values = {
                    "app_env": "production",
                    "secret_key": "s" * 48,
                    "initial_admin_password": SecretStr("strong-admin-password-2026"),
                    "observability_ingest_secret": "i" * 48,
                }
                values.update(override)
                if values["secret_key"] is None:
                    values.pop("secret_key")
                with self.assertRaises(ValidationError):
                    Settings(_env_file=None, **values)

    def test_production_uses_safe_sqlite_fallback_default(self) -> None:
        configured = self._valid_production_settings()

        self.assertFalse(configured.allow_sqlite_fallback)

    def test_development_defaults_fallback_on_and_warns_without_ingest_secret(self) -> None:
        with self.assertLogs("app.core.config", level="WARNING") as captured:
            configured = Settings(
                _env_file=None,
                app_env="development",
                secret_key="replace-this-with-a-development-secret",
                initial_admin_password=SecretStr("replace-with-admin-password"),
                observability_ingest_secret="replace-with-a-long-random-ingest-secret",
            )

        self.assertTrue(configured.allow_sqlite_fallback)
        warning = " ".join(captured.output)
        self.assertIn("OBSERVABILITY_INGEST_SECRET", warning)
        self.assertNotIn("replace-with", warning)

    def test_development_can_explicitly_disable_fallback(self) -> None:
        configured = Settings(
            _env_file=None,
            app_env="development",
            allow_sqlite_fallback=False,
            secret_key="d" * 48,
            observability_ingest_secret="i" * 48,
        )

        self.assertFalse(configured.allow_sqlite_fallback)

    def test_postgresql_failure_falls_back_only_when_enabled(self) -> None:
        candidate = Mock()
        candidate.connect.side_effect = OperationalError("connect", {}, RuntimeError("unavailable"))
        fallback_engine = Mock()
        fallback_engine.dialect = SimpleNamespace(name="sqlite")

        with patch.object(db_session.settings, "database_url", "postgresql://db.invalid/app"), patch.object(
            db_session.settings, "allow_sqlite_fallback", True
        ), patch.object(db_session, "_create_engine", side_effect=[candidate, fallback_engine]) as create_engine, self.assertLogs(
            "app.db.session", level="WARNING"
        ) as captured:
            result = db_session._get_engine()

        self.assertIs(result, fallback_engine)
        self.assertEqual(create_engine.call_args_list[1].args, (db_session.SQLITE_URL,))
        self.assertIn("using local SQLite fallback", " ".join(captured.output))
        self.assertNotIn("db.invalid", " ".join(captured.output))

    def test_postgresql_failure_raises_when_fallback_disabled(self) -> None:
        candidate = Mock()
        candidate.connect.side_effect = OperationalError("connect", {}, RuntimeError("unavailable"))
        with patch.object(db_session.settings, "database_url", "postgresql://db.invalid/app"), patch.object(
            db_session.settings, "allow_sqlite_fallback", False
        ), patch.object(db_session, "_create_engine", return_value=candidate) as create_engine:
            with self.assertRaisesRegex(RuntimeError, "SQLite fallback is disabled"):
                db_session._get_engine()

        create_engine.assert_called_once_with("postgresql://db.invalid/app")

    def test_health_and_observability_report_active_database(self) -> None:
        expected = db_session.active_database
        health_app = FastAPI()
        health_app.add_api_route("/health", health_check)

        with TestClient(health_app) as client:
            response = client.get("/health")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["active_database"], expected)
        self.assertEqual(observability_store.status()["active_database"], expected)


if __name__ == "__main__":
    unittest.main()
