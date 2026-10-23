"""Routes /api/accounts : personnes, programmes, rôles ; il reste toujours un administrateur.

Les comptes sont dans Keycloak ; ici, dans l'annuaire en mémoire des tests (app/directory.py),
qui suit les mêmes règles.
"""

from fastapi.testclient import TestClient

from app.main import create_application
from app.schemas import Role
from tests.conftest import SECURITY, sign, token_content, verifier

PASSWORD = "a-strong-password"


def person(identifier="paul", role="EDITOR", **others) -> dict:
    return {
        "identifier": identifier,
        "name": "Paul Martin",
        "kind": "PERSON",
        "role": role,
        "password": PASSWORD,
        **others,
    }


def program(identifier="tool", role="EDITOR") -> dict:
    return {"identifier": identifier, "name": "Outil", "kind": "PROGRAM", "role": role}


def admin(client) -> dict:
    return next(c for c in client.get("/api/accounts").json() if c["identifier"] == "admin")


def test_admin_created_with_keycloak(client):
    [account] = client.get("/api/accounts").json()
    assert {k: v for k, v in account.items() if k != "id"} == {
        "identifier": "admin",
        "name": "Administrateur",
        "kind": "PERSON",
        "role": "ADMIN",
        "active": True,
    }


def test_create_person_with_temporary_password(client):
    response = client.post("/api/accounts", json=person(identifier="PAUL"))
    assert response.status_code == 201
    created = response.json()
    assert response.headers["Location"] == f"/api/accounts/{created['id']}"
    assert created["identifier"] == "paul"
    assert created["key"] is None
    assert "password" not in created  # jamais renvoyé
    assert client.app.state.directory.temporary_passwords["paul"] == PASSWORD
    assert client.get(f"/api/accounts/{created['id']}").json()["identifier"] == "paul"


def test_create_program_shows_key_only_once(client):
    response = client.post("/api/accounts", json=program())
    assert response.status_code == 201
    assert response.json()["key"] == client.app.state.directory.keys["tool"]
    assert "key" not in client.get(f"/api/accounts/{response.json()['id']}").json()


def test_password_according_to_kind(client):
    assert client.post("/api/accounts", json=person(password=None)).status_code == 422
    assert client.post("/api/accounts", json=person(password="court")).status_code == 422
    assert client.post("/api/accounts", json=person(kind="PROGRAM")).status_code == 422


def test_password_different_from_identifier(client):
    response = client.post("/api/accounts", json=person(identifier="paulmartin12", password="PaulMartin12"))
    assert response.status_code == 422


def test_identifier_unique_between_persons_and_programs(client):
    client.post("/api/accounts", json=person())
    response = client.post("/api/accounts", json=person())
    assert response.status_code == 409
    assert response.json()["detail"] == "L'identifiant paul est déjà utilisé"
    assert client.post("/api/accounts", json=program("paul")).status_code == 409


def test_update(client):
    paul = client.post("/api/accounts", json=person()).json()
    response = client.patch(f"/api/accounts/{paul['id']}", json={"name": "Paul M.", "role": "VIEWER"})
    assert response.status_code == 200
    assert response.json()["name"] == "Paul M."
    assert response.json()["role"] == "VIEWER"
    assert client.put(f"/api/accounts/{paul['id']}", json=person()).status_code == 405


def test_new_temporary_password(client):
    paul = client.post("/api/accounts", json=person()).json()
    response = client.patch(f"/api/accounts/{paul['id']}", json={"password": "new-password"})
    assert response.status_code == 200
    assert client.app.state.directory.temporary_passwords["paul"] == "new-password"
    assert client.patch(f"/api/accounts/{paul['id']}", json={"password": "court"}).status_code == 422


def test_a_program_has_no_password(client):
    tool = client.post("/api/accounts", json=program()).json()
    response = client.patch(f"/api/accounts/{tool['id']}", json={"password": PASSWORD})
    assert response.status_code == 422


def test_new_key(client):
    tool = client.post("/api/accounts", json=program()).json()
    response = client.post(f"/api/accounts/{tool['id']}/key")
    assert response.status_code == 200
    assert response.json()["key"] != tool["key"]
    assert response.json()["key"] == client.app.state.directory.keys["tool"]
    assert client.post(f"/api/accounts/{admin(client)['id']}/key").status_code == 422  # admin : une personne


def test_delete(client):
    paul = client.post("/api/accounts", json=person()).json()
    assert client.delete(f"/api/accounts/{paul['id']}").status_code == 204
    assert client.get(f"/api/accounts/{paul['id']}").status_code == 404


def test_unknown_account_404(client):
    assert client.get("/api/accounts/unknown").status_code == 404
    assert client.patch("/api/accounts/unknown", json={"name": "X"}).status_code == 404
    assert client.delete("/api/accounts/unknown").status_code == 404


def test_always_an_active_administrator_left(client):
    message = "Il doit rester au moins un administrateur actif"
    id_admin = admin(client)["id"]
    for response in (
        client.delete(f"/api/accounts/{id_admin}"),
        client.patch(f"/api/accounts/{id_admin}", json={"active": False}),
        client.patch(f"/api/accounts/{id_admin}", json={"role": "EDITOR"}),
    ):
        assert response.status_code == 409
        assert response.json()["detail"] == message
    # Avec un second administrateur, le premier peut partir.
    client.post("/api/accounts", json=person(identifier="chef", role="ADMIN"))
    assert client.patch(f"/api/accounts/{id_admin}", json={"role": "EDITOR"}).status_code == 200


def test_without_keycloak_client_secret_503():
    # Pas d'annuaire (APP_KEYCLOAK_CLIENT_SECRET absente) : la gestion des comptes est indisponible.
    app = create_application(security=SECURITY, verifier=verifier())
    with TestClient(app) as client:
        header = {"Authorization": f"Bearer {sign(token_content('admin', Role.ADMIN))}"}
        response = client.get("/api/accounts", headers=header)
    assert response.status_code == 503
    assert "APP_KEYCLOAK_CLIENT_SECRET" in response.json()["detail"]
