"""Tests des routes /api/applications."""

import pytest

from tests.conftest import create


def test_create_201(client):
    response = client.post("/api/applications", json={"identifier": "PAIEMENT", "name": "Paiement", "trigram": "ABC"})
    assert response.status_code == 201
    assert response.json() == {"id": 1, "identifier": "paiement", "name": "Paiement", "trigram": "abc"}
    assert response.headers["Location"] == "/api/applications/1"


def test_identifier_unique_409(client):
    create(client, "applications", identifier="PAIEMENT", name="A", trigram="ABC")
    response = client.post("/api/applications", json={"identifier": "paiement", "name": "B", "trigram": "XYZ"})
    assert response.status_code == 409


def test_same_trigram_for_several_applications(client):
    create(client, "applications", identifier="PAIEMENT", name="A", trigram="ABC")
    create(client, "applications", identifier="FACTURE", name="B", trigram="ABC")
    assert len(client.get("/api/applications").json()) == 2


@pytest.mark.parametrize("trigram", ["AB", "ABCD", "A-C"])
def test_trigram_of_3_characters_422(client, trigram):
    body = {"identifier": "PAIEMENT", "name": "A", "trigram": trigram}
    assert client.post("/api/applications", json=body).status_code == 422


def test_identifier_without_underscore_422(client):
    # « _ » est interdit dans un nom de namespace OpenShift, dont l'identifiant fait partie.
    body = {"identifier": "MY_APP", "name": "A", "trigram": "ABC"}
    assert client.post("/api/applications", json=body).status_code == 422


def test_update(client):
    application = create(client, "applications", identifier="PAIEMENT", name="A", trigram="ABC")
    other = create(client, "applications", identifier="FACTURE", name="B", trigram="ABC")
    url = f"/api/applications/{application['id']}"
    assert client.patch(url, json={"name": "Nouveau"}).json()["name"] == "Nouveau"
    assert client.patch(f"/api/applications/{other['id']}", json={"identifier": "PAIEMENT"}).status_code == 409


@pytest.mark.parametrize("resource", ["namespaces", "modules"])
def test_delete_used_application_409(client, dataset, resource):
    application_id = dataset["application"]["id"]
    if resource == "namespaces":
        create(
            client,
            "namespaces",
            application_id=application_id,
            environment_id=dataset["int"]["id"],
            cluster_id=dataset["cluster"]["id"],
            suffix="batch",
            network_zone_id=dataset["zone"]["id"],
        )
    else:
        create(client, "modules", application_id=application_id, code="BATCH", name="Batch", type="BUSINESS_PROJECT")
    assert client.delete(f"/api/applications/{application_id}").status_code == 409


def test_delete_204_then_404(client):
    application = create(client, "applications", identifier="PAIEMENT", name="A", trigram="ABC")
    assert client.delete(f"/api/applications/{application['id']}").status_code == 204
    assert client.get(f"/api/applications/{application['id']}").status_code == 404
