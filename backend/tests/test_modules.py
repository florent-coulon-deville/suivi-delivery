"""Tests des routes /api/modules."""

from tests.conftest import create


def test_create_201(client, dataset):
    body = {
        "application_id": dataset["application"]["id"],
        "code": "BATCH",
        "name": "Batch de paiement",
        "type": "BUSINESS_PROJECT",
    }
    response = client.post("/api/modules", json=body)
    assert response.status_code == 201
    assert response.json() == {"id": 1, **body, "code": "batch"}
    assert response.headers["Location"] == "/api/modules/1"


def test_nonexistent_application_422(client):
    body = {"application_id": 999, "code": "BATCH", "name": "Batch", "type": "BUSINESS_PROJECT"}
    response = client.post("/api/modules", json=body)
    assert response.status_code == 422
    assert response.json() == {"detail": "Application 999 introuvable"}


def test_code_unique_in_application(client, dataset):
    application_id = dataset["application"]["id"]
    other = create(client, "applications", identifier="FACTURE", name="Facture", trigram="ABC")
    create(client, "modules", application_id=application_id, code="BATCH", name="Batch", type="BUSINESS_PROJECT")
    # même code dans la même application : refusé
    body = {"application_id": application_id, "code": "batch", "name": "Autre", "type": "BUSINESS_PROJECT"}
    assert client.post("/api/modules", json=body).status_code == 409
    # même code dans une autre application : accepté
    create(client, "modules", application_id=other["id"], code="BATCH", name="Batch", type="BUSINESS_PROJECT")


def test_list_by_application(client, dataset):
    other = create(client, "applications", identifier="FACTURE", name="Facture", trigram="ABC")
    create(
        client, "modules", application_id=dataset["application"]["id"], code="WEB", name="Web", type="BUSINESS_PROJECT"
    )
    create(client, "modules", application_id=other["id"], code="BATCH", name="Batch", type="BUSINESS_PROJECT")
    assert [m["code"] for m in client.get("/api/modules").json()] == ["batch", "web"]
    response = client.get("/api/modules", params={"application_id": other["id"]})
    assert [m["code"] for m in response.json()] == ["batch"]


def test_update(client, dataset):
    application_id = dataset["application"]["id"]
    create(client, "modules", application_id=application_id, code="WEB", name="Web", type="BUSINESS_PROJECT")
    module = create(
        client, "modules", application_id=application_id, code="BATCH", name="Batch", type="BUSINESS_PROJECT"
    )
    url = f"/api/modules/{module['id']}"
    assert client.patch(url, json={"name": "Nouveau"}).json()["name"] == "Nouveau"
    assert client.patch(url, json={"code": "WEB"}).status_code == 409
    assert client.patch(url, json={"application_id": 999}).status_code == 422
    assert client.patch("/api/modules/999", json={"name": "X"}).status_code == 404


def test_delete_204_then_404(client, dataset):
    module = create(
        client,
        "modules",
        application_id=dataset["application"]["id"],
        code="BATCH",
        name="Batch",
        type="BUSINESS_PROJECT",
    )
    assert client.delete(f"/api/modules/{module['id']}").status_code == 204
    assert client.get(f"/api/modules/{module['id']}").status_code == 404


# --- Création avec emplacements (with_slots) ------------------------------


def two_namespaces(client, dataset) -> list[dict]:
    """Deux namespaces de l'application du jeu (suffixes app et batch), et un d'une autre application."""
    common = {
        "environment_id": dataset["int"]["id"],
        "cluster_id": dataset["cluster"]["id"],
        "network_zone_id": dataset["zone"]["id"],
    }
    other = create(client, "applications", identifier="facture", name="Facture", trigram="abc")
    create(client, "namespaces", application_id=other["id"], suffix="app", **common)
    return [
        create(client, "namespaces", application_id=dataset["application"]["id"], suffix=suffix, **common)
        for suffix in ("app", "batch")
    ]


def module_body(dataset, **others) -> dict:
    body = {
        "application_id": dataset["application"]["id"],
        "code": "batch_paie",
        "name": "Batch",
        "type": "BUSINESS_PROJECT",
    }
    return {**body, **others}


def test_create_with_slots(client, dataset):
    namespaces = two_namespaces(client, dataset)
    response = client.post("/api/modules", json=module_body(dataset, with_slots=True))
    assert response.status_code == 201
    module = response.json()
    assert "with_slots" not in module
    assert response.headers["Location"] == f"/api/modules/{module['id']}"
    # un emplacement dans chaque namespace de son application seulement ; « _ » remplacé par « - »
    slots = client.get("/api/slots", params={"module_id": module["id"]}).json()
    assert {(e["namespace_id"], e["release_name"]) for e in slots} == {(n["id"], "batch-paie") for n in namespaces}


def test_create_without_slots_by_default(client, dataset):
    two_namespaces(client, dataset)
    create(client, "modules", **module_body(dataset))
    assert client.get("/api/slots").json() == []


def test_create_with_slots_all_or_nothing(client, dataset):
    # Le nom de release est déjà pris dans un namespace : ni le module ni aucun emplacement n'est créé.
    _, batch = two_namespaces(client, dataset)
    web = create(client, "modules", **module_body(dataset, code="web"))
    create(client, "slots", namespace_id=batch["id"], module_id=web["id"], release_name="batch-paie")
    response = client.post("/api/modules", json=module_body(dataset, with_slots=True))
    assert response.status_code == 409
    assert "batch-paie" in response.json()["detail"]
    assert [m["code"] for m in client.get("/api/modules").json()] == ["web"]
    assert len(client.get("/api/slots").json()) == 1


def test_with_slots_rejected_in_put_422(client, dataset):
    module = create(client, "modules", **module_body(dataset))
    response = client.put(f"/api/modules/{module['id']}", json=module_body(dataset, with_slots=True))
    assert response.status_code == 422
