"""Tests des compatibilités entre versions, et du refus des saisies incompatibles.

Scénario : en intégration, le batch de paie (application paiement) dépend de
l'authentification (application socle). Les deux tournent dans des namespaces différents.
"""

import pytest

from app.schemas import ConditionType
from app.versions import key, satisfied
from tests.conftest import create

# --- Comparaison de versions ------------------------------------------------


@pytest.mark.parametrize(
    "small, large",
    [
        ("1.4", "1.10"),
        ("1.9.9", "2.0"),
        ("2.3.0-SNAPSHOT", "2.3.0"),
        ("1", "1.0.1"),
    ],
)
def test_version_order(small, large):
    assert key(small) < key(large)


def test_trailing_zeros_ignored():
    assert key("1.4") == key("1.4.0")


@pytest.mark.parametrize(
    "number, condition, version, version_max, expected",
    [
        ("1.4", ConditionType.EXACT, "1.4.0", None, True),
        ("1.5", ConditionType.EXACT, "1.4", None, False),
        ("2.0", ConditionType.AT_LEAST, "1.4", None, True),
        ("1.2", ConditionType.AT_LEAST, "1.4", None, False),
        ("2.0", ConditionType.BETWEEN, "1.4", "2.0", True),  # bornes comprises
        ("2.1", ConditionType.BETWEEN, "1.4", "2.0", False),
    ],
)
def test_conditions(number, condition, version, version_max, expected):
    assert satisfied(number, condition, version, version_max) is expected


# --- Scénario ---------------------------------------------------------------


@pytest.fixture
def s(client, dataset) -> dict:
    """Batch de paie (paiement) et authentification (socle), chacun avec son namespace en intégration."""
    base = create(client, "applications", identifier="socle", name="Socle", trigram="soc")
    d = {"int": dataset["int"], "prod": dataset["prod"], "cluster_prod": dataset["cluster_prod"]}
    d["batch"] = create(
        client,
        "modules",
        application_id=dataset["application"]["id"],
        code="batch",
        name="Batch de paie",
        type="BUSINESS_PROJECT",
    )
    d["auth"] = create(
        client, "modules", application_id=base["id"], code="auth", name="Authentification", type="CAPABILITY"
    )
    for name, application, module in (("paie", dataset["application"], d["batch"]), ("socle", base, d["auth"])):
        namespace = create(
            client,
            "namespaces",
            application_id=application["id"],
            environment_id=dataset["int"]["id"],
            cluster_id=dataset["cluster"]["id"],
            suffix="app",
            network_zone_id=dataset["zone"]["id"],
        )
        technical_parameter = create(
            client,
            "parameters",
            module_id=module["id"],
            name="tech",
            type="TECHNICAL",
            namespace_ids=[namespace["id"]],
        )
        application_parameter = create(
            client,
            "parameters",
            module_id=module["id"],
            name="appli",
            type="APPLICATION",
            namespace_ids=[namespace["id"]],
        )
        d[name] = {
            "namespace": namespace,
            "slot": create(client, "slots", namespace_id=namespace["id"], module_id=module["id"], release_name=name),
            "technical_parameter": technical_parameter,
            "application_parameter": application_parameter,
        }
    d["dependency"] = create(client, "dependencies", module_id=d["batch"]["id"], depends_on_id=d["auth"]["id"])
    for number in ("1.2", "1.4", "2.1"):
        d[f"auth {number}"] = create(
            client, "module-versions", module_id=d["auth"]["id"], number=number, type="RELEASE"
        )
    d["batch 2.3"] = create(client, "module-versions", module_id=d["batch"]["id"], number="2.3", type="RELEASE")
    return d


def install(client, s, or_: str, version: str, date: str):
    """POST d'une installation de « version » sur l'emplacement de « ou » (paie ou socle) ; renvoie la réponse."""
    target = s[or_]
    return client.post(
        "/api/installations",
        json={
            "slot_id": target["slot"]["id"],
            "module_version_id": s[version]["id"],
            "technical_parameter_id": target["technical_parameter"]["id"],
            "application_parameter_id": target["application_parameter"]["id"],
            "date": date,
        },
    )


def require(client, s, condition: str, version: str, version_max: str | None = None):
    """POST « le batch 2.3 a besoin de auth <condition> » ; renvoie la réponse."""
    return client.post(
        "/api/compatibilities",
        json={
            "module_version_id": s["batch 2.3"]["id"],
            "required_module_id": s["auth"]["id"],
            "condition": condition,
            "version": version,
            "version_max": version_max,
        },
    )


# --- Saisie des compatibilités ----------------------------------------------


def test_create_201(client, s):
    response = require(client, s, "AT_LEAST", "1.4")
    assert response.status_code == 201
    assert response.headers["Location"] == f"/api/compatibilities/{response.json()['id']}"
    needs = client.get("/api/compatibilities", params={"module_version_id": s["batch 2.3"]["id"]}).json()
    assert [(b["condition"], b["version"]) for b in needs] == [("AT_LEAST", "1.4")]


def test_undeclared_dependency_422(client, s):
    client.delete(f"/api/dependencies/{s['dependency']['id']}")
    assert require(client, s, "AT_LEAST", "1.4").status_code == 422


@pytest.mark.parametrize(
    "condition, version, version_max",
    [
        ("BETWEEN", "1.4", None),  # borne haute manquante
        ("BETWEEN", "2.0", "1.4"),  # bornes inversées
        ("EXACT", "1.4", "2.0"),  # borne haute inutile
        ("AT_LEAST", "v1.4", None),  # numéro mal formé
        ("PLUS_OR_MINUS", "1.4", None),  # condition inconnue
    ],
)
def test_invalid_condition_422(client, s, condition, version, version_max):
    assert require(client, s, condition, version, version_max).status_code == 422


