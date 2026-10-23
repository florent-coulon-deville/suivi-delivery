"""Annuaire : les comptes de l'outil, gardés par Keycloak, gérés depuis l'écran Comptes.

Les comptes ne sont pas dans notre base : Keycloak les garde (avec les mots de passe et les
clés). L'écran Comptes de l'interface passe quand même par notre API (/api/accounts). L'API les
gère dans Keycloak avec son propre client, « suivi-delivery-api » (un compte de service autorisé
à gérer les utilisateurs et les clients du domaine). Ainsi, l'administrateur ne voit jamais Keycloak.

Deux sortes de comptes :
  PERSON   un utilisateur Keycloak : identifiant, nom (« firstName »), mot de passe. Créé avec
             un mot de passe PROVISOIRE : Keycloak demande d'en choisir un nouveau à la première
             connexion (page à l'allure de l'outil) ;
  PROGRAM  un client Keycloak confidentiel avec compte de service (« client credentials ») :
             son identifiant (client_id) et sa clé (client_secret), affichée une seule fois.
             Marqué par l'attribut « suivi-delivery.program », pour ne pas confondre avec les
             clients de l'outil lui-même (interface, outils, api).
Le rôle (VIEWER, EDITOR, ADMIN) est un rôle du domaine, donné à l'utilisateur
(ou au compte de service du programme). Un seul à la fois.

Deux façons de réaliser l'annuaire, comme pour le stockage :
  KeycloakDirectory  le vrai : l'API d'administration de Keycloak (REST, JSON) ;
  MemoryDirectory   en mémoire : tests, essais sans Keycloak.

Les appels à Keycloak utilisent urllib, livré avec Python : pas de dépendance de plus.
"""

import json
import logging
import secrets
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from abc import ABC, abstractmethod
from typing import Any

from app.schemas import AccountKind, Role
from app.security import AUDIENCE, POSITION, KeycloakUnreachable, strongest_role

logger = logging.getLogger(__name__)

CLIENT_API = "suivi-delivery-api"  # le client de l'API dans Keycloak (keycloak/import/suivi-delivery.json)
CLIENT_TOOLS = "suivi-delivery-tools"  # le client des outils et scripts (jetons hors ligne)
PROGRAM_ATTRIBUTE = "suivi-delivery.program"  # marque les clients créés comme PROGRAM
DELAY = 10  # secondes : au-delà, Keycloak est considéré comme injoignable


class DirectoryConflict(Exception):
    """Identifiant déjà utilisé (409)."""


class DirectoryRejection(Exception):
    """Keycloak refuse la valeur, par exemple un mot de passe trop simple (422)."""


class Directory(ABC):
    """Les comptes : chaque compte est un dictionnaire id, identifiant, nom, sorte, role, actif."""

    @abstractmethod
    def list_all(self) -> list[dict]:
        """Tous les comptes (personnes et programmes)."""

    @abstractmethod
    def read(self, id_: str) -> dict | None:
        """Le compte, ou None s'il n'existe pas."""

    @abstractmethod
    def create_person(self, identifier: str, name: str, role: Role, password: str) -> dict:
        """Crée une personne, avec un mot de passe provisoire ; DirectoryConflict si l'identifiant est pris."""

    @abstractmethod
    def create_program(self, identifier: str, name: str, role: Role) -> tuple[dict, str]:
        """Crée un programme ; renvoie le compte et sa clé (à montrer une seule fois)."""

    @abstractmethod
    def update(
        self,
        account: dict,
        name: str | None = None,
        role: Role | None = None,
        active: bool | None = None,
        password: str | None = None,
    ) -> dict:
        """Change ce qui est donné (mot de passe : provisoire, PERSON seulement) ; renvoie le compte."""

    @abstractmethod
    def delete(self, account: dict) -> None:
        """Supprime le compte : il ne peut plus se connecter."""

    @abstractmethod
    def new_key(self, account: dict) -> str:
        """Nouvelle clé d'un programme (l'ancienne ne marche plus) ; renvoie la clé."""

    @abstractmethod
    def close_offline_access(self, subject: str) -> None:
        """Annule les jetons hors ligne de cette personne (ses scripts devront se reconnecter)."""


# --- En mémoire -----------------------------------------------------------------


