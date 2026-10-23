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

  Base PostgreSQL (voir app/storage_postgres.py et docs/postgresql.md) :
    APP_DB_HOST               adresse du serveur PostgreSQL                aucune : données EN MÉMOIRE,
                                                                           perdues à l'arrêt (essais)
    APP_DB_PORT               port                                         5432
    APP_DB_NAME               nom de la base                               suivi_delivery
    APP_DB_SCHEMA             schéma de nos tables, dans cette base        suivi_delivery
    APP_DB_USER               utilisateur                                  suivi_delivery
    APP_DB_PASSWORD           mot de passe (obligatoire avec APP_DB_HOST)  aucun

  Connexion par Keycloak (voir app/security.py, app/directory.py et docs/keycloak.md) :
    APP_KEYCLOAK_URL          adresse INTERNE de Keycloak, avec /auth      aucune : aucun jeton n'est
                              (ex. http://suivi-delivery-keycloak:8080/    accepté (essais sans connexion)
                              auth) : clés de signature, gestion des
                              comptes
    APP_KEYCLOAK_REALM        nom du domaine Keycloak de l'outil           suivi-delivery
    APP_KEYCLOAK_CLIENT_SECRET  clé du client « suivi-delivery-api », qui  aucune : écran Comptes
                              gère les comptes (16 caractères au moins)    indisponible (503)
    APP_FRONTEND_URL          adresse publique de l'interface : Keycloak   http://localhost:8080
                              est servi sous <adresse>/auth, c'est
                              l'émetteur attendu dans les jetons
    APP_API_URL               adresse publique de l'API : retour de        aucune
                              Swagger après la connexion (affichée dans
                              l'aide de Swagger)

En production (Helm, OpenShift), APP_DB_PASSWORD et APP_KEYCLOAK_CLIENT_SECRET viennent d'un Secret.

Une valeur invalide arrête le démarrage avec un message clair (InvalidSetting) :
mieux vaut ne pas démarrer que démarrer avec un réglage faux.
"""

import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from urllib.parse import urlsplit

LOG_LEVELS = ("critical", "error", "warning", "info", "debug", "trace")
YES = ("oui", "true", "1", "yes", "o", "y")
NO = ("non", "false", "0", "no", "n")

MIN_CLIENT_SECRET_LENGTH = 16
DEFAULT_FRONTEND_URL = "http://localhost:8080"


class InvalidSetting(ValueError):
    """Une variable d'environnement a une valeur impossible."""


@dataclass(frozen=True)
class SecuritySettings:
    """La connexion par Keycloak (docs/keycloak.md)."""

    keycloak_url: str | None = None  # APP_KEYCLOAK_URL (interne), sans « / » final ; None : aucun jeton accepté
    realm: str = "suivi-delivery"  # APP_KEYCLOAK_REALM
    # repr=False : les secrets n'apparaissent jamais si on affiche les réglages (journaux, erreurs).
    client_secret: str | None = field(default=None, repr=False)  # APP_KEYCLOAK_CLIENT_SECRET
    frontend_url: str = DEFAULT_FRONTEND_URL  # APP_FRONTEND_URL, sans « / » final
    api_url: str | None = None  # APP_API_URL, sans « / » final

    @property
    def issuer(self) -> str:
        """L'émetteur des jetons (« iss ») : Keycloak tel que le voit le navigateur, sous l'interface."""
        return f"{self.frontend_url}/auth/realms/{self.realm}"

    @property
    def realm_url(self) -> str | None:
        """Le domaine, à l'adresse interne de Keycloak (clés de signature, gestion des comptes)."""
        return f"{self.keycloak_url}/realms/{self.realm}" if self.keycloak_url else None


@dataclass(frozen=True)
class DatabaseSettings:
    """Connexion à la base PostgreSQL."""

    host: str
    password: str = field(repr=False)
    port: int = 5432
    name: str = "suivi_delivery"
    user: str = "suivi_delivery"
    schema: str = "suivi_delivery"  # nos tables ; « public » reste vide, Keycloak a son schéma

    def connection(self) -> dict:
        """Paramètres de connexion psycopg : nos tables sont cherchées dans notre schéma."""
        return {
            "host": self.host,
            "port": self.port,
            "dbname": self.name,
            "user": self.user,
            "password": self.password,
            "options": f"-c search_path={self.schema} -c TimeZone=UTC",  # dates relues en UTC
        }


@dataclass(frozen=True)
class Settings:
    base: DatabaseSettings | None = None  # None : données en mémoire, perdues à l'arrêt
    host: str = "127.0.0.1"
    port: int = 8000
    log_level: str = "info"
    docs: bool = True
    security: SecuritySettings = SecuritySettings()


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

    _check_port("APP_PORT", port)
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
        security=_read_security(value),
    )


