"""Réglages de l'API, lus dans les variables d'environnement au démarrage.

Une seule version de l'application, qui marche partout : ce qui change d'une
installation à l'autre (emplacement des données, port…) se règle au lancement,
sans rien modifier dans le code. Sans variable, les valeurs par défaut sont
celles du développement sur un poste.

    Variable                  Rôle                                         Défaut
    APP_HOST                  adresse d'écoute (0.0.0.0 dans un conteneur) 127.0.0.1 (ce poste seulement)
    APP_PORT                  port d'écoute                                8000
    APP_LOG_LEVEL             détail des journaux : critical, error,       info
                              warning, info, debug, trace
    APP_DOCS                  Swagger visible (/api/docs) : oui ou non     oui

  Base SQLite (voir app/storage_sqlite.py) :
    APP_DB_FILE               fichier de la base SQLite (créé s'il         aucun : données EN MÉMOIRE,
                              n'existe pas, avec ses tables)               perdues à l'arrêt (essais)

Une valeur invalide arrête le démarrage avec un message clair (InvalidSetting) :
mieux vaut ne pas démarrer que démarrer avec un réglage faux.
"""

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

LOG_LEVELS = ("critical", "error", "warning", "info", "debug", "trace")
YES = ("oui", "true", "1", "yes", "o", "y")
NO = ("non", "false", "0", "no", "n")


class InvalidSetting(ValueError):
    """Une variable d'environnement a une valeur impossible."""


@dataclass(frozen=True)
class DatabaseSettings:
    """La base SQLite : un seul fichier."""

    file: Path


@dataclass(frozen=True)
class Settings:
    base: DatabaseSettings | None = None  # None : données en mémoire, perdues à l'arrêt
    host: str = "127.0.0.1"
    port: int = 8000
    log_level: str = "info"
    docs: bool = True


def read_settings(variables: Mapping[str, str] = os.environ) -> Settings:
    """Lit les réglages ; une variable absente ou vide garde sa valeur par défaut."""
    default = Settings()

    def value(name: str) -> str | None:
        text = variables.get(name, "").strip()
        return text or None

    host = value("APP_HOST")
    port = value("APP_PORT")
    level = value("APP_LOG_LEVEL")
    docs = value("APP_DOCS")

    if port is not None and not (port.isdigit() and 1 <= int(port) <= 65535):
        raise InvalidSetting(f"APP_PORT doit être un nombre entre 1 et 65535 (reçu : {port!r})")
    if level is not None and level.lower() not in LOG_LEVELS:
        raise InvalidSetting(f"APP_LOG_LEVEL doit valoir {', '.join(LOG_LEVELS)} (reçu : {level!r})")
    if docs is not None and docs.lower() not in YES + NO:
        raise InvalidSetting(f"APP_DOCS doit valoir oui ou non (reçu : {docs!r})")

    return Settings(
        base=read_database(variables),
        host=host or default.host,
        port=int(port) if port else default.port,
        log_level=level.lower() if level else default.log_level,
        docs=docs.lower() in YES if docs else default.docs,
    )


def read_database(variables: Mapping[str, str] = os.environ, prefix: str = "APP_DB_") -> DatabaseSettings | None:
    """Réglages de la base SQLite ; None si <prefixe>FILE est absente (données en mémoire).

    prefixe : « APP_DB_ » pour l'API ; les tests lisent « TESTS_DB_ » (tests/conftest.py).
    """
    file = variables.get(prefix + "FILE", "").strip()
    if not file:
        return None
    path = Path(file)
    if path.is_dir():
        raise InvalidSetting(f"{prefix}FILE doit être un fichier, pas un dossier (reçu : {file!r})")
    return DatabaseSettings(file=path)
