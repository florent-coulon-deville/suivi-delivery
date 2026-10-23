"""Routes /api/accounts : les comptes qui peuvent se connecter (réservées à l'ADMIN).

Les comptes sont gardés par Keycloak ; ces routes les gèrent pour l'écran Comptes, sans que
l'administrateur ait à ouvrir Keycloak (app/directory.py).

Une PERSON se connecte avec un mot de passe. L'administrateur lui en donne un PROVISOIRE (à la
création, ou plus tard s'il l'a oublié) : Keycloak lui demande d'en choisir un nouveau à sa
connexion suivante. Un PROGRAM se connecte avec une clé générée par Keycloak, affichée une
seule fois (à la création, ou en en demandant une nouvelle). Les mots de passe et les clés ne
sont jamais relus.

Règle d'or : il reste toujours au moins un administrateur actif. Supprimer, désactiver ou
rétrograder le dernier est refusé (409) : sinon plus personne ne pourrait gérer les comptes.

  GET    /api/accounts            200  liste, triée par identifiant
  GET    /api/accounts/{id}       200  | 404
  POST   /api/accounts            201  + Location (+ « cle » pour un PROGRAM) | 409 identifiant déjà utilisé | 422
  PATCH  /api/accounts/{id}       200  | 404 | 409 dernier administrateur | 422
  DELETE /api/accounts/{id}       204  | 404 | 409 dernier administrateur
  POST   /api/accounts/{id}/key   200  nouvelle clé d'un PROGRAM (l'ancienne ne marche plus) | 404 | 422
Pas de PUT (405) : un mot de passe ne se « remplace » pas avec le reste ; PATCH suffit.
Keycloak injoignable, ou API non reliée à Keycloak : 503.

Chaque saisie est notée au journal (objet « comptes »), sans mot de passe ni clé.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from app.audit_log import log_edit
from app.directory import Directory, DirectoryConflict, DirectoryRejection, count_active_administrators
from app.routes import R404, R409, StorageDep, add_location
from app.schemas import (
    Account,
    AccountCreation,
    AccountKind,
    AccountUpdate,
    AuditAction,
    CreatedAccount,
    NewKey,
    Role,
)
from app.security import KeycloakUnreachable

router = APIRouter(prefix="/accounts", tags=["Comptes"])
OBJECT = "accounts"


def directory_of(request: Request) -> Directory:
    directory: Directory | None = request.app.state.directory
    if directory is None:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Gestion des comptes indisponible : l'API n'a pas la clé de son client Keycloak "
            "(APP_KEYCLOAK_CLIENT_SECRET)",
        )
    return directory


DirectoryDep = Annotated[Directory, Depends(directory_of)]


class KeycloakErrors:
    """Bloc « with » : traduit les refus de Keycloak en réponses HTTP claires."""

    def __init__(self, conflict: str = "Identifiant déjà utilisé") -> None:
        self._conflict = conflict

    def __enter__(self) -> None:
        return None

    def __exit__(self, type_, error, _trace) -> bool:
        if isinstance(error, DirectoryConflict):
            raise HTTPException(status.HTTP_409_CONFLICT, self._conflict) from error
        if isinstance(error, DirectoryRejection):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"Refusé : {error}") from error
        if isinstance(error, KeycloakUnreachable):
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Keycloak ne répond pas : réessayez") from error
        return False


def _read_or_404(directory: Directory, account_id: str) -> dict:
    with KeycloakErrors():
        account = directory.read(account_id)
    if account is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Compte {account_id} introuvable")
    return account


def _check_an_admin_remains(directory: Directory, account: dict, changes: dict | None) -> None:
    """409 si le changement (None : suppression) retire le dernier administrateur actif."""
    remains_admin = changes is not None and changes.get("role", account["role"]) == Role.ADMIN
    remains_active = changes is not None and changes.get("active", account["active"])
    if account["role"] != Role.ADMIN or not account["active"] or (remains_admin and remains_active):
        return
    with KeycloakErrors():
        others = count_active_administrators(directory.list_all(), excluding=account["id"])
    if others == 0:
        raise HTTPException(status.HTTP_409_CONFLICT, "Il doit rester au moins un administrateur actif")


@router.get("", response_model=list[Account], summary="Lister les comptes")
def list_all(directory: DirectoryDep):
    with KeycloakErrors():
        return sorted(directory.list_all(), key=lambda c: c["identifier"])


@router.get("/{account_id}", response_model=Account, responses=R404, summary="Lire un compte")
def read(account_id: str, directory: DirectoryDep):
    return _read_or_404(directory, account_id)


@router.post(
    "",
    response_model=CreatedAccount,
    status_code=status.HTTP_201_CREATED,
    responses=R409,
    summary="Créer un compte",
    description="PERSON : avec un mot de passe provisoire, à changer à sa première connexion. "
    "PROGRAM : la réponse contient sa clé (« cle ») ; elle ne sera plus jamais affichée.",
)
def create(data: AccountCreation, request: Request, response: Response, directory: DirectoryDep, storage: StorageDep):
    with KeycloakErrors(f"L'identifiant {data.identifier} est déjà utilisé"):
        if data.kind == AccountKind.PERSON:
            assert data.password is not None  # vérifié par AccountCreation
            account = directory.create_person(data.identifier, data.name, data.role, data.password)
            key = None
        else:
            account, key = directory.create_program(data.identifier, data.name, data.role)
    log_edit(storage.audit_log, OBJECT, account["id"], AuditAction.CREATE, None, account)
    add_location(request, response, account["id"])
    return {**account, "key": key}


@router.patch(
    "/{account_id}",
    response_model=Account,
    responses={**R404, **R409},
    summary="Modifier un compte",
    description="Seuls les champs envoyés sont modifiés. Un nouveau mot de passe (provisoire), ou un compte "
    "désactivé, met fin à toutes ses connexions en cours.",
)
def update(account_id: str, data: AccountUpdate, directory: DirectoryDep, storage: StorageDep):
    account = _read_or_404(directory, account_id)
    changes = data.model_dump(exclude_unset=True)
    password = changes.pop("password", None)
    if password is not None and account["kind"] != AccountKind.PERSON:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "Un PROGRAM n'a pas de mot de passe : demander une nouvelle clé (POST /api/accounts/{id}/key)",
        )
    if password is not None and password.lower() == account["identifier"]:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "Le mot de passe doit être différent de l'identifiant"
        )
    _check_an_admin_remains(directory, account, changes)
    if not changes and password is None:
        return account
    with KeycloakErrors():
        after = directory.update(account, password=password, **changes)
    # Le mot de passe n'est jamais recopié : « changé » dans le journal.
    secret = {"password": "temporary"} if password is not None else {}  # NOSONAR : une étiquette, pas un mot de passe
    log_edit(storage.audit_log, OBJECT, account_id, AuditAction.UPDATE, account, {**after, **secret})
    return after


@router.delete(
    "/{account_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={**R404, **R409},
    summary="Supprimer un compte",
)
def delete(account_id: str, directory: DirectoryDep, storage: StorageDep) -> None:
    account = _read_or_404(directory, account_id)
    _check_an_admin_remains(directory, account, None)
    with KeycloakErrors():
        directory.delete(account)
    log_edit(storage.audit_log, OBJECT, account_id, AuditAction.DELETE, account, None)


@router.post(
    "/{account_id}/key",
    response_model=NewKey,
    responses=R404,
    summary="Nouvelle clé d'un programme",
    description="Génère une nouvelle clé, affichée une seule fois. L'ancienne ne marche plus.",
)
def new_key(account_id: str, directory: DirectoryDep, storage: StorageDep):
    account = _read_or_404(directory, account_id)
    if account["kind"] != AccountKind.PROGRAM:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Seul un PROGRAM a une clé")
    with KeycloakErrors():
        key = directory.new_key(account)
    log_edit(storage.audit_log, OBJECT, account_id, AuditAction.UPDATE, account, {**account, "key": "new"})
    return {"key": key}
