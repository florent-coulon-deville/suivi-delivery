"""Réglages lus dans les variables d'environnement (app/settings.py)."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import create_application
from app.settings import DatabaseSettings, InvalidSetting, Settings, read_database, read_settings
from tests.conftest import application, started


def test_without_variables_default_values():
    assert read_settings({}) == Settings(base=None, host="127.0.0.1", port=8000, log_level="info", docs=True)


def test_empty_variable_keeps_default_value():
    assert read_settings({"APP_PORT": "", "APP_HOST": "  "}) == Settings()


def test_all_variables():
    settings = read_settings(
        {
            "APP_HOST": "0.0.0.0",
            "APP_PORT": "9000",
            "APP_LOG_LEVEL": "DEBUG",
            "APP_DOCS": "non",
        }
    )
    assert settings == Settings(
        host="0.0.0.0",
        port=9000,
        log_level="debug",
        docs=False,
    )


@pytest.mark.parametrize("value", ["oui", "YES", "true", "1"])
def test_docs_yes(value):
    assert read_settings({"APP_DOCS": value}).docs is True


@pytest.mark.parametrize(
    ("variable", "value"),
    [
        ("APP_PORT", "abc"),
        ("APP_PORT", "0"),
        ("APP_PORT", "70000"),
        ("APP_PORT", "-1"),
        ("APP_LOG_LEVEL", "bavard"),
        ("APP_DOCS", "peut-être"),
    ],
)
def test_invalid_value_rejected(variable, value):
    with pytest.raises(InvalidSetting, match=variable):
        read_settings({variable: value})


def test_swagger_visible_by_default():
    client = TestClient(create_application())
    assert client.get("/api/docs").status_code == 200
    assert client.get("/api/openapi.json").status_code == 200


def test_swagger_hidden():
    with started(application(docs=False)) as client:
        assert client.get("/api/docs").status_code == 404
        assert client.get("/api/openapi.json").status_code == 404
        assert client.get("/api/environments").status_code == 200  # l'API, elle, fonctionne


# --- Base SQLite ----------------------------------------------------------------


def test_database_file():
    assert read_settings({"APP_DB_FILE": "/data/suivi-delivery.sqlite"}).base == DatabaseSettings(
        Path("/data/suivi-delivery.sqlite")
    )


def test_database_folder_rejected(tmp_path):
    with pytest.raises(InvalidSetting, match="APP_DB_FILE"):
        read_settings({"APP_DB_FILE": str(tmp_path)})


def test_tests_database_read_with_another_prefix():
    variables = {"TESTS_DB_FILE": "/tmp/x_tests.sqlite", "APP_DB_FILE": "/data/prod.sqlite"}
    assert read_database(variables, prefix="TESTS_DB_") == DatabaseSettings(Path("/tmp/x_tests.sqlite"))
