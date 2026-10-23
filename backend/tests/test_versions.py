"""Tests des versions de module : /api/module-versions (les paramètres n'ont plus de versions).

Les deux ressources fonctionnent de la même façon (un numéro unique pour un parent),
les tests communs sont donc joués sur les deux.
"""

import pytest

from tests.conftest import create, installation_body

# (URL, champ du parent, clé du parent dans la fixture deploiement, champs en plus)
VERSIONS = pytest.mark.parametrize(
    "resource, parent, key, others",
    [
        ("module-versions", "module_id", "module", {"type": "RELEASE"}),
    ],
)


@VERSIONS
def test_create_201(client, deployment, resource, parent, key, others):
    body = {parent: deployment[key]["id"], "number": "3.0.0", **others}
    response = client.post(f"/api/{resource}", json=body)
    assert response.status_code == 201
    assert response.json() == {"id": response.json()["id"], **body}
    assert response.headers["Location"] == f"/api/{resource}/{response.json()['id']}"


@VERSIONS
def test_nonexistent_parent_422(client, deployment, resource, parent, key, others):
    assert client.post(f"/api/{resource}", json={parent: 999, "number": "1", **others}).status_code == 422


@VERSIONS
def test_number_unique_per_parent_409(client, deployment, resource, parent, key, others):
    body = {parent: deployment[key]["id"], "number": "3.0.0", **others}
    create(client, resource, **body)
    assert client.post(f"/api/{resource}", json=body).status_code == 409


@VERSIONS
def test_filter_by_parent(client, deployment, resource, parent, key, others):
    response = client.get(f"/api/{resource}", params={parent: deployment[key]["id"]})
    assert response.status_code == 200
    assert [v["number"] for v in response.json()] == ["2.3.0" if resource == "module-versions" else "1"]
    assert client.get(f"/api/{resource}", params={parent: 999}).json() == []


@VERSIONS
def test_update(client, deployment, resource, parent, key, others):
    version = create(client, resource, **{parent: deployment[key]["id"], "number": "3.0.0", **others})
    url = f"/api/{resource}/{version['id']}"
    assert client.patch(url, json={"number": "3.0.1"}).json()["number"] == "3.0.1"
    already_taken = "2.3.0" if resource == "module-versions" else "1"
    assert client.patch(url, json={"number": already_taken}).status_code == 409
    assert client.patch(url, json={parent: 999}).status_code == 422
    assert client.patch(f"/api/{resource}/999", json={"number": "9.9.9"}).status_code == 404


@VERSIONS
def test_delete_204_then_404(client, deployment, resource, parent, key, others):
    version = create(client, resource, **{parent: deployment[key]["id"], "number": "3.0.0", **others})
    assert client.delete(f"/api/{resource}/{version['id']}").status_code == 204
    assert client.get(f"/api/{resource}/{version['id']}").status_code == 404


@pytest.mark.parametrize(
    "resource, key",
    [
        ("module-versions", "module_version"),
    ],
)
def test_delete_installed_version_409(client, deployment, resource, key):
    create(client, "installations", **installation_body(deployment))
    assert client.delete(f"/api/{resource}/{deployment[key]['id']}").status_code == 409


def test_module_version_type(client, deployment):
    body = {"module_id": deployment["module"]["id"], "number": "3.0.0-SNAPSHOT", "type": "SNAPSHOT"}
    assert client.post("/api/module-versions", json=body).status_code == 201
    body = {**body, "number": "4", "type": "BETA"}
    assert client.post("/api/module-versions", json=body).status_code == 422


def test_version_snapshot_by_default(client, deployment):
    version = create(client, "module-versions", module_id=deployment["module"]["id"], number="3.0.0")
    assert version["type"] == "SNAPSHOT"


def test_delete_module_with_versions_409(client, deployment):
    assert client.delete(f"/api/modules/{deployment['module']['id']}").status_code == 409
