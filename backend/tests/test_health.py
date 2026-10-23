"""Tests des probes Kubernetes : /startupz, /readyz, /livez (app/routes/health.py).

« with TestClient(...) » lance le démarrage de l'API (lifespan), comme le serveur.
Sans « with », le démarrage n'a pas eu lieu : c'est le cas « démarrage en cours ».
"""

import pytest
from fastapi.testclient import TestClient

from app.main import create_application
from app.storage import StorageUnavailable
from tests.conftest import application, new_storage


@pytest.fixture
def started():
    """Une API démarrée (dans la base des tests s'il y en a une, sinon en mémoire)."""
    with TestClient(application()) as client:
        yield client


@pytest.mark.parametrize("path", ["/startupz", "/readyz", "/livez"])
def test_api_started_all_good(started, path):
    response = started.get(path)
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.parametrize("path", ["/startupz", "/readyz"])
def test_startup_in_progress_503(path):
    client = TestClient(create_application())  # pas de « with » : démarrage pas encore fait
    response = client.get(path)
    assert response.status_code == 503
    assert response.json() == {"status": "unavailable", "detail": "Démarrage en cours"}


def test_live_even_during_startup():
    assert TestClient(create_application()).get("/livez").status_code == 200


def test_database_unreachable_not_ready_but_live(started, monkeypatch):
    def outage():
        raise StorageUnavailable("connection refused")

    monkeypatch.setattr(started.app.state.storage, "check", outage)
    response = started.get("/readyz")
    assert response.status_code == 503
    assert response.json()["detail"] == "Base de données inaccessible"
    # Ni le démarrage ni la vie ne dépendent de la base : Kubernetes ne redémarre pas le pod.
    assert started.get("/startupz").status_code == 200
    assert started.get("/livez").status_code == 200


def test_check_changes_nothing():
    with new_storage() as storage:
        storage.environments.add({"code": "int", "label": "Intégration", "is_prod": False})
        storage.check()
        storage.check()  # rejouable : aucune transaction laissée ouverte
        storage.environments.add({"code": "prod", "label": "Production", "is_prod": True})
        assert [e["code"] for e in storage.environments.list_all()] == ["int", "prod"]


def test_outside_api_and_without_data(started):
    assert started.get("/api/livez").status_code == 404
    assert started.get("/livez").json() == {"status": "ok"}


def test_common_http_rules(started):
    assert started.head("/readyz").status_code == 200
    response = started.options("/livez")
    assert response.status_code == 204
    assert response.headers["allow"] == "GET, HEAD, OPTIONS"
    response = started.post("/livez", json={})
    assert response.status_code == 405
    assert response.headers["allow"] == "GET, HEAD, OPTIONS"
