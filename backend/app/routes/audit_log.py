"""Route /api/audit_log : le journal des actions (qui a créé, modifié ou supprimé quoi, et quand).

Le journal est rempli automatiquement à chaque saisie acceptée (app/audit_log.py). Il se lit
seulement : pas de POST, PUT, PATCH ni DELETE (405). Personne ne peut le modifier ni l'effacer.

Réservé à l'ADMIN (403 pour les autres rôles), qui voit tout : les saisies des données et
la gestion des comptes. Le journal dit qui a fait quoi : c'est une information d'administration.

  GET /api/audit_log   200  lignes, les plus récentes en premier. Filtres, tous facultatifs :
                          auteur (identifiant de connexion), objet (nom de table, ex. installations,
                          ou comptes), object_id, action (CREATE, UPDATE, DELETE),
                          depuis / until (date et heure, bornes comprises ; sans fuseau : UTC),
                          limite (nombre de lignes, 200 par défaut, 1000 au plus).

Les filtres sur les dates sont faits par l'API, après lecture : suffisant pour le volume de
saisies d'une équipe ; à revoir si le journal devient très gros.
"""

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Query

from app.routes import StorageDep
from app.schemas import AuditAction, AuditEntry

router = APIRouter(prefix="/audit-log", tags=["Journal"])


@router.get(
    "",
    response_model=list[AuditEntry],
    summary="Lire le journal des actions",
    description="Les plus récentes en premier. Réservé à l'ADMIN.",
)
def list_all(
    storage: StorageDep,
    author: str | None = None,
    object: str | None = None,
    object_id: str | None = None,
    action: AuditAction | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    limit: Annotated[int, Query(ge=1, le=1000)] = 200,
):
    # Tout est en minuscules (identifiants, noms de table) : « Admin » trouve « admin ».
    criteria = {
        "author": author.lower() if author else None,
        "object": object.lower() if object else None,
        "object_id": object_id,
        "action": action,
    }
    rows = storage.audit_log.list_all(**{field: value for field, value in criteria.items() if value is not None})
    if since is not None:
        rows = [row for row in rows if row["date"] >= _to_utc(since)]
    if until is not None:
        rows = [row for row in rows if row["date"] <= _to_utc(until)]
    return sorted(rows, key=lambda row: (row["date"], row["id"]), reverse=True)[:limit]


def _to_utc(instant: datetime) -> datetime:
    """Une date sans fuseau horaire est lue en UTC (comme les dates du journal)."""
    return instant if instant.tzinfo is not None else instant.replace(tzinfo=UTC)
