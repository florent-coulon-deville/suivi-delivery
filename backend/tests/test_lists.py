"""Tests des listes gérées dans l'outil : /api/environments, /api/clusters et /api/network-zones.

Les trois ressources fonctionnent de la même façon : chaque test est joué sur les trois.
"""

import pytest

from tests.conftest import create

LISTS = pytest.mark.parametrize("resource", ["environments", "clusters", "network-zones"])


@LISTS
def test_list_empty_at_start(client, resource):
    response = client.get(f"/api/{resource}")
    assert response.status_code == 200
    assert response.json() == []


@LISTS
def test_create_201_with_location_and_lowercase_code(client, resource):
    response = client.post(f"/api/{resource}", json={"code": "ABC1", "label": "  Libellé  "})
    assert response.status_code == 201
    assert response.json()["code"] == "abc1"
    assert response.json()["label"] == "Libellé"
    assert response.headers["Location"] == f"/api/{resource}/1"


@LISTS
def test_list_sorted_by_code(client, resource):
    create(client, resource, code="Z1", label="Z")
    create(client, resource, code="A1", label="A")
    assert [e["code"] for e in client.get(f"/api/{resource}").json()] == ["a1", "z1"]


@LISTS
def test_read_200_and_404(client, resource):
    element = create(client, resource, code="A1", label="A")
    assert client.get(f"/api/{resource}/{element['id']}").json() == element
    assert client.get(f"/api/{resource}/999").status_code == 404


@LISTS
def test_code_already_used_409(client, resource):
    create(client, resource, code="A1", label="A")
    assert client.post(f"/api/{resource}", json={"code": "a1", "label": "B"}).status_code == 409


@LISTS
@pytest.mark.parametrize(
    "body",
    [
        {"code": "A1"},  # libellé manquant
        {"code": "A 1", "label": "A"},  # caractère interdit
        {"code": "A1", "label": "A", "unknown": 1},  # champ inconnu
    ],
)
def test_create_invalid_422(client, resource, body):
    assert client.post(f"/api/{resource}", json=body).status_code == 422


@LISTS
def test_update(client, resource):
    element = create(client, resource, code="A1", label="Ancien")
    response = client.patch(f"/api/{resource}/{element['id']}", json={"label": "Nouveau"})
    assert response.status_code == 200
    assert response.json() == {**element, "label": "Nouveau"}
    # garder son propre code n'est pas un doublon
    assert client.patch(f"/api/{resource}/{element['id']}", json={"code": "a1"}).status_code == 200


@LISTS
def test_update_errors(client, resource):
    create(client, resource, code="A1", label="A")
    other = create(client, resource, code="B1", label="B")
    assert client.patch(f"/api/{resource}/{other['id']}", json={"code": "A1"}).status_code == 409
    assert client.patch(f"/api/{resource}/{other['id']}", json={"label": None}).status_code == 422
    assert client.patch(f"/api/{resource}/999", json={"label": "X"}).status_code == 404


@LISTS
def test_delete_204_then_404(client, resource):
    element = create(client, resource, code="A1", label="A")
    response = client.delete(f"/api/{resource}/{element['id']}")
    assert response.status_code == 204
    assert response.content == b""
    assert client.delete(f"/api/{resource}/{element['id']}").status_code == 404


def test_environment_is_prod(client):
    assert create(client, "environments", code="INT", label="A")["is_prod"] is False
    assert create(client, "environments", code="PROD", label="P", is_prod=True)["is_prod"] is True


@pytest.mark.parametrize("resource, key", [("environments", "int"), ("clusters", "cluster"), ("network-zones", "zone")])
def test_delete_used_by_a_namespace_409(client, dataset, resource, key):
    create(
        client,
        "namespaces",
        application_id=dataset["application"]["id"],
        environment_id=dataset["int"]["id"],
        cluster_id=dataset["cluster"]["id"],
        suffix="batch",
        network_zone_id=dataset["zone"]["id"],
    )
    assert client.delete(f"/api/{resource}/{dataset[key]['id']}").status_code == 409


def test_unsupported_method_405(client):
    assert client.put("/api/environments", json={}).status_code == 405
