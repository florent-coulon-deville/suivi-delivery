"""Point d'entrée de l'API.

Démarrage, depuis backend/ (voir app/__main__.py) :
    uv run python -m app --reload
Swagger (documentation interactive, pour tester les appels) :
    http://localhost:8000/api/docs

Les réglages (base de données, port…) viennent des variables d'environnement :
voir app/settings.py.
"""

import logging
import re
import tomllib
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path

import psycopg
from fastapi import Depends, FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute

from app.access import delivery_rights, require, structure_rights
from app.audit_log import RequestAuthor
from app.configuration import TYPE_XLSX
from app.directory import Directory, KeycloakDirectory
from app.http import HttpMethods, invalid_request
from app.routes import (
    accounts,
    applications,
    clusters,
    compatibilities,
    configuration,
    dependencies,
    documentation,
    enumerations,
    environments,
    health,
    installations,
    me,
    module_versions,
    modules,
    namespaces,
    network_zones,
    parameters,
    slots,
)
from app.routes import (
    audit_log as audit_log_routes,
)
from app.schemas import Role
from app.security import Verifier
from app.settings import DatabaseSettings, SecuritySettings, read_settings
from app.storage import MemoryStorage
from app.storage_postgres import PostgresStorage
from app.transactions import RequestTransaction

logger = logging.getLogger(__name__)

# Version de l'application : lue dans pyproject.toml, la seule source (la même pour le frontend
# et le chart Helm, voir docs/deploiement.md « Version unique »).
VERSION = tomllib.loads((Path(__file__).resolve().parent.parent / "pyproject.toml").read_text())["project"]["version"]

TAGS = [
    {"name": "Environnements", "description": "Liste des environnements (int, rec, preprod, prod…)."},
    {"name": "Clusters", "description": "Liste des clusters OpenShift (cb01, cb02…)."},
    {"name": "Zones réseau", "description": "Liste des zones réseau des namespaces (interne, partenaires…)."},
    {"name": "Applications", "description": "Applications : identifiant unique, trigramme partageable."},
    {"name": "Namespaces", "description": "Namespaces OpenShift d'une application, par environnement."},
    {
        "name": "Modules",
        "description": "Programmes (Python, Java…) d'une application : CAPABILITY (socle) ou BUSINESS_PROJECT.",
    },
    {"name": "Dépendances", "description": "Le module A dépend du module B, y compris entre applications."},
    {"name": "Versions de module", "description": "Versions d'un module : SNAPSHOT (par défaut) ou RELEASE."},
    {"name": "Compatibilités", "description": "Versions des modules requis compatibles avec une version de module."},
    {
        "name": "Paramètres",
        "description": "Paramètres TECHNICAL ou APPLICATION d'un module (nom libre, ex. une version), "
        "affectés à des namespaces.",
    },
    {
        "name": "Emplacements",
        "description": "Emplacements (slots) d'un namespace, réservés à un module, nommés par leur release Helm.",
    },
    {
        "name": "Installations",
        "description": "Historique : quelle version, avec quels paramètres, sur quel emplacement.",
    },
    {
        "name": "Configuration",
        "description": "Toute la configuration dans un fichier Excel, objets désignés par leurs codes "
        "(export, import).",
    },
    {"name": "Énumérations", "description": "Valeurs possibles des listes fermées (types de module, de version…)."},
    {
        "name": "Journal",
        "description": "Qui a créé, modifié ou supprimé quoi, et quand (lecture seule).",
    },
    {"name": "Mon compte", "description": "Le compte connecté (d'après son jeton) et ses préférences."},
    {
        "name": "Comptes",
        "description": "Gérer les comptes, gardés par Keycloak : personnes et programmes, et leur rôle (ADMIN).",
    },
    {"name": "Santé", "description": "Probes Kubernetes (hors de /api, sans jeton) : /startupz, /readyz, /livez."},
]


def _log_startup(app: FastAPI, base: DatabaseSettings | None) -> None:
    """Dit dans les journaux, au démarrage, ce qui manque (base, Keycloak, clé de son client)."""
    if base is None:
        logger.warning("Pas de base (APP_DB_HOST absente) : données EN MÉMOIRE, perdues à l'arrêt de l'API")
    if app.state.verifier is None:
        logger.warning("Pas de Keycloak (APP_KEYCLOAK_URL absente) : aucun jeton ne sera accepté")
    else:
        logger.info("Jetons acceptés de %s", app.state.verifier.issuer)
    if app.state.directory is None:
        logger.warning("Pas de clé du client Keycloak (APP_KEYCLOAK_CLIENT_SECRET) : écran Comptes indisponible")


