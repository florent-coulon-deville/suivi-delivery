"""Contrôle d'accès (app/access.py) : 401 sans jeton valide, 403 si le rôle ne suffit pas."""

import pytest
from fastapi.testclient import TestClient

from app.main import create_application
from tests.conftest import ISSUER, a_module, token

PASSWORD = "a-strong-password"


def account(client, identifier: str, role: str) -> dict:
    """Crée une personne avec ce rôle ; renvoie l'en-tête pour l'utiliser."""
    response = client.post(
        "/api/accounts",
        json={
            "identifier": identifier,
            "name": identifier,
            "kind": "PERSON",
            "role": role,
            "password": PASSWORD,
        },
    )
    assert response.status_code == 201, response.json()
    return {"Authorization": f"Bearer {token(client.app, identifier)}"}


def test_without_token_401(anonymous):
    response = anonymous.get("/api/environments")
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
    assert "connectez-vous" in response.json()["detail"]


@pytest.mark.parametrize("path", ["/livez", "/readyz", "/startupz", "/api/docs", "/api/openapi.json"])
def test_routes_open_without_token(anonymous, path):
    assert anonymous.get(path).status_code == 200


def test_viewer_reads_but_does_not_update(client, anonymous):
    header = account(client, "reader", "VIEWER")
    assert anonymous.get("/api/environments", headers=header).status_code == 200
    assert anonymous.get("/api/enumerations", headers=header).status_code == 200
    response = anonymous.post("/api/module-versions", json={"module_id": 1, "number": "1.0.0"}, headers=header)
    assert response.status_code == 403
    assert response.json()["detail"] == "Droits insuffisants : rôle EDITOR requis"


def test_editor_enters_deliveries_but_not_structure(client, anonymous):
    module = a_module(client)
    header = account(client, "saisisseur", "EDITOR")
    version = {"module_id": module["id"], "number": "1.0.0"}
    assert anonymous.post("/api/module-versions", json=version, headers=header).status_code == 201
    response = anonymous.post("/api/environments", json={"code": "int", "label": "A"}, headers=header)
    assert response.status_code == 403
    assert response.json()["detail"] == "Droits insuffisants : rôle ADMIN requis"
    assert anonymous.get("/api/accounts", headers=header).status_code == 403


@pytest.mark.parametrize(
    "resource",
    [
        "environments",
        "clusters",
        "network-zones",
        "applications",
        "namespaces",
        "modules",
        "dependencies",
        "compatibilities",
        "slots",
    ],
)
def test_structure_is_reserved_to_admin(client, anonymous, resource):
    header = account(client, "saisisseur", "EDITOR")
    assert anonymous.get(f"/api/{resource}", headers=header).status_code == 200
    for method, path in (("POST", ""), ("DELETE", "/1")):  # PUT / PATCH : pas sur toutes (405)
        response = anonymous.request(method, f"/api/{resource}{path}", json={}, headers=header)
        assert response.status_code == 403, (method, path)


def test_admin_manages_accounts(client):
    assert client.get("/api/accounts").status_code == 200


def test_role_comes_from_token(client, anonymous):
    # Un rôle changé dans Keycloak s'applique au jeton suivant (au plus tard 5 minutes après).
    version = {"module_id": a_module(client)["id"], "number": "1.0.0"}
    account(client, "paul", "EDITOR")
    paul = next(c for c in client.get("/api/accounts").json() if c["identifier"] == "paul")
    client.patch(f"/api/accounts/{paul['id']}", json={"role": "VIEWER"})
    header = {"Authorization": f"Bearer {token(client.app, 'paul')}"}  # le jeton suivant
    assert anonymous.post("/api/module-versions", json=version, headers=header).status_code == 403


def test_without_keycloak_no_token_accepted():
    app = create_application()  # ni APP_KEYCLOAK_URL, ni vérificateur
    with TestClient(app) as anonymous:
        response = anonymous.get("/api/environments", headers={"Authorization": "Bearer x"})
    assert response.status_code == 401
    assert "APP_KEYCLOAK_URL" in response.json()["detail"]


def test_swagger_describes_keycloak_login(anonymous):
    schema = anonymous.get("/api/openapi.json").json()
    flow = schema["components"]["securitySchemes"]["Connexion"]["flows"]
    oidc = f"{ISSUER}/protocol/openid-connect"
    assert list(flow) == ["authorizationCode", "clientCredentials"]  # la page de connexion d'abord (Bruno)
    assert flow["authorizationCode"]["authorizationUrl"] == f"{oidc}/auth"
    assert flow["authorizationCode"]["tokenUrl"] == flow["clientCredentials"]["tokenUrl"] == f"{oidc}/token"
    assert "password" not in flow  # OAuth 2.1 : une personne passe par la page de connexion
