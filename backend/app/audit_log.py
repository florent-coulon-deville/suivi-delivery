"""Journal des actions : qui a créé, modifié ou supprimé quoi, et quand.

Chaque saisie acceptée laisse une ligne dans la table « journal » : la date, l'auteur (recopié :
le journal reste lisible si le compte est supprimé), l'objet (sa table et son numéro), l'action
(CREATE, UPDATE, DELETE) et l'objet avant et après la saisie.

Comment c'est rempli : AUTOMATIQUEMENT, par le stockage (app/storage.py, TrackedTable). Chaque
ajout, modification ou suppression dans une table suivie écrit sa ligne, dans la même transaction
que la saisie : les deux sont enregistrées ensemble, ou annulées ensemble (une saisie incohérente,
refusée par app/consistency.py, n'écrit donc rien). Aucune route n'a à y penser.

Qui est l'auteur ? La personne ou le programme connecté de la requête en cours, lu dans son jeton
Keycloak. Au début de chaque requête, RequestAuthor prépare une case vide (AUTHOR) ;
app/access.py la remplit une fois le jeton vérifié (log_author). Sans auteur, rien n'est écrit.

La gestion des comptes (écran Comptes) est notée aussi, par la route elle-même (log_edit) :
les comptes sont dans Keycloak, pas dans une de nos tables. Objet « comptes », identifiant
Keycloak du compte ; jamais de mot de passe ni de clé (« changé » quand un mot de passe provisoire
est donné).

Le journal ne se modifie ni ne s'efface : l'API ne fait que le lire (GET /api/audit_log, ADMIN).
"""

from contextvars import ContextVar
from dataclasses import dataclass
from datetime import UTC, date, datetime
from enum import Enum
from typing import TYPE_CHECKING, Any

from app.schemas import AuditAction, AuthorKind

if TYPE_CHECKING:  # pour les types seulement (storage.py importe déjà ce fichier)
    from app.security import Identity
    from app.storage import Table

# Tables dont les saisies vont au journal : toutes, sauf le journal lui-même.
UNTRACKED_TABLES = {"audit_log"}
# Champs secrets, jamais recopiés (mot de passe provisoire donné à un compte, clé d'un programme).
HIDDEN_FIELDS = {"accounts": {"password", "key"}}
# Champs techniques, mis à jour en coulisse : ignorés (une modification de ces seuls champs n'est pas notée).
IGNORED_FIELDS: dict[str, set[str]] = {}
HIDDEN, CHANGE = "masqué", "changé"


@dataclass
class Author:
    """L'auteur de la requête en cours, noté par app/access.py une fois le jeton vérifié."""

    identifier: str | None = None  # None : pas (encore) d'auteur, rien n'est noté
    subject: str | None = None  # identifiant Keycloak (« sub »)
    kind: AuthorKind | None = None


# La case « auteur » de la requête en cours (None hors requête).
AUTHOR: ContextVar[Author | None] = ContextVar("author", default=None)


class RequestAuthor:
    """Middleware ASGI : une case « auteur » vide pour chaque requête sous /api.

    C'est un objet (et non une valeur) : app/access.py le remplit depuis un autre fil d'exécution
    (FastAPI y lance les fonctions non « async »), et la route le voit quand même.
    """

    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or not scope["path"].startswith("/api"):
            return await self.app(scope, receive, send)
        token = AUTHOR.set(Author())
        try:
            await self.app(scope, receive, send)
        finally:
            AUTHOR.reset(token)


def log_author(identity: Identity) -> None:
    """La personne (ou le programme) connectée devient l'auteur des saisies de la requête en cours."""
    author = AUTHOR.get()
    if author is not None:
        author.identifier, author.subject = identity.identifier, identity.subject
        author.kind = AuthorKind(identity.kind)


def log_edit(
    audit_log: Table, object: str, object_id: str, action: AuditAction, before: dict | None, after: dict | None
) -> None:
    """Note une saisie faite hors de nos tables (gestion des comptes, dans Keycloak)."""
    row = audit_entry(object, action, object_id, before, after)
    if row is not None:
        audit_log.add(row)


def audit_entry(
    table: str, action: AuditAction, object_id: int | str, before: dict | None, after: dict | None
) -> dict | None:
    """La ligne à écrire au journal pour cette saisie ; None si rien à noter
    (table non suivie, pas d'auteur, ou rien de changé)."""
    author = AUTHOR.get()
    if table in UNTRACKED_TABLES or author is None or author.identifier is None:
        return None
    ignored = IGNORED_FIELDS.get(table, set())
    if action == AuditAction.UPDATE and _without(before, ignored) == _without(after, ignored):
        return None  # rien n'a vraiment changé
    hidden = HIDDEN_FIELDS.get(table, set())
    return {
        "date": datetime.now(UTC),
        "author_id": author.subject,
        "author": author.identifier,
        "author_kind": author.kind,
        "object": table,
        "object_id": str(object_id),
        "action": action,
        "before": _to_json(_hide(before, hidden, ignored, None)),
        "after": _to_json(_hide(after, hidden, ignored, before)),
    }


def _without(row: dict | None, fields: set[str]) -> dict | None:
    return None if row is None else {k: v for k, v in row.items() if k not in fields}


def _hide(row: dict | None, hidden: set[str], ignored: set[str], before: dict | None) -> dict | None:
    """Les secrets remplacés par « masqué », ou « changé » s'ils diffèrent de « avant »."""
    if row is None:
        return None
    result = _without(row, ignored) or {}
    for field in hidden & result.keys():
        change = before is not None and before.get(field) != row[field]
        result[field] = CHANGE if change else HIDDEN
    return result


def _to_json(value: Any) -> Any:
    """Une valeur enregistrable en JSON : dates en texte ISO 8601, énumérations en texte."""
    if isinstance(value, dict):
        return {key: _to_json(v) for key, v in value.items()}
    if isinstance(value, list | tuple):
        return [_to_json(v) for v in value]
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, Enum):
        return value.value
    return value