class MemoryDirectory(Directory):
    """Les comptes en mémoire (tests, essais sans Keycloak). Mêmes règles que Keycloak : un
    identifiant pris (personne ou programme) est refusé ; les mots de passe et clés ne sont pas gardés."""

    def __init__(self) -> None:
        self._accounts: dict[str, dict] = {}
        self.temporary_passwords: dict[str, str] = {}  # identifiant → mot de passe (vérifié par les tests)
        self.keys: dict[str, str] = {}  # identifiant → clé du programme
        self.offline_access_closed: list[str] = []  # sujets dont les jetons hors ligne ont été annulés

    def list_all(self) -> list[dict]:
        return [dict(c) for c in self._accounts.values()]

    def read(self, id_: str) -> dict | None:
        account = self._accounts.get(id_)
        return dict(account) if account else None

    def _add(self, identifier: str, name: str, kind: AccountKind, role: Role) -> dict:
        if any(c["identifier"] == identifier for c in self._accounts.values()):
            raise DirectoryConflict(identifier)
        account = {"id": str(uuid.uuid4()), "identifier": identifier, "name": name, "kind": kind, "role": role}
        self._accounts[account["id"]] = {**account, "active": True}
        return dict(self._accounts[account["id"]])

    def create_person(self, identifier: str, name: str, role: Role, password: str) -> dict:
        account = self._add(identifier, name, AccountKind.PERSON, role)
        self.temporary_passwords[identifier] = password
        return account

    def create_program(self, identifier: str, name: str, role: Role) -> tuple[dict, str]:
        account = self._add(identifier, name, AccountKind.PROGRAM, role)
        return account, self.new_key(account)

    def update(self, account, name=None, role=None, active=None, password=None) -> dict:
        row = self._accounts[account["id"]]
        changes = {"name": name, "role": role, "active": active}
        row.update({field: value for field, value in changes.items() if value is not None})
        if password is not None:
            self.temporary_passwords[row["identifier"]] = password
        return dict(row)

    def delete(self, account: dict) -> None:
        del self._accounts[account["id"]]

    def new_key(self, account: dict) -> str:
        key = secrets.token_urlsafe(32)
        self.keys[account["identifier"]] = key
        return key

    def close_offline_access(self, subject: str) -> None:
        self.offline_access_closed.append(subject)


# --- Keycloak -------------------------------------------------------------------


