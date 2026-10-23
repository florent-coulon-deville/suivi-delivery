"""Tests de /api/enumerations : les valeurs des listes fermées, pour l'interface."""

from tests.conftest import application, started


def test_values_of_closed_lists(client):
    response = client.get("/api/enumerations")
    assert response.status_code == 200
    assert response.json() == {
        "ModuleType": ["CAPABILITY", "BUSINESS_PROJECT"],
        "VersionType": ["RELEASE", "SNAPSHOT"],
        "ParameterType": ["TECHNICAL", "APPLICATION"],
        "ConditionType": ["EXACT", "AT_LEAST", "BETWEEN"],
    }


def test_available_even_without_swagger():
    with started(application(docs=False)) as client:
        assert client.get("/api/openapi.json").status_code == 404
        assert client.get("/api/enumerations").status_code == 200


def test_read_only(client):
    response = client.post("/api/enumerations", json={})
    assert response.status_code == 405
    assert response.headers["allow"] == "GET, HEAD, OPTIONS"
