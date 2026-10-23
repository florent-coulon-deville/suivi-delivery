"""Tests des routes /api/namespaces."""

import pytest

from tests.conftest import create


def namespace_body(dataset, **others) -> dict:
    """Corps de création d'un namespace valide, modifiable champ par champ."""
    return {
        "application_id": dataset["application"]["id"],
        "environment_id": dataset["int"]["id"],
        "cluster_id": dataset["cluster"]["id"],
        "suffix": "batch",
        "network_zone_id": dataset["zone"]["id"],
        **others,
    }


def test_create_201_with_computed_name(client, dataset):
    response = client.post("/api/namespaces", json=namespace_body(dataset, suffix="Batch"))
    assert response.status_code == 201
    assert response.headers["Location"] == "/api/namespaces/1"
    namespace = response.json()
    assert namespace["name"] == "abc-paiement-int-batch"
    assert namespace["suffix"] == "batch"


@pytest.mark.parametrize("suffix", [None, "", "my_suffix"])
def test_suffix_required_and_without_underscore_422(client, dataset, suffix):
    assert client.post("/api/namespaces", json=namespace_body(dataset, suffix=suffix)).status_code == 422
    body = namespace_body(dataset)
    del body["suffix"]
    assert client.post("/api/namespaces", json=body).status_code == 422


def test_name_follows_application_changes(client, dataset):
    namespace = create(client, "namespaces", **namespace_body(dataset))
    client.patch(f"/api/applications/{dataset['application']['id']}", json={"identifier": "reglement"})
    assert client.get(f"/api/namespaces/{namespace['id']}").json()["name"] == "abc-reglement-int-batch"


@pytest.mark.parametrize("field", ["application_id", "environment_id", "cluster_id", "network_zone_id"])
def test_nonexistent_reference_422(client, dataset, field):
    assert client.post("/api/namespaces", json=namespace_body(dataset, **{field: 999})).status_code == 422


def test_unknown_network_zone_422(client, dataset):
    response = client.post("/api/namespaces", json=namespace_body(dataset, network_zone_id=999))
    assert response.status_code == 422
    assert response.json() == {"detail": "Zone réseau 999 introuvable"}


def test_environment_and_suffix_unique_in_application(client, dataset):
    create(client, "namespaces", **namespace_body(dataset, suffix="batch"))
    # même environnement, même suffixe : refusé
    assert client.post("/api/namespaces", json=namespace_body(dataset, suffix="BATCH")).status_code == 409
    # autre suffixe, ou autre environnement : accepté
    create(client, "namespaces", **namespace_body(dataset, suffix="web"))
    create(
        client,
        "namespaces",
        **namespace_body(
            dataset, environment_id=dataset["prod"]["id"], cluster_id=dataset["cluster_prod"]["id"], suffix="batch"
        ),
    )
    # plusieurs namespaces pour un même environnement
    assert len(client.get("/api/namespaces").json()) == 3


def test_list_sorted_by_name_and_application(client, dataset):
    other = create(client, "applications", identifier="facture", name="Facture", trigram="abc")
    create(client, "namespaces", **namespace_body(dataset))
    create(client, "namespaces", **namespace_body(dataset, application_id=other["id"]))
    names = [n["name"] for n in client.get("/api/namespaces").json()]
    assert names == ["abc-facture-int-batch", "abc-paiement-int-batch"]
    response = client.get("/api/namespaces", params={"application_id": other["id"]})
    assert [n["name"] for n in response.json()] == ["abc-facture-int-batch"]


def test_update(client, dataset):
    namespace = create(client, "namespaces", **namespace_body(dataset))
    url = f"/api/namespaces/{namespace['id']}"
    response = client.patch(
        url,
        json={
            "environment_id": dataset["prod"]["id"],
            "cluster_id": dataset["cluster_prod"]["id"],
            "network_zone_id": dataset["zone_partenaires"]["id"],
        },
    )
    assert response.status_code == 200
    assert response.json()["name"] == "abc-paiement-prod-batch"
    assert response.json()["network_zone_id"] == dataset["zone_partenaires"]["id"]
    assert client.patch(url, json={"suffix": "web"}).json()["name"] == "abc-paiement-prod-web"


def test_update_errors(client, dataset):
    create(client, "namespaces", **namespace_body(dataset, suffix="web"))
    namespace = create(client, "namespaces", **namespace_body(dataset, suffix="batch"))
    url = f"/api/namespaces/{namespace['id']}"
    assert client.patch(url, json={"suffix": "web"}).status_code == 409  # deviendrait un doublon
    assert client.patch(url, json={"suffix": None}).status_code == 422  # obligatoire
    assert client.patch(url, json={"cluster_id": 999}).status_code == 422
    assert client.patch(url, json={"network_zone_id": None}).status_code == 422
    assert client.patch(url, json={"network_zone_id": 999}).status_code == 422
    assert client.patch("/api/namespaces/999", json={"suffix": "x"}).status_code == 404


def test_delete_204_then_404(client, dataset):
    namespace = create(client, "namespaces", **namespace_body(dataset))
    assert client.delete(f"/api/namespaces/{namespace['id']}").status_code == 204
    assert client.get(f"/api/namespaces/{namespace['id']}").status_code == 404


