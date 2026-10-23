"""Journal des actions : chaque saisie acceptée est notée (qui, quand, quoi, avant / après)."""

from datetime import UTC, datetime, timedelta

from tests.conftest import a_module, create, token

PASSWORD = "a-strong-password"


def now() -> datetime:
    return datetime.now(UTC)


def create_person(client, identifier: str = "paul", role: str = "EDITOR") -> dict:
    body = {"identifier": identifier, "name": identifier, "kind": "PERSON", "role": role}
    response = client.post("/api/accounts", json={**body, "password": PASSWORD})
    assert response.status_code == 201, response.json()
    return response.json()


def as_(client, identifier: str) -> dict:
    return {"Authorization": f"Bearer {token(client.app, identifier)}"}


def audit_log(client, header: dict | None = None, **filters) -> list[dict]:
    response = client.get("/api/audit-log", params=filters, headers=header or {})
    assert response.status_code == 200, response.json()
    return response.json()


# --- Ce qui est noté -------------------------------------------------------------


def test_creation_logged(client):
    int = create(client, "environments", code="int", label="Intégration")
    [row] = audit_log(client)
    assert row["action"] == "CREATE"
    assert (row["object"], row["object_id"]) == ("environments", str(int["id"]))
    assert (row["author"], row["author_kind"]) == ("admin", "PERSON")
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


# --- Comptes et secrets ----------------------------------------------------------


def test_account_created_without_password(client):
    paul = create_person(client)
    [row] = audit_log(client, object="accounts")
    assert (row["object_id"], row["action"]) == (paul["id"], "CREATE")
    assert row["after"]["identifier"] == "paul"
    assert PASSWORD not in str(row)


def test_temporary_password_logged_without_secret(client):
    paul = create_person(client)
    response = client.patch(f"/api/accounts/{paul['id']}", json={"password": "another-password"})
    assert response.status_code == 200
    row = audit_log(client, object="accounts", action="UPDATE")[0]
    assert row["after"]["password"] == "changé"
    assert "another-password" not in str(row)


def test_new_key_logged_without_key(client):
    response = client.post(
        "/api/accounts", json={"identifier": "tool", "name": "O", "kind": "PROGRAM", "role": "EDITOR"}
    )
    tool = response.json()
    key = client.post(f"/api/accounts/{tool['id']}/key").json()["key"]
    row = audit_log(client, object="accounts", action="UPDATE")[0]
    assert row["after"]["key"] == "changé"
    everything = str(audit_log(client))
    assert key not in everything
    assert tool["key"] not in everything


def test_edit_by_program(client):
    client.post("/api/accounts", json={"identifier": "tool", "name": "O", "kind": "PROGRAM", "role": "EDITOR"})
    version = {"module_id": a_module(client)["id"], "number": "1.0.0"}
    assert client.post("/api/module-versions", json=version, headers=as_(client, "tool")).status_code == 201
    [row] = audit_log(client, object="module_versions")
    assert (row["author"], row["author_kind"]) == ("tool", "PROGRAM")


def test_author_kept_after_account_deletion(client):
    version = {"module_id": a_module(client)["id"], "number": "1.0.0"}
    paul = create_person(client)
    client.post("/api/module-versions", json=version, headers=as_(client, "paul"))
    assert client.delete(f"/api/accounts/{paul['id']}").status_code == 204
    [row] = audit_log(client, object="module_versions")
    assert (row["author_id"], row["author"]) == (paul["id"], "paul")


# --- Qui lit quoi ----------------------------------------------------------------


def test_reserved_to_admin(client):
    create_person(client, "lea", role="VIEWER")
    create_person(client, "paul", role="EDITOR")
    create(client, "clusters", code="cb01", label="Cluster")
    for identifier in ("lea", "paul"):
        assert client.get("/api/audit-log", headers=as_(client, identifier)).status_code == 403
    assert {row["object"] for row in audit_log(client)} == {"accounts", "clusters"}  # l'admin voit tout


def test_read_only(client, anonymous):
    assert client.post("/api/audit-log", json={}).status_code == 405
    assert client.delete("/api/audit-log").status_code == 405
    assert anonymous.get("/api/audit-log").status_code == 401


# --- Filtres ---------------------------------------------------------------------


def test_filters(client):
    create_person(client)
    int = create(client, "environments", code="int", label="A")
    create(client, "environments", code="rec", label="T")
    version = {"module_id": a_module(client)["id"], "number": "1.0.0"}
    client.post("/api/module-versions", json=version, headers=as_(client, "paul"))
    client.patch(f"/api/environments/{int['id']}", json={"label": "A2"})

    assert [row["object"] for row in audit_log(client, author="PAUL")] == ["module_versions"]
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
