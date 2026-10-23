"""Tests du stockage (app/storage.py, app/storage_postgres.py, app/transactions.py).

Les tests marqués « with_postgres » ne tournent qu'avec une base de tests (TESTS_DB_HOST, voir
tests/conftest.py) : rien n'est perdu au redémarrage de l'API, une saisie qui échoue n'enregistre
rien, la base refuse elle-même ce qui est incohérent. « Redémarrer » = créer une nouvelle
application sur la même base, sans la vider.
"""

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from app.main import create_application
from app.routes import clusters
from app.settings import DatabaseSettings
from app.storage import MemoryStorage, StorageUnavailable
from app.storage_postgres import PostgresStorage
from tests.conftest import BASE, application, connected, create, installation_body, new_storage, with_postgres


def restart():
    """Une nouvelle API sur les mêmes données, comme après un redémarrage (client connecté)."""
    return connected(application(clear=False))


ALL = [
    "environments",
    "clusters",
    "applications",
    "namespaces",
    "modules",
    "module-versions",
    "parameters",
    "slots",
    "installations",
]


# --- Opérations des tables (en mémoire, et dans la base s'il y en a une) -----------


def test_add_read_update_delete():
    with new_storage() as storage:
        int = storage.environments.add(
            {"code": "int", "label": "Intégration", "is_prod": False, "promotion_order": None}
        )
        assert int == {"id": 1, "code": "int", "label": "Intégration", "is_prod": False, "promotion_order": None}
        assert storage.environments.read(1) == int
        assert storage.environments.update(1, {"promotion_order": 2})["promotion_order"] == 2
        storage.environments.delete(1)
        assert storage.environments.read(1) is None
        assert (
            storage.environments.add({"code": "prod", "label": "Prod", "is_prod": True, "promotion_order": None})["id"]
            == 2
        )


def test_list_and_find_by_criteria():
    with new_storage() as storage:
        for code, order in (("int", 1), ("rec", None), ("prod", None)):
            storage.environments.add({"code": code, "label": code, "is_prod": False, "promotion_order": order})
        assert [e["code"] for e in storage.environments.list_all()] == ["int", "rec", "prod"]  # ordre de saisie
        assert [e["code"] for e in storage.environments.list_all(promotion_order=None)] == ["rec", "prod"]
        assert (storage.environments.find(code="prod") or {}).get("id") == 3
        assert storage.environments.find(code="preprod") is None


def test_successful_attempt_kept_failed_attempt_cancelled():
    def failed_attempt(storage):
        with storage.transaction(), storage.attempt() as attempt:
            attempt.clusters.add({"code": "cb02", "label": "Annulé", "is_prod": False})
            raise RuntimeError("incohérent")

    with new_storage() as storage:
        with storage.transaction(), storage.attempt() as attempt:
            attempt.clusters.add({"code": "cb01", "label": "Gardé", "is_prod": False})
        with pytest.raises(RuntimeError):
            failed_attempt(storage)
        assert [c["code"] for c in storage.clusters.list_all()] == ["cb01"]


def test_dates_read_back_as_dates(client, deployment):
    date = datetime(2026, 10, 9, 8, 30, tzinfo=UTC)
    installation = create(client, "installations", **installation_body(deployment), date=date.isoformat())
    assert installation["date"] == "2026-10-09T08:30:00Z"


def test_namespaces_of_a_parameter(client, dataset):
    ids = [
        create(
            client,
            "namespaces",
            application_id=dataset["application"]["id"],
            environment_id=dataset["int"]["id"],
            cluster_id=dataset["cluster"]["id"],
            suffix=suffix,
            network_zone_id=dataset["zone"]["id"],
        )["id"]
        for suffix in ("a", "b", "c")
    ]
    module = create(
        client, "modules", application_id=dataset["application"]["id"], code="web", name="Web", type="BUSINESS_PROJECT"
    )
    body = {"module_id": module["id"], "name": "conf", "type": "TECHNICAL"}
    parameter = create(client, "parameters", **body, namespace_ids=[ids[2], ids[0]])
    assert parameter["namespace_ids"] == [ids[0], ids[2]]  # triés, sans doublon
    updated = client.patch(f"/api/parameters/{parameter['id']}", json={"namespace_ids": [ids[1]]}).json()
    assert updated["namespace_ids"] == [ids[1]]
    assert client.delete(f"/api/parameters/{parameter['id']}").status_code == 204  # ses affectations partent avec