class KeycloakDirectory(Directory):
    """Les comptes dans Keycloak, par son API d'administration (/admin/realms/<domaine>)."""

    def __init__(self, keycloak_url: str, realm: str, client_secret: str) -> None:
        self._tokens = f"{keycloak_url}/realms/{realm}/protocol/openid-connect/token"
        self._admin = f"{keycloak_url}/admin/realms/{realm}"
        self._client_secret = client_secret
        self._token: str | None = None
        self._expire = 0.0
        self._roles: dict[str, dict] = {}  # représentation des rôles (id, name), lue une fois

    # --- Appels HTTP ---

    def _open(self, request: urllib.request.Request) -> tuple[int, dict[str, str], Any]:
        try:
            with urllib.request.urlopen(request, timeout=DELAY) as response:  # noqa: S310 (adresse de nos réglages)
                status, headers, body = response.status, dict(response.headers), response.read()
        except urllib.error.HTTPError as error:
            status, headers, body = error.code, dict(error.headers), error.read()
        except OSError as error:  # URLError et TimeoutError en font partie
            raise KeycloakUnreachable(str(error)) from error
        content = json.loads(body) if body and body[:1] in (b"{", b"[", b'"') else None
        return status, headers, content

    def _admin_token(self) -> str:
        """Jeton du client de l'API (client credentials), gardé jusqu'à 30 s avant sa fin."""
        if self._token is None or time.monotonic() > self._expire:
            body = urllib.parse.urlencode(
                {"grant_type": "client_credentials", "client_id": CLIENT_API, "client_secret": self._client_secret}
            ).encode()
            request = urllib.request.Request(self._tokens, data=body, method="POST")  # noqa: S310
            request.add_header("Content-Type", "application/x-www-form-urlencoded")
            status, _, content = self._open(request)
            if status != 200 or not isinstance(content, dict):
                raise KeycloakUnreachable(f"connexion de l'API à Keycloak refusée ({status}) : vérifier la clé")
            self._token = str(content["access_token"])
            self._expire = time.monotonic() + int(content.get("expires_in", 60)) - 30
        return self._token

    def _call(self, method: str, path: str, body: Any = None) -> tuple[int, dict[str, str], Any]:
        data = json.dumps(body).encode() if body is not None else None
        request = urllib.request.Request(self._admin + path, data=data, method=method)  # noqa: S310
        request.add_header("Authorization", f"Bearer {self._admin_token()}")
        if data is not None:
            request.add_header("Content-Type", "application/json")
        status, headers, content = self._open(request)
        if status >= 500 or status in (401, 403):
            raise KeycloakUnreachable(f"Keycloak a répondu {status} à {method} {path}")
        return status, headers, content

    def _read(self, path: str) -> Any:
        status, _, content = self._call("GET", path)
        return content if status == 200 else None

    def _write(self, method: str, path: str, body: Any = None) -> tuple[dict[str, str], Any]:
        status, headers, content = self._call(method, path, body)
        if status == 409:
            raise DirectoryConflict(_message(content))
        if status >= 400:
            raise DirectoryRejection(_message(content))
        return headers, content

    # --- Rôles ---

    def _role(self, role: Role) -> dict:
        if role not in self._roles:
            self._roles[role] = self._read(f"/roles/{role}") or {}
        return {"id": self._roles[role]["id"], "name": role}

    def _roles_by_user(self) -> dict[str, Role]:
        """Le rôle de chaque utilisateur (et compte de service) qui en a un : 3 appels en tout."""
        roles: dict[str, list[str]] = {}
        for role in Role:
            for user in self._read(f"/roles/{role}/users?first=0&max=10000") or []:
                roles.setdefault(user["id"], []).append(role)
        return {id_: r for id_, list in roles.items() if (r := strongest_role(list)) is not None}

    def _give_role(self, user_id: str, role: Role | None) -> None:
        """Remplace le rôle de l'outil de cet utilisateur (les autres rôles de Keycloak ne bougent pas)."""
        current = self._read(f"/users/{user_id}/role-mappings/realm") or []
        to_remove = [{"id": r["id"], "name": r["name"]} for r in current if r["name"] in Role.__members__]
        if to_remove:
            self._write("DELETE", f"/users/{user_id}/role-mappings/realm", to_remove)
        if role is not None:
            self._write("POST", f"/users/{user_id}/role-mappings/realm", [self._role(role)])

    # --- Lecture ---

    def _person(self, user: dict, roles: dict[str, Role]) -> dict:
        return {
            "id": user["id"],
            "identifier": user["username"],
            "name": user.get("firstName") or user["username"],
            "kind": AccountKind.PERSON,
            "role": roles.get(user["id"]),
            "active": bool(user.get("enabled")),
        }

    def _program(self, client: dict, roles: dict[str, Role]) -> dict:
        service_account = self._read(f"/clients/{client['id']}/service-account-user") or {}
        return {
            "id": client["id"],
            "identifier": client["clientId"],
            "name": client.get("name") or client["clientId"],
            "kind": AccountKind.PROGRAM,
            "role": roles.get(service_account.get("id", "")),
            "active": bool(client.get("enabled")),
            "_account_service": service_account.get("id"),
        }

    @staticmethod
    def _is_program(client: dict) -> bool:
        return (client.get("attributes") or {}).get(PROGRAM_ATTRIBUTE) == "true"

    @staticmethod
    def _is_person(user: dict) -> bool:
        return "serviceAccountClientId" not in user and not user["username"].startswith("service-account-")

    def list_all(self) -> list[dict]:
        roles = self._roles_by_user()
        users = self._read("/users?first=0&max=10000&briefRepresentation=false") or []
        clients = self._read("/clients?first=0&max=10000") or []
        return [self._person(u, roles) for u in users if self._is_person(u)] + [
            _public(self._program(c, roles)) for c in clients if self._is_program(c)
        ]

    def read(self, id_: str) -> dict | None:
        return _public(account) if (account := self._read_full(id_)) else None

    def _read_full(self, id_: str) -> dict | None:
        if not _is_identifier(id_):
            return None  # jamais recollé dans une adresse s'il n'a pas la forme d'un identifiant Keycloak
        roles = self._roles_by_user()
        user = self._read(f"/users/{id_}")
        if user is not None and self._is_person(user):
            return self._person(user, roles)
        client = self._read(f"/clients/{id_}")
        if client is not None and self._is_program(client):
            return self._program(client, roles)
        return None

    # --- Écriture ---

    def _check_free_port(self, identifier: str) -> None:
        name = urllib.parse.quote(identifier)
        if self._read(f"/users?username={name}&exact=true") or self._read(f"/clients?clientId={name}"):
            raise DirectoryConflict(identifier)

    def create_person(self, identifier: str, name: str, role: Role, password: str) -> dict:
        self._check_free_port(identifier)
        user = {
            "username": identifier,
            "firstName": name,
            "enabled": True,
            "credentials": [{"type": "password", "value": password, "temporary": True}],
        }
        headers, _ = self._write("POST", "/users", user)
        id_ = _location_id(headers)
        try:
            self._give_role(id_, role)
        except Exception:
            self._call("DELETE", f"/users/{id_}")  # pas de compte à moitié créé
            raise
        return self.read(id_) or {}

    def create_program(self, identifier: str, name: str, role: Role) -> tuple[dict, str]:
        self._check_free_port(identifier)
        client = {
            "clientId": identifier,
            "name": name,
            "description": "Programme de l'outil Suivi de la delivery (géré depuis l'écran Comptes).",
            "enabled": True,
            "publicClient": False,
            "clientAuthenticatorType": "client-secret",
            "serviceAccountsEnabled": True,
            "standardFlowEnabled": False,
            "implicitFlowEnabled": False,
            "directAccessGrantsEnabled": False,
            "attributes": {PROGRAM_ATTRIBUTE: "true", "use.refresh.tokens": "false"},
            "protocolMappers": [
                {
                    "name": "audience-api",
                    "protocol": "openid-connect",
                    "protocolMapper": "oidc-audience-mapper",
                    "config": {
                        "included.custom.audience": AUDIENCE,
                        "access.token.claim": "true",
                        "id.token.claim": "false",
                        "introspection.token.claim": "true",
                    },
                }
            ],
        }
        headers, _ = self._write("POST", "/clients", client)
        id_ = _location_id(headers)
        try:
            service_account = self._read(f"/clients/{id_}/service-account-user") or {}
            self._give_role(service_account["id"], role)
            key = self._key(id_)
        except Exception:
            self._call("DELETE", f"/clients/{id_}")
            raise
        return self.read(id_) or {}, key

    def _key(self, id_client: str) -> str:
        content = self._read(f"/clients/{id_client}/client-secret") or {}
        return str(content.get("value", ""))

    def update(self, account, name=None, role=None, active=None, password=None) -> dict:
        if account["kind"] == AccountKind.PERSON:
            self._update_person(account["id"], name, role, active, password)
        else:
            self._update_program(account, name, role, active)
        return self.read(account["id"]) or {}

    def _update_person(self, id_: str, name, role, active, password) -> None:
        path = f"/users/{id_}"
        self._update_representation(path, "firstName", name, active)
        if password is not None:
            identifiers = {"type": "password", "value": password, "temporary": True}
            self._write("PUT", f"{path}/reset-password", identifiers)
        if role is not None:
            self._give_role(id_, role)
        if active is False or password is not None:
            self._call("POST", f"{path}/logout")  # ses connexions en cours prennent fin

    def _update_program(self, account: dict, name, role, active) -> None:
        complete = self._read_full(account["id"]) or account
        self._update_representation(f"/clients/{account['id']}", "name", name, active)
        if role is not None and complete.get("_account_service"):
            self._give_role(complete["_account_service"], role)

    def _update_representation(self, path: str, name_field: str, name, active) -> None:
        """Change le nom (champ name_field) et l'activation d'un utilisateur ou d'un client, s'ils sont donnés."""
        if name is None and active is None:
            return
        representation = self._read(path) or {}
        if name is not None:
            representation[name_field] = name
        if active is not None:
            representation["enabled"] = active
        self._write("PUT", path, representation)

    def delete(self, account: dict) -> None:
        folder = "users" if account["kind"] == AccountKind.PERSON else "clients"
        self._write("DELETE", f"/{folder}/{account['id']}")

    def new_key(self, account: dict) -> str:
        _, content = self._write("POST", f"/clients/{account['id']}/client-secret")
        return str((content or {}).get("value", ""))

    def close_offline_access(self, subject: str) -> None:
        # Retirer l'accord donné au client des outils annule ses jetons hors ligne (et ses sessions).
        if _is_identifier(subject):
            self._call("DELETE", f"/users/{subject}/consents/{CLIENT_TOOLS}")


