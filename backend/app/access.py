"""Contrôle d'accès : qui appelle (jeton d'accès de Keycloak) et a-t-il le droit (rôle) ?

Chaque appel à une route protégée doit porter l'en-tête « Authorization: Bearer <jeton> », un
jeton d'accès remis par Keycloak (docs/keycloak.md) :
  - à une personne, connectée sur la page de connexion (interface, Bruno, Swagger), ou par un
    jeton « hors ligne » pour ses scripts ;
  - à un programme, avec son identifiant et sa clé (client credentials).
L'API le vérifie (signature, émetteur, destinataire, expiration : app/security.py) et y lit le rôle.

  401  pas de jeton, jeton invalide ou expiré. Réponse avec l'en-tête WWW-Authenticate: Bearer.
  403  le jeton est bon, mais son rôle ne suffit pas.
  503  Keycloak ne répond pas (impossible de lire ses clés de signature).

Droits (branchés dans main.py, ou dans la route) :
  structure            GET / HEAD : VIEWER ; POST / PUT / PATCH / DELETE : ADMIN
                       (environnements, clusters, zones réseau, applications, namespaces, modules,
                       dépendances, compatibilités, emplacements : le paramétrage, fait par l'admin)
  livraisons           GET / HEAD : VIEWER ; POST / PUT / PATCH / DELETE : EDITOR
                       (versions de module, paramètres, installations : saisis par les développeurs)
  /api/configuration   GET / HEAD (export) : VIEWER ; PATCH (import) : ADMIN
  /api/accounts, /api/audit_log   ADMIN
  /api/me             toute personne ou programme connecté
  probes (/livez…), Swagger : sans jeton
"""

from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from fastapi.openapi.models import OAuthFlowAuthorizationCode, OAuthFlowClientCredentials, OAuthFlows
from fastapi.security import OAuth2

from app.audit_log import log_author
from app.schemas import Role
from app.security import Identity, InvalidToken, KeycloakUnreachable, Verifier, has_role

# Décrit la connexion dans Swagger : c'est ce qui affiche le bouton « Authorize ». Les adresses
# de Keycloak sont complétées par routes/documentation.py (elles dépendent des réglages).
# Adresse provisoire de Keycloak, remplacée par la vraie dans routes/documentation.py.
_KEYCLOAK = "/auth"
_schema = OAuth2(
    flows=OAuthFlows(
        authorizationCode=OAuthFlowAuthorizationCode(authorizationUrl=_KEYCLOAK, tokenUrl=_KEYCLOAK),
        clientCredentials=OAuthFlowClientCredentials(tokenUrl=_KEYCLOAK),
    ),
    scheme_name="Connexion",
    description="Personne : page de connexion de l'outil (authorization code + PKCE, client "
    "« suivi-delivery-tools »). Programme : son identifiant et sa clé (client credentials).",
    auto_error=False,  # on renvoie nous-mêmes un 401 avec un message clair
)


def _reject(message: str) -> HTTPException:
    return HTTPException(status.HTTP_401_UNAUTHORIZED, message, headers={"WWW-Authenticate": "Bearer"})


def connected_identity(request: Request, authorization: Annotated[str | None, Depends(_schema)]) -> Identity:
    """Qui appelle ; 401 si le jeton manque ou ne vaut rien.
    Il devient l'auteur des saisies de la requête, notées au journal (app/audit_log.py)."""
    schema, _, token = (authorization or "").partition(" ")
    if schema.lower() != "bearer" or not token:
        raise _reject("Jeton d'accès manquant : connectez-vous")
    verifier: Verifier | None = request.app.state.verifier
    if verifier is None:
        raise _reject("Connexion impossible : l'API n'est pas reliée à Keycloak (APP_KEYCLOAK_URL)")
    try:
        identity = verifier.check(token)
    except KeycloakUnreachable as error:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Keycloak ne répond pas : réessayez") from error
    except InvalidToken as error:
        raise _reject("Jeton d'accès invalide ou expiré") from error
    log_author(identity)
    return identity


IdentityDep = Annotated[Identity, Depends(connected_identity)]


def require(role: Role):
    """Dépendance : la personne (ou le programme) connectée doit avoir au moins ce rôle, sinon 403."""

    def check(identity: IdentityDep) -> Identity:
        if not has_role(identity, role):
            raise HTTPException(status.HTTP_403_FORBIDDEN, f"Droits insuffisants : rôle {role} requis")
        return identity

    return check


def _read_or_update(role_to_update: Role):
    """Dépendance : lire demande VIEWER, modifier demande le rôle donné."""

    def check(request: Request, identity: IdentityDep) -> Identity:
        role = Role.VIEWER if request.method in ("GET", "HEAD") else role_to_update
        return require(role)(identity)

    return check


# Structure (le paramétrage général) : seul l'administrateur la modifie.
structure_rights = _read_or_update(Role.ADMIN)
# Livraisons (versions, paramètres, installations) : les développeurs (EDITOR) les saisissent.
delivery_rights = _read_or_update(Role.EDITOR)