# --- Base PostgreSQL ------------------------------------------------------------


@with_postgres
def test_everything_found_after_restart(client, deployment):
    assert client.post("/api/installations", json=installation_body(deployment)).status_code == 201
    before = {resource: client.get(f"/api/{resource}").json() for resource in ALL}

    with restart() as after:
        for resource in ALL:
            assert after.get(f"/api/{resource}").json() == before[resource], resource


@with_postgres
def test_update_and_deletion_saved(client, dataset):
    client.patch(f"/api/clusters/{dataset['cluster']['id']}", json={"label": "Renommé"})
    assert client.delete(f"/api/environments/{dataset['int']['id']}").status_code == 204

    with restart() as after:
        assert after.get(f"/api/clusters/{dataset['cluster']['id']}").json()["label"] == "Renommé"
        assert after.get(f"/api/environments/{dataset['int']['id']}").status_code == 404


@with_postgres
def test_deleted_element_identifier_never_reused(client):
    first = create(client, "clusters", code="cb01", label="Cluster 1")
    second = create(client, "clusters", code="cb02", label="Cluster 2")
    client.delete(f"/api/clusters/{second['id']}")

    with restart() as after:
        new = create(after, "clusters", code="cb03", label="Cluster 3")
    assert new["id"] == second["id"] + 1 > first["id"]


@with_postgres
def test_rejected_edit_is_not_saved(client, deployment):
    # Le namespace est sur ce cluster dans un environnement hors prod : passer le cluster en prod est refusé.
    cluster = deployment["cluster"]
    assert client.patch(f"/api/clusters/{cluster['id']}", json={"is_prod": True}).status_code == 409

    with restart() as after:
        assert after.get(f"/api/clusters/{cluster['id']}").json()["is_prod"] is False


@with_postgres
def test_unexpected_error_everything_cancelled(client, monkeypatch):
    # Le cluster est écrit, puis la route plante : la transaction de la requête est annulée.
    def outage(*args):
        raise RuntimeError("outage")

    monkeypatch.setattr(clusters, "add_location", outage)
    without_exception = TestClient(client.app, raise_server_exceptions=False, headers=client.headers)
    assert without_exception.post("/api/clusters", json={"code": "cb01", "label": "C"}).status_code == 500
    assert client.get("/api/clusters").json() == []


@with_postgres
def test_database_rejects_what_the_api_would_let_through(client, monkeypatch):
    # Filet de sécurité : sans la vérification d'unicité de l'API, la base refuse le doublon (409).
    monkeypatch.setattr(clusters, "check_unique", lambda *args, **kwargs: None)
    create(client, "clusters", code="cb01", label="Cluster 1")
    response = client.post("/api/clusters", json={"code": "cb01", "label": "Doublon"})
    assert response.status_code == 409
    assert response.json()["detail"].startswith("Saisie refusée par la base de données")
    assert len(client.get("/api/clusters").json()) == 1


@with_postgres
def test_database_without_tables_rejected_at_startup():
    # La base « postgres », créée d'office par PostgreSQL, n'a pas nos tables : Liquibase n'est pas passé.
    assert BASE is not None
    without_tables = DatabaseSettings(BASE.host, BASE.password, BASE.port, "postgres", BASE.user)
    storage = PostgresStorage(without_tables)
    with pytest.raises(StorageUnavailable, match="Liquibase"):
        storage.open()
    with pytest.raises(StorageUnavailable, match="Liquibase"), TestClient(create_application(without_tables)):
        pass


@with_postgres
def test_database_unreachable():
    assert BASE is not None
    unreachable = DatabaseSettings("127.0.0.1", "x", 1, BASE.name, BASE.user)  # rien n'écoute sur le port 1
    storage = PostgresStorage(unreachable)
    with pytest.raises(StorageUnavailable, match="injoignable"):
        storage.open(wait_seconds=1)


# --- En mémoire -----------------------------------------------------------------


def test_without_database_data_in_memory():
    app = create_application()
    with TestClient(app):
        assert isinstance(app.state.storage, MemoryStorage)