def test_single_compatibility_per_required_module_409(client, s):
    require(client, s, "AT_LEAST", "1.4")
    assert require(client, s, "EXACT", "2.1").status_code == 409


def test_update_condition(client, s):
    compatibility = require(client, s, "AT_LEAST", "1.4").json()
    url = f"/api/compatibilities/{compatibility['id']}"
    response = client.patch(url, json={"condition": "BETWEEN", "version_max": "2.0"})
    assert response.status_code == 200
    assert (response.json()["condition"], response.json()["version_max"]) == ("BETWEEN", "2.0")
    assert client.patch(url, json={"condition": "EXACT"}).status_code == 422  # version_max encore là
    assert client.patch("/api/compatibilities/999", json={"version": "1"}).status_code == 404


def test_deletions_blocked_by_a_compatibility_409(client, s):
    require(client, s, "AT_LEAST", "1.4")
    assert client.delete(f"/api/dependencies/{s['dependency']['id']}").status_code == 409
    assert client.delete(f"/api/module-versions/{s['batch 2.3']['id']}").status_code == 409


# --- Refus des installations incompatibles ----------------------------------


def test_installation_compatible_201(client, s):
    require(client, s, "AT_LEAST", "1.4")
    assert install(client, s, "socle", "auth 1.4", "2026-10-01T10:00:00Z").status_code == 201
    assert install(client, s, "paie", "batch 2.3", "2026-10-02T10:00:00Z").status_code == 201


def test_required_module_missing_409(client, s):
    require(client, s, "AT_LEAST", "1.4")
    response = install(client, s, "paie", "batch 2.3", "2026-10-02T10:00:00Z")
    assert response.status_code == 409
    assert "auth en 1.4 ou plus, qui n'est pas installé en int" in response.json()["detail"]


def test_required_module_too_old_409(client, s):
    require(client, s, "AT_LEAST", "1.4")
    install(client, s, "socle", "auth 1.2", "2026-10-01T10:00:00Z")
    response = install(client, s, "paie", "batch 2.3", "2026-10-02T10:00:00Z")
    assert response.status_code == 409
    assert "mais auth 1.2 tourne en int" in response.json()["detail"]


def test_upgrade_of_required_module_breaking_a_user_409(client, s):
    require(client, s, "BETWEEN", "1.4", "2.0")
    install(client, s, "socle", "auth 1.4", "2026-10-01T10:00:00Z")
    install(client, s, "paie", "batch 2.3", "2026-10-02T10:00:00Z")
    # passer l'authentification en 2.1 casserait le batch 2.3 (besoin : entre 1.4 et 2.0)
    assert install(client, s, "socle", "auth 2.1", "2026-10-03T10:00:00Z").status_code == 409


def test_no_check_between_environments(client, s):
    # En prod, rien n'est installé : ce qui tourne en int ne compte pas pour la prod, et inversement.
    require(client, s, "AT_LEAST", "1.4")
    install(client, s, "socle", "auth 1.4", "2026-10-01T10:00:00Z")
    to_prod = {"environment_id": s["prod"]["id"], "cluster_id": s["cluster_prod"]["id"]}
    assert client.patch(f"/api/namespaces/{s['socle']['namespace']['id']}", json=to_prod).status_code == 200
    assert install(client, s, "paie", "batch 2.3", "2026-10-02T10:00:00Z").status_code == 409


def test_move_required_module_to_another_environment_409(client, s):
    require(client, s, "AT_LEAST", "1.4")
    install(client, s, "socle", "auth 1.4", "2026-10-01T10:00:00Z")
    install(client, s, "paie", "batch 2.3", "2026-10-02T10:00:00Z")
    response = client.patch(
        f"/api/namespaces/{s['socle']['namespace']['id']}",
        json={"environment_id": s["prod"]["id"], "cluster_id": s["cluster_prod"]["id"]},
    )
    assert response.status_code == 409


def test_delete_installation_that_would_make_incompatible_409(client, s):
    require(client, s, "AT_LEAST", "1.4")
    install(client, s, "socle", "auth 1.2", "2026-09-01T10:00:00Z")
    new = install(client, s, "socle", "auth 1.4", "2026-10-01T10:00:00Z").json()
    install(client, s, "paie", "batch 2.3", "2026-10-02T10:00:00Z")
    # supprimer la 1.4 ferait revenir l'authentification en 1.2 : incompatible
    assert client.delete(f"/api/installations/{new['id']}").status_code == 409


def test_new_compatibility_contradicted_by_existing_409(client, s):
    install(client, s, "socle", "auth 1.2", "2026-10-01T10:00:00Z")
    install(client, s, "paie", "batch 2.3", "2026-10-02T10:00:00Z")
    # le batch 2.3 tourne déjà avec auth 1.2 : déclarer « 1.4 ou plus » contredirait la réalité saisie
    assert require(client, s, "AT_LEAST", "1.4").status_code == 409
    assert require(client, s, "BETWEEN", "1.0", "1.3").status_code == 201


def test_change_number_of_an_installed_version_409(client, s):
    require(client, s, "AT_LEAST", "1.4")
    install(client, s, "socle", "auth 1.4", "2026-10-01T10:00:00Z")
    install(client, s, "paie", "batch 2.3", "2026-10-02T10:00:00Z")
    response = client.patch(f"/api/module-versions/{s['auth 1.4']['id']}", json={"number": "1.3"})
    assert response.status_code == 409