def _public(account: dict) -> dict:
    """Le compte sans ses champs internes (commençant par « _ »)."""
    return {key: value for key, value in account.items() if not key.startswith("_")}


def _is_identifier(text: str) -> bool:
    """Un identifiant Keycloak (UUID) : lettres, chiffres et tirets seulement."""
    try:
        uuid.UUID(text)
    except ValueError:
        return False
    return True


def _location_id(headers: dict[str, str]) -> str:
    """L'identifiant du compte créé, à la fin de l'en-tête Location de la réponse 201."""
    location = next((v for k, v in headers.items() if k.lower() == "location"), "")
    return location.rstrip("/").rsplit("/", 1)[-1]


def _message(content: Any) -> str:
    """Le message d'erreur de Keycloak, ou un message générique."""
    if isinstance(content, dict):
        for key in ("errorMessage", "error_description", "error"):
            if content.get(key):
                return str(content[key])
    return "refusé par Keycloak"


def count_active_administrators(accounts: list[dict], excluding: str | None = None) -> int:
    """Nombre de comptes actifs avec le rôle ADMIN (sans compter « sauf »)."""
    return sum(
        1
        for c in accounts
        if c["active"]
        and c["role"] is not None
        and POSITION[c["role"]] == POSITION[Role.ADMIN]
        and c["id"] != excluding
    )
