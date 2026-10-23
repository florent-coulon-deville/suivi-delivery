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
import sqlite3
import tomllib
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute

from app.configuration import TYPE_XLSX
from app.http import HttpMethods, invalid_request
from app.routes import (
    applications,
    clusters,
    compatibilities,
    configuration,
    dependencies,
    enumerations,
    environments,
    health,
    installations,
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
from app.settings import DatabaseSettings, read_settings
from app.storage import MemoryStorage
from app.storage_sqlite import SqliteStorage
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
        "description": "Quoi a été créé, modifié ou supprimé, et quand (lecture seule).",
    },
    {"name": "Santé", "description": "Probes Kubernetes (hors de /api) : /startupz, /readyz, /livez."},
]


def create_application(base: DatabaseSettings | None = None, docs: bool = True) -> FastAPI:
    """Crée l'application.

    Sans base : stockage vide, en mémoire, perdu à l'arrêt. Les tests appellent create_application()
    pour repartir d'une application neuve à chaque test.
    Avec une base : les données sont dans un fichier SQLite (app/storage_sqlite.py), dont l'API crée
    ou complète elle-même la structure au démarrage.
    docs=False masque la documentation Swagger (/api/docs et /api/openapi.json).

    Pas de connexion ni de rôles : tout le monde peut tout lire et tout saisir. À réserver à un
    réseau de confiance (voir docs/architecture.md).
    """

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
        # Exécuté au démarrage de l'API (avant « yield ») et à son arrêt (après).
        # La base n'est ouverte qu'ici : importer ce module (dans les tests) n'y touche pas.
        if base is None:
            logger.warning("Pas de base (APP_DB_FILE absente) : données EN MÉMOIRE, perdues à l'arrêt de l'API")
        else:
            storage = SqliteStorage(base)
            storage.open()
            app.state.storage = storage
        app.state.started = True  # probes /startupz et /readyz (routes/health.py)
        yield
        app.state.storage.close()

    app = FastAPI(
        lifespan=lifespan,
        title="Suivi de la delivery",
        version=VERSION,
        openapi_tags=TAGS,
        docs_url="/api/docs" if docs else None,
        openapi_url="/api/openapi.json" if docs else None,
        redoc_url=None,
    )
    app.state.storage = MemoryStorage()  # remplacé au démarrage par la base, s'il y en a une
    app.state.started = False  # passe à True à la fin du démarrage (lifespan)

    routers = [
        module.router
        for module in (
            environments,
            clusters,
            network_zones,
            applications,
            namespaces,
            modules,
            dependencies,
            module_versions,
            compatibilities,
            parameters,
            slots,
            installations,
            enumerations,  # listes fermées, pour l'interface (lecture seule)
            configuration,  # toute la configuration en un fichier Excel (export, import)
            audit_log_routes,
        )
    ]
    for router in routers:
        app.include_router(router, prefix="/api")
    app.include_router(health.router)  # probes Kubernetes, hors de /api

    # Règles HTTP communes (voir app/http.py) : HEAD, OPTIONS, en-tête Allow, 415, et 400 / 404 / 422.
    routes = [
        (re.compile("^" + prefix + route.path_regex.pattern.lstrip("^")), route.methods or set())
        for router, prefix in [(router, "/api") for router in routers] + [(health.router, "")]
        for route in router.routes
        if isinstance(route, APIRoute)
    ]
    # Une transaction par requête (base SQLite), voir app/transactions.py.
    app.add_middleware(RequestTransaction)
    # Seule exception au JSON : l'import de la configuration reçoit le fichier Excel de l'export.
    files = {"/api/configuration": (TYPE_XLSX, "un fichier Excel")}
    app.add_middleware(HttpMethods, routes=routes, files=files)
    app.add_exception_handler(RequestValidationError, invalid_request)
    app.add_exception_handler(sqlite3.IntegrityError, database_rejection)
    return app


def database_rejection(request: Request, error: Exception) -> JSONResponse:
    """Filet de sécurité : une saisie que l'API aurait laissée passer, mais que les contrôles de la
    base refusent (unicité, lien, valeur interdite) donne 409 et non une erreur 500."""
    assert isinstance(error, sqlite3.IntegrityError)
    detail = str(error)
    logger.warning("Saisie refusée par la base : %s", detail)
    return JSONResponse({"detail": f"Saisie refusée par la base de données : {detail}"}, status.HTTP_409_CONFLICT)


# L'application lancée par le serveur, avec les réglages de l'environnement (app/settings.py).
settings = read_settings()
app = create_application(settings.base, docs=settings.docs)
