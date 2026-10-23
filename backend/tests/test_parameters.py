"""Tests des routes /api/parameters : un paramètre appartient à un module ; son nom est libre
(ex. une version), en minuscules, unique par module et par type."""

from tests.conftest import create, installation_body


def module_of(client, dataset, code="web-paie") -> dict:
    return create(
        client, "modules", application_id=dataset["application"]["id"], code=code, name=code, type="BUSINESS_PROJECT"
    )


def test_create_201(client, deployment):
    body = {
        "module_id": deployment["module"]["id"],
        "name": "BDD",
        "type": "TECHNICAL",
        "namespace_ids": [deployment["namespace"]["id"]],
    }
    response = client.post("/api/parameters", json=body)
    assert response.status_code == 201
    assert response.json() == {"id": response.json()["id"], **body, "name": "bdd"}


def test_module_required_and_existing_422(client, dataset):
    assert client.post("/api/parameters", json={"name": "p", "type": "TECHNICAL"}).status_code == 422
    assert client.post("/api/parameters", json={"module_id": 999, "name": "p", "type": "TECHNICAL"}).status_code == 422
    # application_id n'est pas un champ du paramètre : il appartient à un module (champ inconnu, 422).
    body = {"application_id": dataset["application"]["id"], "name": "p", "type": "TECHNICAL"}
    assert client.post("/api/parameters", json=body).status_code == 422


def test_assigned_to_no_namespace_by_default(client, dataset):
    parameter = create(client, "parameters", module_id=module_of(client, dataset)["id"], name="p", type="APPLICATION")
    assert parameter["namespace_ids"] == []


def test_unknown_type_422(client, dataset):
    body = {"module_id": module_of(client, dataset)["id"], "name": "p", "type": "OTHER"}
    assert client.post("/api/parameters", json=body).status_code == 422


def test_name_unique_per_module_and_type_409(client, deployment):
    body = {"module_id": deployment["module"]["id"], "name": "TECH", "type": "TECHNICAL"}
    response = client.post("/api/parameters", json=body)
    assert response.status_code == 409
    assert "batch-paie" in response.json()["detail"]
    # Même nom, autre type : accepté.
    assert client.post("/api/parameters", json={**body, "type": "APPLICATION"}).status_code == 201


def test_free_name_in_lowercase(client, deployment):
    for name in ("2.3", "1.0-RC", "Version du 12 octobre"):
        body = {"module_id": deployment["module"]["id"], "name": name, "type": "TECHNICAL"}
        assert create(client, "parameters", **body)["name"] == name.lower()
    body = {"module_id": deployment["module"]["id"], "name": "x" * 51, "type": "TECHNICAL"}
    assert client.post("/api/parameters", json=body).status_code == 422


def test_same_name_in_two_modules_of_the_application(client, deployment):
    other = module_of(client, deployment)
    assert create(client, "parameters", module_id=other["id"], name="tech", type="TECHNICAL")["name"] == "tech"


def test_namespace_nonexistent_or_from_another_application_422(client, deployment):
    other = create(client, "applications", identifier="facture", name="Facture", trigram="abc")
    module = create(client, "modules", application_id=other["id"], code="web", name="Web", type="BUSINESS_PROJECT")
    body = {"module_id": module["id"], "name": "p", "type": "TECHNICAL"}
    assert client.post("/api/parameters", json={**body, "namespace_ids": [999]}).status_code == 422
    response = client.post("/api/parameters", json={**body, "namespace_ids": [deployment["namespace"]["id"]]})
    assert response.status_code == 422


def test_filters(client, deployment):
    namespace_id = deployment["namespace"]["id"]
    other = module_of(client, deployment)
    create(client, "parameters", module_id=other["id"], name="free", type="TECHNICAL")
    for_module = client.get("/api/parameters", params={"module_id": deployment["module"]["id"]}).json()
    assert [p["name"] for p in for_module] == ["appli", "tech"]
    for_application = client.get("/api/parameters", params={"application_id": deployment["application"]["id"]})
    assert [p["name"] for p in for_application.json()] == ["appli", "free", "tech"]
    assigned = client.get("/api/parameters", params={"namespace_id": namespace_id}).json()
    assert [p["name"] for p in assigned] == ["appli", "tech"]


def test_update_assigned_namespaces(client, deployment):
    url = f"/api/parameters/{deployment['technical_parameter']['id']}"
    namespace_id = deployment["namespace"]["id"]
    assert client.patch(url, json={"namespace_ids": []}).json()["namespace_ids"] == []
    response = client.patch(url, json={"namespace_ids": [namespace_id, namespace_id]})  # doublon ignoré
    assert response.json()["namespace_ids"] == [namespace_id]
    assert client.patch(url, json={"namespace_ids": [999]}).status_code == 422
    assert client.patch(url, json={"name": "appli"}).status_code == 200  # autre type : pas de conflit
    create(client, "parameters", module_id=deployment["module"]["id"], name="other", type="TECHNICAL")
    assert client.patch(url, json={"name": "other"}).status_code == 409
    assert client.patch("/api/parameters/999", json={"name": "x"}).status_code == 404


def test_change_module(client, deployment):
    other = module_of(client, deployment)
    url = f"/api/parameters/{deployment['technical_parameter']['id']}"
    # Pas encore utilisé par une installation : accepté.
    assert client.patch(url, json={"module_id": other["id"]}).json()["module_id"] == other["id"]
    assert client.patch(url, json={"module_id": deployment["module"]["id"]}).status_code == 200
    # Utilisé par une installation : refusé (elle utiliserait le paramètre d'un autre module).
    create(client, "installations", **installation_body(deployment))
    response = client.patch(url, json={"module_id": other["id"]})
    assert response.status_code == 409
    assert "installation" in response.json()["detail"]


def test_delete(client, dataset):
    parameter = create(client, "parameters", module_id=module_of(client, dataset)["id"], name="p", type="TECHNICAL")
    assert client.delete(f"/api/parameters/{parameter['id']}").status_code == 204
    assert client.get(f"/api/parameters/{parameter['id']}").status_code == 404


def test_installed_parameter(client, deployment):
    # Utilisé par une installation : ni supprimé, ni changé de type, ni retiré de son namespace.
    create(client, "installations", **installation_body(deployment))
    url = f"/api/parameters/{deployment['technical_parameter']['id']}"
    response = client.delete(url)
    assert response.status_code == 409
    assert response.json()["detail"] == "Paramètre utilisé par au moins une installation"
    assert client.patch(url, json={"type": "APPLICATION", "name": "new"}).status_code == 409
    assert client.patch(url, json={"namespace_ids": []}).status_code == 409
    # Son nom, lui, peut changer.
    assert client.patch(url, json={"name": "2.0"}).json()["name"] == "2.0"


def test_delete_linked_module_or_namespace_409(client, dataset):
    module = module_of(client, dataset)
    create(client, "parameters", module_id=module["id"], name="p", type="TECHNICAL")
    response = client.delete(f"/api/modules/{module['id']}")
    assert response.status_code == 409
    assert response.json()["detail"] == "Module qui a encore des paramètres"


def test_module_with_parameters_cannot_change_application(client, dataset):
    module = module_of(client, dataset)
    create(client, "parameters", module_id=module["id"], name="p", type="TECHNICAL")
    other = create(client, "applications", identifier="facture", name="Facture", trigram="def")
    response = client.patch(f"/api/modules/{module['id']}", json={"application_id": other["id"]})
    assert response.status_code == 409


def test_linked_namespace_409(client, deployment):
    assert client.delete(f"/api/namespaces/{deployment['namespace']['id']}").status_code == 409
