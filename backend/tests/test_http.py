"""Tests des règles HTTP communes (app/http.py) et du PUT.

HEAD → comme GET sans corps ; OPTIONS → 204 + Allow ; 405 → Allow complet ;
PUT → remplacement complet ; 400 / 404 / 415 / 422 selon ce qui est faux dans la requête.
"""

import pytest

from tests.conftest import create, installation_body

# Toutes les collections de l'API, et les méthodes attendues sur un élément.
EDITABLE = [
    "environments",
    "clusters",
    "applications",
    "namespaces",
    "modules",
    "module-versions",
    "compatibilities",
    "parameters",
    "slots",
]
READ_ONLY = ["dependencies", "installations"]


# --- HEAD -------------------------------------------------------------------


def test_head_as_get_without_body(client, dataset):
    for url in ("/api/applications", f"/api/applications/{dataset['application']['id']}"):
        get, head = client.get(url), client.head(url)
        assert head.status_code == get.status_code == 200
        assert head.content == b""
        assert head.headers["content-type"] == get.headers["content-type"]
        assert head.headers["content-length"] == get.headers["content-length"]


def test_head_not_found_404(client):
    assert client.head("/api/applications/999").status_code == 404


# --- OPTIONS et en-tête Allow -----------------------------------------------


@pytest.mark.parametrize("resource", EDITABLE + READ_ONLY)
def test_options_on_a_collection(client, resource):
    response = client.options(f"/api/{resource}")
    assert response.status_code == 204
    assert response.headers["allow"] == "GET, HEAD, POST, OPTIONS"


@pytest.mark.parametrize("resource", EDITABLE)
def test_options_on_an_editable_element(client, resource):
    response = client.options(f"/api/{resource}/1")
    assert response.status_code == 204
    assert response.headers["allow"] == "GET, HEAD, PUT, PATCH, DELETE, OPTIONS"


@pytest.mark.parametrize("resource", READ_ONLY)
def test_options_on_a_read_only_element(client, resource):
    assert client.options(f"/api/{resource}/1").headers["allow"] == "GET, HEAD, DELETE, OPTIONS"


@pytest.mark.parametrize(
    "method, url, allow",
    [
        ("DELETE", "/api/applications", "GET, HEAD, POST, OPTIONS"),
        ("POST", "/api/applications/1", "GET, HEAD, PUT, PATCH, DELETE, OPTIONS"),
        ("PATCH", "/api/installations/1", "GET, HEAD, DELETE, OPTIONS"),
        ("PUT", "/api/dependencies/1", "GET, HEAD, DELETE, OPTIONS"),
    ],
)
def test_405_with_allow_complete(client, method, url, allow):
    response = client.request(method, url, json={})
    assert response.status_code == 405
    assert response.headers["allow"] == allow


def test_options_unknown_path_404(client):
    assert client.options("/api/unknown").status_code == 404


# --- PUT --------------------------------------------------------------------


def test_put_replaces_all_200(client, dataset):
    url = f"/api/applications/{dataset['application']['id']}"
    body = {"identifier": "reglement", "name": "Règlement", "trigram": "xyz"}
    response = client.put(url, json=body)
    assert response.status_code == 200
    assert response.json() == {"id": dataset["application"]["id"], **body}
    # idempotent : rejouer donne le même résultat
    assert client.put(url, json=body).json() == response.json()


def test_put_missing_optional_field_gets_default_value(client):
    environment = create(client, "environments", code="int", label="Intégration", promotion_order=1)
    response = client.put(f"/api/environments/{environment['id']}", json={"code": "int", "label": "Intégration"})
    assert response.status_code == 200
    assert response.json()["promotion_order"] is None


def test_put_missing_required_field_422(client, dataset):
    response = client.put(f"/api/applications/{dataset['application']['id']}", json={"name": "Seulement le nom"})
    assert response.status_code == 422


def test_put_does_not_create_404(client):
    response = client.put("/api/applications/999", json={"identifier": "a", "name": "A", "trigram": "abc"})
    assert response.status_code == 404


def test_put_duplicate_409(client, dataset):
    other = create(client, "applications", identifier="facture", name="Facture", trigram="abc")
    response = client.put(
        f"/api/applications/{other['id']}", json={"identifier": "paiement", "name": "Facture", "trigram": "abc"}
    )
    assert response.status_code == 409


def test_put_applies_same_rules_as_patch(client, deployment):
    # changer le module d'un emplacement qui a des installations : refusé, en PUT comme en PATCH
    create(client, "installations", **installation_body(deployment))
    web = create(
        client,
        "modules",
        application_id=deployment["application"]["id"],
        code="web",
        name="Web",
        type="BUSINESS_PROJECT",
    )
    response = client.put(
        f"/api/slots/{deployment['slot']['id']}",
        json={"namespace_id": deployment["namespace"]["id"], "module_id": web["id"], "release_name": "batch-paie"},
    )
    assert response.status_code == 409


# --- 400 / 404 / 415 / 422 --------------------------------------------------


def test_malformed_json_400(client):
    response = client.post("/api/applications", content="{pas du json", headers={"content-type": "application/json"})
    assert response.status_code == 400
    assert response.json() == {"detail": "Corps JSON mal formé"}


@pytest.mark.parametrize("headers", [{"content-type": "text/plain"}, {}])
def test_body_that_is_not_json_415(client, headers):
    response = client.post("/api/applications", content="identifier=a", headers=headers)
    assert response.status_code == 415


def test_creation_without_body_422(client):
    # Sans corps, pas de 415 (rien à lire) : c'est le contenu manquant qui est refusé.
    assert client.post("/api/applications").status_code == 422


def test_json_with_charset_accepted(client):
    response = client.post(
        "/api/applications",
        content='{"identifier": "a", "name": "A", "trigram": "abc"}',
        headers={"content-type": "application/json; charset=utf-8"},
    )
    assert response.status_code == 201


def test_invalid_url_parameter_400(client):
    assert client.get("/api/modules", params={"type": "UNKNOWN"}).status_code == 400
    assert client.get("/api/modules", params={"application_id": "abc"}).status_code == 400


def test_non_numeric_identifier_404(client):
    response = client.get("/api/applications/abc")
    assert response.status_code == 404
    assert response.json() == {"detail": "/api/applications/abc introuvable"}


def test_invalid_content_still_422(client):
    response = client.post("/api/applications", json={"identifier": "a", "name": "A", "trigram": "ab"})
    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["body", "trigram"]
