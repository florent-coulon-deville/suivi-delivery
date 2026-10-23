"""Journal des actions : quoi a été créé, modifié ou supprimé, et quand.

Chaque saisie acceptée laisse une ligne dans la table « audit_log » : la date, l'objet (sa table
et son numéro), l'action (CREATE, UPDATE, DELETE) et l'objet avant et après la saisie. Pas
d'auteur : cette version de l'outil n'a pas de comptes (tout le monde peut tout faire).

Comment c'est rempli : AUTOMATIQUEMENT, par le stockage (app/storage.py, TrackedTable). Chaque
ajout, modification ou suppression dans une table suivie écrit sa ligne, dans la même transaction
que la saisie : les deux sont enregistrées ensemble, ou annulées ensemble (une saisie incohérente,
refusée par app/consistency.py, n'écrit donc rien). Aucune route n'a à y penser.

Le journal ne se modifie ni ne s'efface : l'API ne fait que le lire (GET /api/audit-log).
"""

from datetime import UTC, date, datetime
from enum import Enum
from typing import Any

from app.schemas import AuditAction

# Tables dont les saisies vont au journal : toutes, sauf le journal lui-même.
UNTRACKED_TABLES = {"audit_log"}


def audit_entry(
    table: str, action: AuditAction, object_id: int | str, before: dict | None, after: dict | None
) -> dict | None:
    """La ligne à écrire au journal pour cette saisie ; None si rien à noter
    (table non suivie, ou rien de changé)."""
    if table in UNTRACKED_TABLES:
        return None
    if action == AuditAction.UPDATE and before == after:
        return None  # rien n'a vraiment changé
    return {
        "date": datetime.now(UTC),
        "object": table,
        "object_id": str(object_id),
        "action": action,
        "before": _to_json(before),
        "after": _to_json(after),
    }


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
