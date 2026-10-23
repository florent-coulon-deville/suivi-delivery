"""Tests des routes /api/slots.

Un emplacement est réservé à un module dès sa création, même vide.
"""

from tests.conftest import create, installation_body


def module_web(client, d: dict) -> dict:
    """Un second module (web) dans l'application de la fixture deploiement."""
    return create(
        client, "modules", application_id=d["application"]["id"], code="web", name="Web", type="BUSINESS_PROJECT"
    )


def test_create_201(client, deployment):
    web = module_web(client, deployment)
    body = {"namespace_id": deployment["namespace"]["id"], "module_id": web["id"], "release_name": "Web-Front"}
    response = client.post("/api/slots", json=body)
    assert response.status_code == 201
    assert response.json() == {"id": response.json()["id"], **body, "release_name": "web-front"}


def test_references_nonexistent_or_missing_422(client, deployment):
    namespace_id, module_id = deployment["namespace"]["id"], deployment["module"]["id"]
    assert (
        client.post("/api/slots", json={"namespace_id": 999, "module_id": module_id, "release_name": "x"}).status_code
        == 422
    )
    assert (
        client.post(
            "/api/slots", json={"namespace_id": namespace_id, "module_id": 999, "release_name": "x"}
        ).status_code
        == 422
    )
    assert (
        client.post("/api/slots", json={"namespace_id": namespace_id, "release_name": "x"}).status_code == 422
    )  # module absent


def test_module_from_another_application_422(client, deployment):
    other = create(client, "applications", identifier="facture", name="Facture", trigram="abc")
    module = create(client, "modules", application_id=other["id"], code="web", name="Web", type="BUSINESS_PROJECT")
    response = client.post(
        "/api/slots",
        json={"namespace_id": deployment["namespace"]["id"], "module_id": module["id"], "release_name": "web"},
    )
    assert response.status_code == 422
    assert response.json() == {"detail": "Le module n'appartient pas à l'application du namespace"}


def test_release_name_unique_in_namespace(client, deployment):
    body = {
        "namespace_id": deployment["namespace"]["id"],
        "module_id": deployment["module"]["id"],
        "release_name": "batch-paie",
    }
    assert client.post("/api/slots", json=body).status_code == 409
    # même nom dans un autre namespace : accepté
    other = create(
        client,
        "namespaces",
        application_id=deployment["application"]["id"],
        environment_id=deployment["prod"]["id"],
        cluster_id=deployment["cluster_prod"]["id"],
        suffix="batch",
        network_zone_id=deployment["zone"]["id"],
    )
    create(client, "slots", **{**body, "namespace_id": other["id"]})


def test_several_slots_in_a_namespace(client, deployment):
    namespace_id = deployment["namespace"]["id"]
    web = module_web(client, deployment)
    create(client, "slots", namespace_id=namespace_id, module_id=web["id"], release_name="web")
    response = client.get("/api/slots", params={"namespace_id": namespace_id})
    assert [e["release_name"] for e in response.json()] == ["batch-paie", "web"]
    # où le module web a-t-il sa place ?
    response = client.get("/api/slots", params={"module_id": web["id"]})
    assert [e["release_name"] for e in response.json()] == ["web"]


def test_update(client, deployment):
    web = module_web(client, deployment)
    slot = create(client, "slots", namespace_id=deployment["namespace"]["id"], module_id=web["id"], release_name="web")
    url = f"/api/slots/{slot['id']}"
    assert client.patch(url, json={"release_name": "web2"}).json()["release_name"] == "web2"
    assert client.patch(url, json={"release_name": "batch-paie"}).status_code == 409
    assert client.patch(url, json={"namespace_id": 999}).status_code == 422
    assert client.patch("/api/slots/999", json={"release_name": "x"}).status_code == 404


def test_change_module_only_if_empty(client, deployment):
    web = module_web(client, deployment)
    url = f"/api/slots/{deployment['slot']['id']}"
    assert client.patch(url, json={"module_id": web["id"]}).status_code == 200  # vide : autorisé
    assert client.patch(url, json={"module_id": deployment["module"]["id"]}).status_code == 200
    create(client, "installations", **installation_body(deployment))
    assert client.patch(url, json={"module_id": web["id"]}).status_code == 409  # déjà utilisé


def test_install_another_module_422(client, deployment):
    web = module_web(client, deployment)
    version = create(client, "module-versions", module_id=web["id"], number="1.0.0")
    response = client.post("/api/installations", json=installation_body(deployment, module_version_id=version["id"]))
    assert response.status_code == 422
    assert response.json() == {"detail": "L'emplacement batch-paie est réservé au module batch-paie"}


def test_delete(client, deployment):
    url = f"/api/slots/{deployment['slot']['id']}"
    create(client, "installations", **installation_body(deployment))
    assert client.delete(url).status_code == 409  # a déjà des installations
    web = module_web(client, deployment)
    other = create(client, "slots", namespace_id=deployment["namespace"]["id"], module_id=web["id"], release_name="web")
    assert client.delete(f"/api/slots/{other['id']}").status_code == 204


def test_delete_module_with_a_slot_409(client, deployment):
    web = module_web(client, deployment)
    create(client, "slots", namespace_id=deployment["namespace"]["id"], module_id=web["id"], release_name="web")
    assert client.delete(f"/api/modules/{web['id']}").status_code == 409


def test_change_application_of_module_with_a_slot_409(client, deployment):
    other = create(client, "applications", identifier="facture", name="Facture", trigram="abc")
    response = client.patch(f"/api/modules/{deployment['module']['id']}", json={"application_id": other["id"]})
    assert response.status_code == 409


def test_delete_namespace_with_slots_409(client, deployment):
    # On retire d'abord les paramètres du namespace, pour que seul l'emplacement le retienne.
    for key in ("technical_parameter", "application_parameter"):
        client.patch(f"/api/parameters/{deployment[key]['id']}", json={"namespace_ids": []})
    response = client.delete(f"/api/namespaces/{deployment['namespace']['id']}")
    assert response.status_code == 409
    assert response.json() == {"detail": "Namespace qui a encore des emplacements"}
