"""Outils partagés par tous les tests (pytest charge ce fichier automatiquement).

Deux façons de lancer les tests, depuis backend/ :
    uv run pytest                 données en mémoire (rapide, sans rien installer) ;
    TESTS_DB_HOST=localhost TESTS_DB_PORT=5432 TESTS_DB_NAME=suivi_delivery_tests \
    TESTS_DB_PASSWORD=... uv run pytest
                                  les MÊMES tests sur une vraie base PostgreSQL, dont la structure a
                                  été créée par Liquibase (voir docs/postgresql.md). La CI fait les deux.

Keycloak n'est pas lancé : les jetons sont fabriqués par les tests (voir SECURITY ci-dessous), et
les comptes sont dans un annuaire en mémoire (app/directory.py, MemoryDirectory).

Avec une base, elle est VIDÉE avant chaque test : son nom doit finir par « _tests », pour ne
jamais effacer une base qui sert. Variables TESTS_DB_* (et non APP_DB_*) : lancer les tests
dans un terminal réglé pour l'API ne touche pas à sa base.
"""

import os
import time
from collections.abc import Generator, Iterator
from contextlib import contextmanager

import jwt
import psycopg
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from psycopg import sql

from app.directory import MemoryDirectory
from app.main import create_application
from app.schemas import AccountKind, Role
from app.security import AUDIENCE, Verifier
from app.settings import DatabaseSettings, SecuritySettings, read_database
from app.storage import TABLE_NAMES, MemoryStorage, Storage
from app.storage_postgres import PostgresStorage
from tests.keys_for_tests import PRIVATE_KEY

# Connexion des tests : pas de vrai Keycloak. Les tests fabriquent eux-mêmes des jetons comme ceux de
# Keycloak (même contenu), signés avec une clé RSA tirée au hasard au lancement ; l'API les vérifie
# avec la clé publique correspondante, exactement comme elle vérifie ceux de Keycloak.
SECURITY = SecuritySettings(frontend_url="http://frontend.test")
ISSUER = SECURITY.issuer
ADMIN_PASSWORD = "tests-password"

# La base des tests, si TESTS_DB_HOST est renseignée ; None : tests en mémoire.
BASE: DatabaseSettings | None = read_database(os.environ, prefix="TESTS_DB_")
if BASE is not None and not BASE.name.endswith("_tests"):
    pytest.exit(f"TESTS_DB_NAME={BASE.name} : le nom doit finir par « _tests » (la base est vidée)", returncode=2)

# Pour les tests qui n'ont de sens qu'avec une vraie base (données relues après un redémarrage…).
with_postgres = pytest.mark.skipif(BASE is None, reason="sans base de tests (TESTS_DB_HOST absente)")


def clear_database() -> None:
    """Efface toutes les données de la base des tests, et remet les numéros d'identifiant à 1."""
    assert BASE is not None
    tables = sql.SQL(", ").join(map(sql.Identifier, [*TABLE_NAMES, "parameter_namespaces"]))
    with psycopg.connect(**BASE.connection()) as connection:  # « with » : enregistré à la fin du bloc
        connection.execute(sql.SQL("truncate {} restart identity cascade").format(tables))


def verifier() -> Verifier:
    """Vérifie les jetons des tests : la clé publique des tests, à la place de celles de Keycloak."""
    return Verifier(ISSUER, fixed_key=PRIVATE_KEY.public_key())


def test_directory() -> MemoryDirectory:
    """Un annuaire en mémoire (à la place de Keycloak), avec le compte admin, comme à l'import de Keycloak."""
    directory = MemoryDirectory()
    directory.create_person("admin", "Administrateur", Role.ADMIN, ADMIN_PASSWORD)
    return directory


def application(docs: bool = True, security: SecuritySettings = SECURITY, clear: bool = True) -> FastAPI:
    """Une application de test, sur des données vides : en mémoire, ou dans la base des tests.
    clear=False : garde ce qui est dans la base (pour simuler un redémarrage de l'API)."""
    if BASE is not None and clear:
        clear_database()
    return create_application(BASE, docs=docs, security=security, verifier=verifier(), directory=test_directory())


@contextmanager
def new_storage() -> Generator[Storage]:
    """Un stockage vide, hors de l'API (en mémoire, ou la base des tests vidée)."""
    if BASE is None:
        yield MemoryStorage()
        return
    clear_database()
    storage = PostgresStorage(BASE)
    storage.open()
    try:
        yield storage
    finally:
        storage.close()


def sign(content: dict, key=PRIVATE_KEY) -> str:
    """Un jeton signé comme ceux de Keycloak (RS256), avec la clé des tests (ou une autre)."""
    return jwt.encode(content, key, algorithm="RS256", headers={"kid": "test-keys"})


def token_content(
    identifier: str,
    role: Role | None,
    kind: AccountKind = AccountKind.PERSON,
    subject: str = "tests-subject",
    name: str | None = None,
    duration: int = 300,
) -> dict:
    """Le contenu d'un jeton d'accès de Keycloak pour cette personne (ou ce programme)."""
    now = int(time.time())
    content = {
        "iss": ISSUER,
        "aud": [AUDIENCE, "account"],
        "sub": subject,
        "typ": "Bearer",
        "iat": now,
        "exp": now + duration,
        "realm_access": {"roles": ["default-roles-suivi-delivery", "offline_access", *([role] if role else [])]},
    }
    if kind == AccountKind.PROGRAM:
        return {
            **content,
            "azp": identifier,
            "client_id": identifier,
            "preferred_username": f"service-account-{identifier}",
        }
    return {**content, "azp": "suivi-delivery-frontend", "preferred_username": identifier, "name": name or identifier}


def token(app: FastAPI, identifier: str = "admin") -> str:
    """Un jeton d'accès valide pour ce compte de l'annuaire des tests (rôle, sorte et nom du compte)."""
    account = next((c for c in app.state.directory.list_all() if c["identifier"] == identifier), None)
    assert account is not None, identifier
    return sign(token_content(identifier, account["role"], account["kind"], account["id"], account["name"]))


@contextmanager
def connected(app: FastAPI, identifier: str | None = "admin") -> Generator[TestClient]:
    """Démarre l'application et renvoie un client connecté avec ce compte ;
    identifiant None : client anonyme, sans jeton."""
    with TestClient(app) as client:
        if identifier is not None:
            client.headers["Authorization"] = f"Bearer {token(app, identifier)}"
        yield client


@pytest.fixture
def client() -> Iterator[TestClient]:
    """Un client HTTP de test, connecté en administrateur, sur une application neuve (stockage vide)."""
    with connected(application()) as client:
        yield client


@pytest.fixture
def anonymous(client: TestClient) -> TestClient:
    """Un client SANS jeton, sur la même application que « client »."""
    return TestClient(client.app)


def create(client: TestClient, resource: str, **fields) -> dict:
    """POST /api/<ressource> qui doit réussir (201) ; renvoie l'élément créé."""
    response = client.post(f"/api/{resource}", json=fields)
    assert response.status_code == 201, response.json()
    return response.json()


def a_module(client: TestClient) -> dict:
    """Une application et son module, créés par l'admin (structure) : de quoi saisir une version."""
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