def test_same_namespace_on_two_clusters(client, dataset):
    # Le même nom une fois par cluster : accepté ; deux fois sur le même cluster : refusé.
    other = create(client, "clusters", code="cb03", label="Autre cluster hors prod")
    first = create(client, "namespaces", **namespace_body(dataset))
    second = create(client, "namespaces", **namespace_body(dataset, cluster_id=other["id"]))
    assert first["name"] == second["name"] == "abc-paiement-int-batch"
    response = client.post("/api/namespaces", json=namespace_body(dataset, cluster_id=other["id"]))
    assert response.status_code == 409
    assert "cb03" in response.json()["detail"]
    # Déplacer le second sur le cluster du premier : il deviendrait un doublon.
    assert (
        client.patch(f"/api/namespaces/{second['id']}", json={"cluster_id": dataset["cluster"]["id"]}).status_code
        == 409
    )


# --- Création groupée : POST /api/namespaces/batch ---------------------------------


def batch_body(dataset, cluster_ids: list[int], **others) -> dict:
    """Corps d'une création groupée valide, modifiable champ par champ."""
    body = namespace_body(dataset, cluster_ids=cluster_ids, **others)
    del body["cluster_id"]
    return body


def two_modules(client, dataset) -> list[dict]:
    """Deux modules de l'application du jeu, dont un avec un « _ » dans son code."""
    application_id = dataset["application"]["id"]
    return [
        create(client, "modules", application_id=application_id, code="web", name="Web", type="BUSINESS_PROJECT"),
        create(
            client, "modules", application_id=application_id, code="batch_paie", name="Batch", type="BUSINESS_PROJECT"
        ),
    ]


def test_batch_on_two_clusters_with_slots(client, dataset):
    other = create(client, "clusters", code="cb03", label="Autre cluster hors prod")
    web, batch_module = two_modules(client, dataset)
    response = client.post("/api/namespaces/batch", json=batch_body(dataset, [dataset["cluster"]["id"], other["id"]]))
    assert response.status_code == 201
    batch = response.json()
    assert [(n["name"], n["cluster_id"]) for n in batch["namespaces"]] == [
        ("abc-paiement-int-batch", dataset["cluster"]["id"]),
        ("abc-paiement-int-batch", other["id"]),
    ]
    # un emplacement par module et par namespace ; « _ » remplacé par « - » dans le nom de release
    releases = ((batch_module, "batch-paie"), (web, "web"))
    expected = {(n["id"], m["id"], r) for n in batch["namespaces"] for m, r in releases}
    assert {(e["namespace_id"], e["module_id"], e["release_name"]) for e in batch["slots"]} == expected
    assert len(client.get("/api/slots").json()) == 4


def test_batch_without_slots(client, dataset):
    two_modules(client, dataset)
    body = batch_body(dataset, [dataset["cluster"]["id"]], with_slots=False)
    batch = client.post("/api/namespaces/batch", json=body).json()
    assert len(batch["namespaces"]) == 1
    assert batch["slots"] == []
    assert client.get("/api/slots").json() == []


def test_batch_all_or_nothing(client, dataset):
    # Le namespace existe déjà sur cb03 : tout le lot est refusé, rien n'est créé sur cb01.
    other = create(client, "clusters", code="cb03", label="Autre cluster hors prod")
    two_modules(client, dataset)
    create(client, "namespaces", **namespace_body(dataset, cluster_id=other["id"]))
    response = client.post("/api/namespaces/batch", json=batch_body(dataset, [dataset["cluster"]["id"], other["id"]]))
    assert response.status_code == 409
    assert "cb03" in response.json()["detail"]
    assert len(client.get("/api/namespaces").json()) == 1
    assert client.get("/api/slots").json() == []


def test_batch_cluster_of_wrong_type_422_and_nothing_created(client, dataset):
    body = batch_body(dataset, [dataset["cluster"]["id"], dataset["cluster_prod"]["id"]])
    response = client.post("/api/namespaces/batch", json=body)
    assert response.status_code == 422
    assert response.json() == {"detail": "L'environnement int demande un cluster de hors prod"}
    assert client.get("/api/namespaces").json() == []


def test_batch_duplicate_release_name_409(client, dataset):
    # « batch_paie » et « batch-paie » donneraient le même nom de release : refusé, rien n'est créé.
    two_modules(client, dataset)
    application_id = dataset["application"]["id"]
    create(client, "modules", application_id=application_id, code="batch-paie", name="Bis", type="BUSINESS_PROJECT")
    response = client.post("/api/namespaces/batch", json=batch_body(dataset, [dataset["cluster"]["id"]]))
    assert response.status_code == 409
    assert "batch-paie" in response.json()["detail"]
    assert client.get("/api/namespaces").json() == []


@pytest.mark.parametrize(
    ("cluster_ids", "others"),
    [([], {}), ([1, 1], {}), ([1], {"suffix": "my_suffix"}), ([1], {"application_id": 999}), ([999], {})],
)
def test_batch_invalid_422(client, dataset, cluster_ids, others):
    assert client.post("/api/namespaces/batch", json=batch_body(dataset, cluster_ids, **others)).status_code == 422
    assert client.get("/api/namespaces").json() == []


def test_batch_logged_in_audit_log(client, dataset):
    two_modules(client, dataset)
    client.post("/api/namespaces/batch", json=batch_body(dataset, [dataset["cluster"]["id"]]))
    objects = [row["object"] for row in client.get("/api/audit-log").json()]
    assert objects.count("namespaces") == 1
    assert objects.count("slots") == 2