def create_application(
    base: DatabaseSettings | None = None,
    docs: bool = True,
    security: SecuritySettings | None = None,
    verifier: Verifier | None = None,
    directory: Directory | None = None,
) -> FastAPI:
    """Crée l'application.

    Sans base : stockage vide, en mémoire, perdu à l'arrêt. Les tests appellent create_application()
    pour repartir d'une application neuve à chaque test.
    Avec une base : les données sont dans PostgreSQL (app/storage_postgres.py), dont la structure
    a été créée par Liquibase avant le démarrage.
    docs=False masque la documentation Swagger (/api/docs et /api/openapi.json).
    securite : la connexion par Keycloak (app/settings.py). Par défaut, le vérificateur des jetons
    et l'annuaire des comptes en sont tirés ; les tests donnent les leurs (verificateur, annuaire).
    """
    security = security or SecuritySettings()
    if verifier is None:
        verifier = Verifier.from_settings(security)
    if directory is None and security.keycloak_url and security.client_secret:
        directory = KeycloakDirectory(security.keycloak_url, security.realm, security.client_secret)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
        # Exécuté au démarrage de l'API (avant « yield ») et à son arrêt (après).
        # La base n'est contactée qu'ici : importer ce module (dans les tests) ne s'y connecte pas.
        if base is not None:
            storage = PostgresStorage(base)
            storage.open()
            app.state.storage = storage
        _log_startup(app, base)
        app.state.started = True  # probes /startupz et /readyz (routes/health.py)
        yield
        app.state.storage.close()

    app = FastAPI(
        lifespan=lifespan,
        title="Suivi de la delivery",
        version=VERSION,
        openapi_tags=TAGS,
        # Swagger et la description OpenAPI sont servis par routes/documentation.py (retouchés pour Bruno).
        docs_url=None,
        openapi_url=None,
        redoc_url=None,
    )
    app.state.storage = MemoryStorage()  # remplacé au démarrage par la base, s'il y en a une
    app.state.security = security  # réglages de la connexion (adresses de Keycloak)
    app.state.verifier = verifier  # vérifie les jetons d'accès (app/security.py) ; None sans Keycloak
    app.state.directory = directory  # les comptes, dans Keycloak (app/directory.py) ; None sans sa clé
    app.state.docs = docs  # Swagger servi ou non (routes/documentation.py)
    app.state.started = False  # passe à True à la fin du démarrage (lifespan)

    # Données métier : chaque appel doit porter un jeton ; lire demande VIEWER (app/access.py).
    # Structure (paramétrage général) : la modifier demande ADMIN.
    structure_routers = [
        module.router
        for module in (
            environments,
            clusters,
            network_zones,
            applications,
            namespaces,
            modules,
            dependencies,
            compatibilities,
            slots,
        )
    ]
    # Livraisons (saisies par les développeurs) : les modifier demande EDITOR.
    delivery_routers = [
        module.router
        for module in (
            module_versions,
            parameters,
            installations,
            enumerations,  # listes fermées, pour l'interface (lecture seule)
        )
    ]
    for router in structure_routers:
        app.include_router(router, prefix="/api", dependencies=[Depends(structure_rights)])
    for router in delivery_routers:
        app.include_router(router, prefix="/api", dependencies=[Depends(delivery_rights)])
    # Toute la configuration en un fichier : l'exporter demande VIEWER, l'importer ADMIN.
    app.include_router(configuration.router, prefix="/api", dependencies=[Depends(structure_rights)])
    app.include_router(accounts.router, prefix="/api", dependencies=[Depends(require(Role.ADMIN))])
    app.include_router(audit_log_routes.router, prefix="/api", dependencies=[Depends(require(Role.ADMIN))])
    app.include_router(me.router, prefix="/api")  # toute personne ou programme connecté (vérifié dans me.py)
    app.include_router(health.router)  # probes Kubernetes, hors de /api, sans jeton
    if docs:
        app.include_router(documentation.router)  # Swagger : /api/docs, /api/openapi.json
    routers = [
        *structure_routers,
        *delivery_routers,
        configuration.router,
        accounts.router,
        audit_log_routes.router,
        me.router,
    ]

    # Règles HTTP communes (voir app/http.py) : HEAD, OPTIONS, en-tête Allow, 415, et 400 / 404 / 422.
    routes = [
        (re.compile("^" + prefix + route.path_regex.pattern.lstrip("^")), route.methods or set())
        for router, prefix in [(router, "/api") for router in routers] + [(health.router, "")]
        for route in router.routes
        if isinstance(route, APIRoute)
    ]
    # L'auteur de chaque requête, pour le journal des actions (app/audit_log.py).
    app.add_middleware(RequestAuthor)
    # Une transaction par requête (base PostgreSQL), voir app/transactions.py.
    app.add_middleware(RequestTransaction)
    # Seule exception au JSON : l'import de la configuration reçoit le fichier Excel de l'export.
    files = {"/api/configuration": (TYPE_XLSX, "un fichier Excel")}
    app.add_middleware(HttpMethods, routes=routes, files=files)
    app.add_exception_handler(RequestValidationError, invalid_request)
    app.add_exception_handler(psycopg.errors.IntegrityError, database_rejection)
    return app


def database_rejection(request: Request, error: Exception) -> JSONResponse:
    """Filet de sécurité : une saisie que l'API aurait laissée passer, mais que les contrôles de la
    base refusent (unicité, lien, valeur interdite) donne 409 et non une erreur 500."""
    assert isinstance(error, psycopg.errors.IntegrityError)
    detail = error.diag.message_primary or str(error)
    logger.warning("Saisie refusée par la base : %s", detail)
    return JSONResponse({"detail": f"Saisie refusée par la base de données : {detail}"}, status.HTTP_409_CONFLICT)


# L'application lancée par le serveur, avec les réglages de l'environnement (app/settings.py).
settings = read_settings()
app = create_application(settings.base, docs=settings.docs, security=settings.security)
