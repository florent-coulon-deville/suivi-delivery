"""Journal des actions : chaque saisie acceptée est notée (quand, quoi, avant / après)."""

from datetime import UTC, datetime, timedelta

from tests.conftest import a_module, create


def now() -> datetime:
    return datetime.now(UTC)


def audit_log(client, **filters) -> list[dict]:
    response = client.get("/api/audit-log", params=filters)
    assert response.status_code == 200, response.json()
    return response.json()


# --- Ce qui est noté -------------------------------------------------------------


def test_creation_logged(client):
    int = create(client, "environments", code="int", label="Intégration")
    [row] = audit_log(client)
    assert row["action"] == "CREATE"
    assert (row["object"], row["object_id"]) == ("environments", str(int["id"]))
    assert row["before"] is None
    assert row["after"]["code"] == "int"
    assert abs(now() - datetime.fromisoformat(row["date"])) < timedelta(minutes=1)


def test_update_before_after(client):
    int = create(client, "environments", code="int", label="Intégration")
    client.patch(f"/api/environments/{int['id']}", json={"label": "Intégration 2"})
    row = audit_log(client)[0]  # la plus récente d'abord
    assert row["action"] == "UPDATE"
    assert (row["before"]["label"], row["after"]["label"]) == ("Intégration", "Intégration 2")


def test_update_without_change_not_logged(client):
    int = create(client, "environments", code="int", label="Intégration")
    body = {"code": "int", "label": "Intégration"}
    assert client.put(f"/api/environments/{int['id']}", json=body).status_code == 200
    assert len(audit_log(client)) == 1  # la création seulement


def test_deletion_logged(client):
    int = create(client, "environments", code="int", label="Intégration")
    assert client.delete(f"/api/environments/{int['id']}").status_code == 204
    row = audit_log(client)[0]
    assert row["action"] == "DELETE"
    assert row["before"]["code"] == "int"
    assert row["after"] is None


def test_list_and_enumeration_fields_logged(client, deployment):
    rows = audit_log(client, object="parameters", action="CREATE")
    assert {tuple(row["after"]["namespace_ids"]) for row in rows} == {(deployment["namespace"]["id"],)}
    assert {row["after"]["type"] for row in rows} == {"TECHNICAL", "APPLICATION"}


# --- Ce qui n'est pas noté -------------------------------------------------------


def test_rejected_edit_not_logged(client, dataset):
    before = len(audit_log(client))
    assert client.post("/api/environments", json={"code": "int", "label": "Doublon"}).status_code == 409
    assert client.post("/api/environments", json={"code": "x"}).status_code == 422
    assert client.delete("/api/environments/999").status_code == 404
    assert len(audit_log(client)) == before


def test_inconsistent_edit_cancelled_not_logged(client, dataset):
    create(
        client,
        "namespaces",
        application_id=dataset["application"]["id"],
        environment_id=dataset["prod"]["id"],
        cluster_id=dataset["cluster_prod"]["id"],
        suffix="web",
        network_zone_id=dataset["zone"]["id"],
    )
    before = len(audit_log(client))
    assert client.patch(f"/api/clusters/{dataset['cluster_prod']['id']}", json={"is_prod": False}).status_code == 409
    assert len(audit_log(client)) == before


# --- Lecture seule --------------------------------------------------------------


def test_read_only(client):
    assert client.post("/api/audit-log", json={}).status_code == 405
    assert client.delete("/api/audit-log").status_code == 405


# --- Filtres ---------------------------------------------------------------------


def test_filters(client):
    int = create(client, "environments", code="int", label="A")
    create(client, "environments", code="rec", label="T")
    version = {"module_id": a_module(client)["id"], "number": "1.0.0"}
    client.post("/api/module-versions", json=version)
    client.patch(f"/api/environments/{int['id']}", json={"label": "A2"})

    assert len(audit_log(client, object="MODULE_VERSIONS")) == 1
    assert len(audit_log(client, object="environments")) == 3
    assert [row["action"] for row in audit_log(client, object="environments", object_id=str(int["id"]))] == [
        "UPDATE",
        "CREATE",
    ]
    assert len(audit_log(client, action="UPDATE")) == 1
    assert len(audit_log(client, limit=2)) == 2
    assert client.get("/api/audit-log", params={"limit": 0}).status_code == 400
    assert client.get("/api/audit-log", params={"action": "OTHER"}).status_code == 400


def test_filter_by_period(client):
    create(client, "environments", code="int", label="A")
    yesterday, tomorrow = now() - timedelta(days=1), now() + timedelta(days=1)
    assert len(audit_log(client, since=yesterday.isoformat(), until=tomorrow.isoformat())) == 1
    assert audit_log(client, since=tomorrow.isoformat()) == []
    assert audit_log(client, until=yesterday.isoformat()) == []
    # Sans fuseau horaire : UTC.
    assert len(audit_log(client, since=yesterday.replace(tzinfo=None).isoformat())) == 1
