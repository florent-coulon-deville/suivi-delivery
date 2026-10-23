"""Tests des règles d'ensemble (app/consistency.py) et de l'ordre des environnements.

- un namespace est sur un cluster du même type (prod / hors prod) que son environnement ;
- en prod, seules des versions RELEASE tournent ;
- un module requis doit tourner dans l'environnement, même sans condition de version.
"""

from tests.conftest import create


def namespace_prod(client, dataset) -> dict:
    """Un namespace en prod, avec un module web, son emplacement et des paramètres prêts pour une installation."""
    application_id = dataset["application"]["id"]
    module = create(client, "modules", application_id=application_id, code="web", name="Web", type="BUSINESS_PROJECT")
    namespace = create(
        client,
        "namespaces",
        application_id=application_id,
        environment_id=dataset["prod"]["id"],
        cluster_id=dataset["cluster_prod"]["id"],
        suffix="app",
        network_zone_id=dataset["zone"]["id"],
    )
    technical_parameter = create(
        client,
        "parameters",
        module_id=module["id"],
        name="tech-prod",
        type="TECHNICAL",
        namespace_ids=[namespace["id"]],
    )
    application_parameter = create(
        client,
        "parameters",
        module_id=module["id"],
        name="appli-prod",
        type="APPLICATION",
        namespace_ids=[namespace["id"]],
    )
    return {
        "namespace": namespace,
        "module": module,
        "slot": create(client, "slots", namespace_id=namespace["id"], module_id=module["id"], release_name="app"),
        "technical_parameter": technical_parameter,
        "application_parameter": application_parameter,
    }


def install(client, target: dict, version: dict):
    return client.post(
        "/api/installations",
        json={
            "slot_id": target["slot"]["id"],
            "module_version_id": version["id"],
            "technical_parameter_id": target["technical_parameter"]["id"],
            "application_parameter_id": target["application_parameter"]["id"],
        },
    )


# --- Ordre des environnements (information, ne bloque rien) ------------------


def test_environments_sorted_by_order(client):
    create(client, "environments", code="prod", label="Production", is_prod=True, promotion_order=4)
    create(client, "environments", code="int", label="Intégration", promotion_order=1)
    create(client, "environments", code="bac", label="Bac à sable")  # sans ordre : à la fin
    create(client, "environments", code="preprod", label="Recette", promotion_order=3)
    codes = [e["code"] for e in client.get("/api/environments").json()]
    assert codes == ["int", "preprod", "prod", "bac"]


def test_order_optional_and_editable(client):
    environment = create(client, "environments", code="int", label="Intégration", promotion_order=1)
    url = f"/api/environments/{environment['id']}"
    assert client.patch(url, json={"promotion_order": None}).json()["promotion_order"] is None
    assert client.patch(url, json={"promotion_order": 0}).status_code == 422


# --- Type de cluster --------------------------------------------------------


def test_cluster_of_the_other_type_422(client, dataset):
    body = {
        "application_id": dataset["application"]["id"],
        "environment_id": dataset["prod"]["id"],
        "cluster_id": dataset["cluster"]["id"],
        "suffix": "app",
        "network_zone_id": dataset["zone"]["id"],
    }
    response = client.post("/api/namespaces", json=body)
    assert response.status_code == 422
    assert response.json() == {"detail": "L'environnement prod demande un cluster de prod"}


def test_change_type_of_a_used_cluster_409(client, dataset):
    namespace_prod(client, dataset)
    assert client.patch(f"/api/clusters/{dataset['cluster_prod']['id']}", json={"is_prod": False}).status_code == 409
    assert client.patch(f"/api/environments/{dataset['prod']['id']}", json={"is_prod": False}).status_code == 409


# --- Pas de snapshot en prod ------------------------------------------------


def test_snapshot_forbidden_in_prod_409(client, dataset):
    target = namespace_prod(client, dataset)
    module = target["module"]
    snapshot = create(client, "module-versions", module_id=module["id"], number="1.0.0-SNAPSHOT")
    response = install(client, target, snapshot)
    assert response.status_code == 409
    assert "est un snapshot : interdit en prod" in response.json()["detail"]
    release = create(client, "module-versions", module_id=module["id"], number="1.0.0", type="RELEASE")
    assert install(client, target, release).status_code == 201
    # repasser la release en snapshot alors qu'elle tourne en prod : refusé
    assert client.patch(f"/api/module-versions/{release['id']}", json={"type": "SNAPSHOT"}).status_code == 409


# --- Dépendance sans condition de version -----------------------------------


def test_required_module_missing_even_without_condition_409(client, deployment):
    base = create(client, "applications", identifier="socle", name="Socle", trigram="soc")
    auth = create(client, "modules", application_id=base["id"], code="auth", name="Authentification", type="CAPABILITY")
    create(client, "dependencies", module_id=deployment["module"]["id"], depends_on_id=auth["id"])
    response = client.post(
        "/api/installations",
        json={
            "slot_id": deployment["slot"]["id"],
            "module_version_id": deployment["module_version"]["id"],
            "technical_parameter_id": deployment["technical_parameter"]["id"],
            "application_parameter_id": deployment["application_parameter"]["id"],
        },
    )
    assert response.status_code == 409
    assert "batch-paie 2.3.0 a besoin de auth, qui n'est pas installé en int" in response.json()["detail"]


def test_new_dependency_contradicted_by_what_is_running_409(client, deployment):
    client.post(
        "/api/installations",
        json={
            "slot_id": deployment["slot"]["id"],
            "module_version_id": deployment["module_version"]["id"],
            "technical_parameter_id": deployment["technical_parameter"]["id"],
            "application_parameter_id": deployment["application_parameter"]["id"],
        },
    )
    base = create(client, "applications", identifier="socle", name="Socle", trigram="soc")
    auth = create(client, "modules", application_id=base["id"], code="auth", name="Authentification", type="CAPABILITY")
    # le batch tourne en int sans l'authentification : déclarer qu'il en dépend contredirait la réalité saisie
    response = client.post(
        "/api/dependencies", json={"module_id": deployment["module"]["id"], "depends_on_id": auth["id"]}
    )
    assert response.status_code == 409
