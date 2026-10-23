"""Tests des types de module et des routes /api/dependencies."""

import pytest

from tests.conftest import create


@pytest.fixture
def modules(client, dataset) -> dict:
    """Trois modules sur deux applications : un batch métier qui s'appuie sur deux capacités du socle."""
    base = create(client, "applications", identifier="socle", name="Socle", trigram="soc")
    return {
        "batch": create(
            client,
            "modules",
            application_id=dataset["application"]["id"],
            code="batch-paie",
            name="Batch de paie",
            type="BUSINESS_PROJECT",
        ),
        "auth": create(
            client, "modules", application_id=base["id"], code="auth", name="Authentification", type="CAPABILITY"
        ),
        "log": create(
            client, "modules", application_id=base["id"], code="log", name="Journalisation", type="CAPABILITY"
        ),
    }


def depend(client, a: dict, b: dict) -> dict:
    """Déclare « a dépend de b » (doit réussir)."""
    return create(client, "dependencies", module_id=a["id"], depends_on_id=b["id"])


# --- Type de module ---------------------------------------------------------


def test_module_type_required_and_checked(client, dataset):
    body = {"application_id": dataset["application"]["id"], "code": "x", "name": "X"}
    assert client.post("/api/modules", json=body).status_code == 422  # absent
    assert client.post("/api/modules", json={**body, "type": "OTHER"}).status_code == 422  # inconnu
    assert client.post("/api/modules", json={**body, "type": "CAPABILITY"}).status_code == 201


def test_filter_modules_by_type(client, modules):
    response = client.get("/api/modules", params={"type": "CAPABILITY"})
    assert [m["code"] for m in response.json()] == ["auth", "log"]


# --- Dépendances ------------------------------------------------------------


def test_create_201_between_applications(client, modules):
    response = client.post(
        "/api/dependencies", json={"module_id": modules["batch"]["id"], "depends_on_id": modules["auth"]["id"]}
    )
    assert response.status_code == 201
    assert response.headers["Location"] == f"/api/dependencies/{response.json()['id']}"


def test_what_a_module_needs_and_who_uses_it(client, modules):
    depend(client, modules["batch"], modules["auth"])
    depend(client, modules["batch"], modules["log"])
    depend(client, modules["auth"], modules["log"])
    needs = client.get("/api/dependencies", params={"module_id": modules["batch"]["id"]}).json()
    assert [d["depends_on_id"] for d in needs] == [modules["auth"]["id"], modules["log"]["id"]]
    users = client.get("/api/dependencies", params={"depends_on_id": modules["log"]["id"]}).json()
    assert sorted(d["module_id"] for d in users) == sorted([modules["batch"]["id"], modules["auth"]["id"]])


def test_nonexistent_module_422(client, modules):
    body = {"module_id": modules["batch"]["id"], "depends_on_id": 999}
    assert client.post("/api/dependencies", json=body).status_code == 422


def test_no_dependency_on_itself_422(client, modules):
    body = {"module_id": modules["batch"]["id"], "depends_on_id": modules["batch"]["id"]}
    assert client.post("/api/dependencies", json=body).status_code == 422


def test_duplicate_409(client, modules):
    depend(client, modules["batch"], modules["auth"])
    body = {"module_id": modules["batch"]["id"], "depends_on_id": modules["auth"]["id"]}
    assert client.post("/api/dependencies", json=body).status_code == 409


def test_loop_409(client, modules):
    depend(client, modules["batch"], modules["auth"])
    depend(client, modules["auth"], modules["log"])
    # log → batch fermerait la boucle batch → auth → log → batch
    response = client.post(
        "/api/dependencies", json={"module_id": modules["log"]["id"], "depends_on_id": modules["batch"]["id"]}
    )
    assert response.status_code == 409
    assert response.json() == {"detail": "Cette dépendance créerait une boucle"}


def test_no_update_405(client, modules):
    dependency = depend(client, modules["batch"], modules["auth"])
    assert client.patch(f"/api/dependencies/{dependency['id']}", json={}).status_code == 405


def test_delete_204_then_404(client, modules):
    dependency = depend(client, modules["batch"], modules["auth"])
    assert client.delete(f"/api/dependencies/{dependency['id']}").status_code == 204
    assert client.get(f"/api/dependencies/{dependency['id']}").status_code == 404


def test_delete_linked_module_409(client, modules):
    depend(client, modules["batch"], modules["auth"])
    assert client.delete(f"/api/modules/{modules['auth']['id']}").status_code == 409  # d'autres en dépendent
    assert client.delete(f"/api/modules/{modules['batch']['id']}").status_code == 409  # il dépend d'autres
    assert client.delete(f"/api/modules/{modules['log']['id']}").status_code == 204  # libre
