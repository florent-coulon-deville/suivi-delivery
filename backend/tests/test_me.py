"""Routes /api/me : qui suis-je (d'après mon jeton Keycloak), et mes préférences."""

from app.schemas import AccountKind, Role
from tests.conftest import sign, token_content


def test_my_account(client):
    response = client.get("/api/me")
    assert response.status_code == 200
    assert response.json() == {
        "identifier": "admin",
        "name": "Administrateur",
        "kind": "PERSON",
        "role": "ADMIN",
        "theme": "AUTO",
    }


def test_a_program(anonymous):
    token = sign(token_content("deployment-tool", Role.EDITOR, AccountKind.PROGRAM, "tool-subject"))
    response = anonymous.get("/api/me", headers={"Authorization": f"Bearer {token}"})
    assert response.json()["identifier"] == "deployment-tool"  # le nom du client, pas « service-account-… »
    assert response.json()["kind"] == "PROGRAM"


def test_password_cannot_be_changed_here(client):
    # Il se change sur la page de Keycloak, où l'interface envoie la personne.
    assert client.put("/api/me/password", json={}).status_code == 404


def test_without_token_401(anonymous):
    assert anonymous.get("/api/me").status_code == 401


# --- Préférences : le thème de couleurs ------------------------------------------


def test_theme_auto_by_default(client):
    assert client.get("/api/me").json()["theme"] == "AUTO"


def test_change_my_theme(client):
    response = client.patch("/api/me", json={"theme": "DARK"})
    assert response.status_code == 200
    assert response.json()["theme"] == "DARK"
    assert client.get("/api/me").json()["theme"] == "DARK"
    # Rien envoyé : rien ne change.
    assert client.patch("/api/me", json={}).json()["theme"] == "DARK"
    # Une seule ligne de préférences pour cette personne.
    assert len(client.app.state.storage.preferences.list_all()) == 1


def test_each_person_has_own_theme(client, anonymous):
    client.patch("/api/me", json={"theme": "DARK"})
    other = sign(token_content("lea", Role.VIEWER, subject="lea-subject"))
    assert anonymous.get("/api/me", headers={"Authorization": f"Bearer {other}"}).json()["theme"] == "AUTO"


def test_theme_unknown_or_empty_422(client):
    assert client.patch("/api/me", json={"theme": "ROSE"}).status_code == 422
    assert client.patch("/api/me", json={"theme": None}).status_code == 422


def test_only_theme_can_be_changed_here(client):
    # Le rôle, le nom… se changent dans /api/accounts (administration), pas ici.
    assert client.patch("/api/me", json={"role": "VIEWER"}).status_code == 422


def test_options_of_me(client):
    assert client.options("/api/me").headers["Allow"] == "GET, HEAD, PATCH, OPTIONS"


# --- Accès par script (jetons hors ligne) ------------------------------------------


def test_close_my_offline_access(client):
    assert client.delete("/api/me/offline-access").status_code == 204
    admin = next(c for c in client.get("/api/accounts").json() if c["identifier"] == "admin")
    assert client.app.state.directory.offline_access_closed == [admin["id"]]


def test_a_program_has_no_offline_access(anonymous):
    token = sign(token_content("tool", Role.EDITOR, AccountKind.PROGRAM))
    response = anonymous.delete("/api/me/offline-access", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 422
