"""Outils partagés par tous les tests (pytest charge ce fichier automatiquement).

Deux façons de lancer les tests, depuis backend/ :
    uv run pytest                                   données en mémoire (rapide) ;
    TESTS_DB_FILE=/tmp/suivi-tests.sqlite uv run pytest
                                                    les MÊMES tests sur une vraie base SQLite, dans ce
                                                    fichier. La CI fait les deux.

Avec une base, son fichier est EFFACÉ avant chaque test : il doit finir par « _tests.sqlite »,
pour ne jamais effacer une base qui sert. Variable TESTS_DB_FILE (et non APP_DB_FILE) : lancer
les tests dans un terminal réglé pour l'API ne touche pas à sa base.
"""

import os
from collections.abc import Generator, Iterator
from contextlib import contextmanager

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.main import create_application
from app.settings import DatabaseSettings, read_database
from app.storage import MemoryStorage, Storage
from app.storage_sqlite import SqliteStorage

# La base des tests, si TESTS_DB_FILE est renseignée ; None : tests en mémoire.
BASE: DatabaseSettings | None = read_database(os.environ, prefix="TESTS_DB_")
if BASE is not None and not BASE.file.name.endswith("_tests.sqlite"):
    pytest.exit(f"TESTS_DB_FILE={BASE.file} : le nom doit finir par « _tests.sqlite » (il est effacé)", returncode=2)

# Pour les tests qui n'ont de sens qu'avec une vraie base (données relues après un redémarrage…).
with_sqlite = pytest.mark.skipif(BASE is None, reason="sans base de tests (TESTS_DB_FILE absente)")


def clear_database() -> None:
    """Efface la base des tests (son fichier et ceux de son journal d'écriture) : elle repart de zéro."""
    assert BASE is not None
    for suffix in ("", "-wal", "-shm"):
        BASE.file.with_name(BASE.file.name + suffix).unlink(missing_ok=True)


def application(docs: bool = True, clear: bool = True) -> FastAPI:
    """Une application de test, sur des données vides : en mémoire, ou dans la base des tests.
    clear=False : garde ce qui est dans la base (pour simuler un redémarrage de l'API)."""
    if BASE is not None and clear:
        clear_database()
    return create_application(BASE, docs=docs)


@contextmanager
def new_storage() -> Generator[Storage]:
    """Un stockage vide, hors de l'API (en mémoire, ou la base des tests effacée)."""
    if BASE is None:
        yield MemoryStorage()
        return
    clear_database()
    storage = SqliteStorage(BASE)
    storage.open()
    try:
        yield storage
    finally:
        storage.close()


@contextmanager
def started(app: FastAPI) -> Generator[TestClient]:
    """Démarre l'application et renvoie un client HTTP de test."""
    with TestClient(app) as client:
        yield client


@pytest.fixture
def client() -> Iterator[TestClient]:
    """Un client HTTP de test, sur une application neuve (stockage vide)."""
    with started(application()) as client:
        yield client


def create(client: TestClient, resource: str, **fields) -> dict:
    """POST /api/<ressource> qui doit réussir (201) ; renvoie l'élément créé."""
    response = client.post(f"/api/{resource}", json=fields)
    assert response.status_code == 201, response.json()
    return response.json()


def a_module(client: TestClient) -> dict:
    """Une application et son module : de quoi saisir une version."""
    application = create(client, "applications", identifier="paiement", name="Paiement", trigram="abc")
    module = {"code": "batch-paie", "name": "Batch de paie", "type": "BUSINESS_PROJECT"}
    return create(client, "modules", application_id=application["id"], **module)


@pytest.fixture
def dataset(client) -> dict:
    """Un petit jeu de données : 1 application, 2 environnements (int, prod), 2 clusters (hors prod, prod),
    2 zones réseau."""
    return {
        "application": create(client, "applications", identifier="paiement", name="Paiement", trigram="abc"),
        "int": create(client, "environments", code="int", label="Intégration"),
        "prod": create(client, "environments", code="PROD", label="Production", is_prod=True),
        "cluster": create(client, "clusters", code="cb01", label="Cluster hors prod"),
        "cluster_prod": create(client, "clusters", code="cb02", label="Cluster prod", is_prod=True),
        "zone": create(client, "network-zones", code="INTERNE", label="INTERNE"),
        "zone_partenaires": create(client, "network-zones", code="partenaires", label="PARTENAIRES"),
    }


@pytest.fixture
def deployment(client, dataset) -> dict:
    """Tout ce qu'il faut pour enregistrer une installation, en plus du jeu de base :
    un namespace, un module et sa version, un paramètre technique et un applicatif du module
    (affectés au namespace) avec chacun une version, et un emplacement.
    """
    application_id = dataset["application"]["id"]
    namespace = create(
        client,
        "namespaces",
        application_id=application_id,
        environment_id=dataset["int"]["id"],
        cluster_id=dataset["cluster"]["id"],
        suffix="batch",
        network_zone_id=dataset["zone"]["id"],
    )
    module = create(
        client,
        "modules",
        application_id=application_id,
        code="batch-paie",
        name="Batch de paie",
        type="BUSINESS_PROJECT",
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
    return {
        **dataset,
        "namespace": namespace,
        "module": module,
        "module_version": create(client, "module-versions", module_id=module["id"], number="2.3.0", type="RELEASE"),
        "technical_parameter": technical_parameter,
        "application_parameter": application_parameter,
        "slot": create(
            client, "slots", namespace_id=namespace["id"], module_id=module["id"], release_name="batch-paie"
        ),
    }


def installation_body(d: dict, **others) -> dict:
    """Corps de création d'une installation valide à partir de la fixture deploiement."""
    return {
        "slot_id": d["slot"]["id"],
        "module_version_id": d["module_version"]["id"],
        "technical_parameter_id": d["technical_parameter"]["id"],
        "application_parameter_id": d["application_parameter"]["id"],
        **others,
    }
