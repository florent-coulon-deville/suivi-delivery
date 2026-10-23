"""Tests des routes /api/installations."""

import pytest

from tests.conftest import create, installation_body


def test_create_201(client, deployment):
    body = installation_body(deployment, date="2026-10-01T10:00:00Z")
    response = client.post("/api/installations", json=body)
    assert response.status_code == 201
    assert response.headers["Location"] == f"/api/installations/{response.json()['id']}"
    assert response.json()["date"] == "2026-10-01T10:00:00Z"


def test_date_defaults_to_now(client, deployment):
    installation = create(client, "installations", **installation_body(deployment))
    assert installation["date"].startswith("20")


@pytest.mark.parametrize(
    "field",
    [
        "slot_id",
        "module_version_id",
        "technical_parameter_id",
        "application_parameter_id",
    ],
)
def test_nonexistent_reference_422(client, deployment, field):
    assert client.post("/api/installations", json=installation_body(deployment, **{field: 999})).status_code == 422


def test_swapped_parameters_422(client, deployment):
    body = installation_body(
        deployment,
        technical_parameter_id=deployment["application_parameter"]["id"],
        application_parameter_id=deployment["technical_parameter"]["id"],
    )
    assert client.post("/api/installations", json=body).status_code == 422


def test_parameter_not_assigned_to_namespace_422(client, deployment):
    client.patch(f"/api/parameters/{deployment['technical_parameter']['id']}", json={"namespace_ids": []})
    response = client.post("/api/installations", json=installation_body(deployment))
    assert response.status_code == 422
    assert "n'est pas affecté au namespace" in response.json()["detail"]


def test_parameter_from_another_module_422(client, deployment):
    # Un paramètre du même namespace, mais qui configure un autre module : refusé.
    other = create(
        client,
        "modules",
        application_id=deployment["application"]["id"],
        code="web",
        name="Web",
        type="BUSINESS_PROJECT",
    )
    parameter = create(
        client,
        "parameters",
        module_id=other["id"],
        name="tech-web",
        type="TECHNICAL",
        namespace_ids=[deployment["namespace"]["id"]],
    )
    response = client.post(
        "/api/installations", json=installation_body(deployment, technical_parameter_id=parameter["id"])
    )
    assert response.status_code == 422
    assert "n'est pas un paramètre du module batch-paie" in response.json()["detail"]


def test_module_from_another_application_422(client, deployment):
    other = create(client, "applications", identifier="facture", name="Facture", trigram="abc")
    module = create(client, "modules", application_id=other["id"], code="web", name="Web", type="BUSINESS_PROJECT")
    version = create(client, "module-versions", module_id=module["id"], number="1.0.0", type="RELEASE")
    body = installation_body(deployment, module_version_id=version["id"])
    assert client.post("/api/installations", json=body).status_code == 422


def test_slot_history_most_recent_first(client, deployment):
    v2 = create(client, "module-versions", module_id=deployment["module"]["id"], number="2.4.0", type="RELEASE")
    create(client, "installations", **installation_body(deployment, date="2026-09-01T10:00:00Z"))
    create(
        client,
        "installations",
        **installation_body(deployment, module_version_id=v2["id"], date="2026-10-01T10:00:00Z"),
    )
    history = client.get("/api/installations", params={"slot_id": deployment["slot"]["id"]}).json()
    # la première de la liste est ce qui tourne actuellement sur l'emplacement
    assert [i["module_version_id"] for i in history] == [v2["id"], deployment["module_version"]["id"]]


def test_where_a_version_is_installed(client, deployment):
    create(client, "installations", **installation_body(deployment))
    response = client.get("/api/installations", params={"module_version_id": deployment["module_version"]["id"]})
    assert [i["slot_id"] for i in response.json()] == [deployment["slot"]["id"]]


def test_no_update_405(client, deployment):
    installation = create(client, "installations", **installation_body(deployment))
    assert client.patch(f"/api/installations/{installation['id']}", json={}).status_code == 405


def test_delete_204_then_404(client, deployment):
    installation = create(client, "installations", **installation_body(deployment))
    assert client.delete(f"/api/installations/{installation['id']}").status_code == 204
    assert client.get(f"/api/installations/{installation['id']}").status_code == 404
