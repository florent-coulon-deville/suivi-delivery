"""Sécurité : vérifier les jetons d'accès remis par Keycloak, et lire qui appelle.

Keycloak gère les comptes, les mots de passe, la page de connexion et la fabrication des jetons
(docs/keycloak.md). L'API, elle, se contente de VÉRIFIER chaque jeton reçu :
  - sa signature : Keycloak signe avec une clé privée qu'il garde ; l'API lit les clés publiques
    correspondantes sur Keycloak (adresse « certs », gardées en mémoire et relues quand Keycloak
    en change) ;
  - son émetteur (« iss ») : le domaine « suivi-delivery » de NOTRE Keycloak, à l'adresse que
    voient les navigateurs (<APP_FRONTEND_URL>/auth/realms/suivi-delivery) ;
  - son destinataire (« aud ») : « suivi-delivery-api », ajouté par Keycloak aux jetons des
    clients de l'outil (interface, outils, programmes). Un jeton fait pour une autre application
    du même Keycloak est refusé ;
  - sa date d'expiration (5 minutes après sa fabrication).

Qui appelle ? Lu dans le jeton (« Identite ») :
  sujet        identifiant Keycloak, qui ne change jamais (« sub ») ;
  identifiant  identifiant de connexion d'une PERSON (« preferred_username »), ou nom du
               client d'un PROGRAM (« azp ») ;
  sorte        PROGRAM pour un compte de service (client credentials), PERSON sinon ;
  rôle         le plus fort des rôles VIEWER, EDITOR, ADMIN du jeton (rôles du
               domaine, « realm_access »). Aucun : la personne ne peut rien faire dans l'outil.

Un rôle retiré, ou un compte désactivé dans Keycloak, prend effet au plus tard à la fin du jeton
en cours (5 minutes) : le renouvellement est alors refusé par Keycloak.
"""

import logging
from dataclasses import dataclass
from typing import Any

import jwt

from app.schemas import AccountKind, Role
from app.settings import SecuritySettings

logger = logging.getLogger(__name__)

AUDIENCE = "suivi-delivery-api"  # destinataire des jetons de l'outil (mappeur « audience-api » de Keycloak)
ALGORITHMS = ["RS256"]  # signature de Keycloak par défaut (clé RSA)
SERVICE_ACCOUNT_PREFIX = "service-account-"  # nom donné par Keycloak à l'utilisateur d'un programme

# Ordre des rôles : chacun comprend les droits du précédent (rôles composites dans Keycloak).
POSITION = {Role.VIEWER: 1, Role.EDITOR: 2, Role.ADMIN: 3}


@dataclass(frozen=True)
class Identity:
    """Qui appelle, d'après son jeton."""

    subject: str
    identifier: str
    name: str
    kind: AccountKind
    role: Role | None


class InvalidToken(Exception):
    """Jeton illisible, mal signé, expiré, ou pas fait pour l'outil."""


class KeycloakUnreachable(Exception):
    """Keycloak ne répond pas : impossible de lire ses clés de signature (ou de gérer les comptes)."""


def has_role(identity: Identity, role: Role) -> bool:
    """L'identité a-t-elle au moins ce rôle ?"""
    return identity.role is not None and POSITION[identity.role] >= POSITION[role]


def strongest_role(roles: list[str]) -> Role | None:
    """Le plus fort des rôles de l'outil dans cette liste (les autres rôles de Keycloak sont ignorés)."""
    known = [Role(r) for r in roles if r in Role.__members__]
    return max(known, key=POSITION.__getitem__, default=None)


def token_identity(content: dict[str, Any]) -> Identity:
    """L'identité décrite par le contenu (déjà vérifié) d'un jeton d'accès."""
    username = str(content.get("preferred_username") or "")
    program = "client_id" in content or username.startswith(SERVICE_ACCOUNT_PREFIX)
    identifier = str(content.get("azp") or username) if program else username
    roles = content.get("realm_access", {}).get("roles", [])
    return Identity(
        subject=str(content["sub"]),
        identifier=identifier,
        name=str(content.get("name") or identifier),
        kind=AccountKind.PROGRAM if program else AccountKind.PERSON,
        role=strongest_role(roles if isinstance(roles, list) else []),
    )


class Verifier:
    """Vérifie les jetons d'accès d'un Keycloak.

    cles : d'où viennent les clés publiques. Par défaut, l'adresse « certs » du domaine sur
    Keycloak (PyJWKClient : lues au premier jeton, gardées en mémoire, relues si un jeton est
    signé avec une clé inconnue). Les tests donnent la leur (tests/conftest.py).
    """

    def __init__(self, issuer: str, keys: jwt.PyJWKClient | None = None, fixed_key: Any = None) -> None:
        self.issuer = issuer
        self._keys = keys
        self._fixed_key = fixed_key

    @classmethod
    def from_settings(cls, settings: SecuritySettings) -> Verifier | None:
        """Le vérificateur des réglages, ou None sans Keycloak (aucun jeton ne sera accepté)."""
        if settings.realm_url is None:
            return None
        certs = f"{settings.realm_url}/protocol/openid-connect/certs"
        return cls(settings.issuer, keys=jwt.PyJWKClient(certs, cache_keys=True, lifespan=3600, timeout=5))

    def check(self, token: str) -> Identity:
        """L'identité du jeton ; InvalidToken s'il ne vaut rien."""
        try:
            key = (
                self._fixed_key
                if self._fixed_key is not None
                else self._keycloak_keys().get_signing_key_from_jwt(token).key
            )
            content = jwt.decode(
                token,
                key,
                algorithms=ALGORITHMS,
                audience=AUDIENCE,
                issuer=self.issuer,
                options={"require": ["exp", "iat", "sub", "iss", "aud"]},
                leeway=10,  # secondes : petit décalage d'horloge toléré entre Keycloak et l'API
            )
        except jwt.PyJWKClientConnectionError as error:
            logger.exception("Keycloak injoignable pour lire ses clés de signature")
            raise KeycloakUnreachable(str(error)) from error
        except jwt.PyJWTError as error:
            raise InvalidToken(str(error)) from error
        if content.get("typ", "Bearer") != "Bearer":
            raise InvalidToken("pas un jeton d'accès")  # ex. un jeton d'identité (« ID token »)
        return token_identity(content)

    def _keycloak_keys(self) -> jwt.PyJWKClient:
        assert self._keys is not None, "ni clés de Keycloak, ni clé fixe"
        return self._keys
