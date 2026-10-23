"""Réglages lus dans les variables d'environnement (app/settings.py)."""

import pytest
from fastapi.testclient import TestClient

from app.main import create_application
from app.settings import DatabaseSettings, InvalidSetting, SecuritySettings, Settings, read_database, read_settings
from tests.conftest import application, connected


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
    with connected(application(docs=False)) as client:
        assert client.get("/api/docs").status_code == 404
        assert client.get("/api/openapi.json").status_code == 404
        assert client.get("/api/environments").status_code == 200  # l'API, elle, fonctionne


# --- Base PostgreSQL ------------------------------------------------------------

DATABASE_PASSWORD = "database-password"


def test_database_with_default_values():
    base = read_settings({"APP_DB_HOST": "postgres", "APP_DB_PASSWORD": DATABASE_PASSWORD}).base
    assert base == DatabaseSettings(
        host="postgres", password=DATABASE_PASSWORD, port=5432, name="suivi_delivery", user="suivi_delivery"
    )


def test_database_all_variables():
    variables = {
        "APP_DB_HOST": "db.exemple.fr",
        "APP_DB_PORT": "6432",
        "APP_DB_NAME": "delivery",
        "APP_DB_USER": "appli",
        "APP_DB_PASSWORD": DATABASE_PASSWORD,
        "APP_DB_SCHEMA": "suivi",
    }
    expected = DatabaseSettings("db.exemple.fr", DATABASE_PASSWORD, 6432, "delivery", "appli", "suivi")
    assert read_settings(variables).base == expected


def test_connection_in_our_tables_schema():
    base = read_settings({"APP_DB_HOST": "postgres", "APP_DB_PASSWORD": DATABASE_PASSWORD}).base
    assert base is not None
    assert "-c search_path=suivi_delivery" in base.connection()["options"]


def test_database_password_never_shown():
    settings = read_settings({"APP_DB_HOST": "postgres", "APP_DB_PASSWORD": DATABASE_PASSWORD})
    assert DATABASE_PASSWORD not in repr(settings)


@pytest.mark.parametrize(
    ("variables", "message"),
    [
        ({"APP_DB_HOST": "postgres"}, "APP_DB_PASSWORD est obligatoire"),
        ({"APP_DB_HOST": "postgres", "APP_DB_PASSWORD": "x", "APP_DB_PORT": "cinq"}, "APP_DB_PORT"),
        ({"APP_DB_PASSWORD": "x"}, "sans APP_DB_HOST"),
        ({"APP_DB_NAME": "delivery"}, "sans APP_DB_HOST"),
        ({"APP_DB_SCHEMA": "suivi"}, "sans APP_DB_HOST"),
        ({"APP_DB_HOST": "postgres", "APP_DB_PASSWORD": "x", "APP_DB_SCHEMA": "Suivi Delivery"}, "APP_DB_SCHEMA"),
        ({"APP_DB_HOST": "postgres", "APP_DB_PASSWORD": "x", "APP_DB_SCHEMA": "a,public"}, "APP_DB_SCHEMA"),
    ],
)
def test_inconsistent_database_rejected(variables, message):
    with pytest.raises(InvalidSetting, match=message):
        read_settings(variables)


def test_tests_database_read_with_another_prefix():
    variables = {"TESTS_DB_HOST": "localhost", "TESTS_DB_PASSWORD": "x", "APP_DB_HOST": "prod"}
    assert read_database(variables, prefix="TESTS_DB_") == DatabaseSettings("localhost", "x")


# --- Connexion par Keycloak ----------------------------------------------------

KEY = "c" * 16


def test_security_by_default():
    security = read_settings({}).security
    assert security == SecuritySettings(
        keycloak_url=None, realm="suivi-delivery", client_secret=None, frontend_url="http://localhost:8080"
    )
    assert security.issuer == "http://localhost:8080/auth/realms/suivi-delivery"
    assert security.realm_url is None


def test_security_all_variables():
    security = read_settings(
        {
            "APP_KEYCLOAK_URL": "http://keycloak:8080/auth/",
            "APP_KEYCLOAK_REALM": "delivery",
            "APP_KEYCLOAK_CLIENT_SECRET": KEY,
            "APP_FRONTEND_URL": "https://suivi.exemple.fr/",
            "APP_API_URL": "https://suivi-api.exemple.fr",
        }
    ).security
    assert security == SecuritySettings(
        "http://keycloak:8080/auth", "delivery", KEY, "https://suivi.exemple.fr", "https://suivi-api.exemple.fr"
    )
    # Émetteur : Keycloak vu du navigateur, sous l'interface ; clés et comptes : par l'adresse interne.
    assert security.issuer == "https://suivi.exemple.fr/auth/realms/delivery"
    assert security.realm_url == "http://keycloak:8080/auth/realms/delivery"


def test_key_never_shown():
    settings = read_settings({"APP_KEYCLOAK_URL": "http://keycloak:8080/auth", "APP_KEYCLOAK_CLIENT_SECRET": KEY})
    assert KEY not in repr(settings)


@pytest.mark.parametrize(
    ("variables", "message"),
    [
        ({"APP_KEYCLOAK_URL": "keycloak:8080"}, "APP_KEYCLOAK_URL"),
        ({"APP_KEYCLOAK_REALM": "suivi delivery"}, "APP_KEYCLOAK_REALM"),
        ({"APP_KEYCLOAK_URL": "http://k/auth", "APP_KEYCLOAK_CLIENT_SECRET": "c" * 15}, "APP_KEYCLOAK_CLIENT_SECRET"),
        ({"APP_KEYCLOAK_CLIENT_SECRET": KEY}, "sans APP_KEYCLOAK_URL"),
        ({"APP_FRONTEND_URL": "suivi.exemple.fr"}, "APP_FRONTEND_URL"),
    ],
)
def test_security_invalid_value_rejected(variables, message):
    with pytest.raises(InvalidSetting, match=message) as error:
        read_settings(variables)
    assert "c" * 15 not in str(error.value)  # une clé n'est jamais recopiée dans le message