def _check_port(name: str, port: str | None) -> None:
    if port is not None and not (port.isdigit() and 1 <= int(port) <= 65535):
        raise InvalidSetting(f"{name} doit être un nombre entre 1 et 65535 (reçu : {port!r})")


def read_database(variables: Mapping[str, str] = os.environ, prefix: str = "APP_DB_") -> DatabaseSettings | None:
    """Réglages de la base PostgreSQL ; None si <prefixe>HOST est absente (données en mémoire).

    prefixe : « APP_DB_ » pour l'API ; les tests lisent « TESTS_DB_ » (tests/conftest.py).
    """

    def value(name: str) -> str | None:
        text = variables.get(prefix + name, "").strip()
        return text or None

    host, port, name, user, password = (value(n) for n in ("HOST", "PORT", "NAME", "USER", "PASSWORD"))
    schema = value("SCHEMA")
    if host is None:
        # Règle d'or : rien d'incohérent. Des réglages de base sans adresse sont sans doute un oubli.
        fields = (("PORT", port), ("NAME", name), ("USER", user), ("SCHEMA", schema))
        others = [prefix + n for n, v in fields if v] + ([prefix + "PASSWORD"] if password else [])
        if others:
            raise InvalidSetting(f"{', '.join(others)} sans {prefix}HOST : préciser l'adresse de la base")
        return None
    if password is None:
        raise InvalidSetting(f"{prefix}PASSWORD est obligatoire avec {prefix}HOST")
    _check_port(prefix + "PORT", port)
    if schema is not None and not _is_name(schema):
        raise InvalidSetting(f"{prefix}SCHEMA : lettres minuscules, chiffres et _ seulement (reçu : {schema!r})")
    default = DatabaseSettings(host=host, password=password)
    return DatabaseSettings(
        host=host,
        password=password,
        port=int(port) if port else default.port,
        name=name or default.name,
        user=user or default.user,
        schema=schema or default.schema,
    )


def _is_name(text: str) -> bool:
    """Un nom PostgreSQL simple (schéma) : il entre dans search_path sans guillemets."""
    return text[:1].isalpha() and all(c.isascii() and (c.islower() or c.isdigit() or c == "_") for c in text)


def _read_security(value) -> SecuritySettings:
    default = SecuritySettings()
    keycloak = _public_url("APP_KEYCLOAK_URL", value("APP_KEYCLOAK_URL"))
    realm = value("APP_KEYCLOAK_REALM")
    key = value("APP_KEYCLOAK_CLIENT_SECRET")
    frontend_url = _public_url("APP_FRONTEND_URL", value("APP_FRONTEND_URL"))
    api_url = _public_url("APP_API_URL", value("APP_API_URL"))

    if realm is not None and not all(c.isascii() and (c.isalnum() or c in "-_") for c in realm):
        raise InvalidSetting(f"APP_KEYCLOAK_REALM : lettres, chiffres, - et _ seulement (reçu : {realm!r})")
    # Les valeurs secrètes ne sont jamais recopiées dans les messages d'erreur.
    if key is not None and len(key) < MIN_CLIENT_SECRET_LENGTH:
        raise InvalidSetting(f"APP_KEYCLOAK_CLIENT_SECRET doit faire au moins {MIN_CLIENT_SECRET_LENGTH} caractères")
    # Règle d'or : rien d'incohérent. Une clé sans Keycloak est sans doute un oubli.
    if key is not None and keycloak is None:
        raise InvalidSetting("APP_KEYCLOAK_CLIENT_SECRET sans APP_KEYCLOAK_URL : préciser l'adresse de Keycloak")
    return SecuritySettings(
        keycloak_url=keycloak,
        realm=realm or default.realm,
        client_secret=key,
        frontend_url=frontend_url or default.frontend_url,
        api_url=api_url,
    )


def _public_url(name: str, url: str | None) -> str | None:
    """Une adresse publique (http(s)://hôte[:port][/chemin]), sans « / » final ; None si absente."""
    if url is None:
        return None
    url = url.rstrip("/")
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.hostname or parts.query or parts.fragment:
        raise InvalidSetting(f"{name} doit être une adresse http(s)://hôte[:port] (reçu : {url!r})")
    return url
