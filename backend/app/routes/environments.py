"""Routes /api/environments : la liste des environnements (int, rec, preprod, prod…).

L'ordre (chaîne de promotion) est une information : il sert au tri, sans rien bloquer.
Changer is_prod est refusé (409) si cela rend des données incohérentes
(cluster d'un autre type, snapshot qui tournerait en prod).

  GET    /api/environments        200  liste, triée par ordre puis par code
  GET    /api/environments/{id}   200  | 404
  POST   /api/environments        201  + Location | 409 code déjà utilisé | 422
  PATCH  /api/environments/{id}   200  | 404 | 409 | 422
  PUT    /api/environments/{id}   200  remplace tout | 404 | 409 | 422
  DELETE /api/environments/{id}   204  | 404 | 409 utilisé par un namespace
"""

from fastapi import APIRouter, Request, Response, status

from app.consistency import apply_if_consistent
from app.routes import (
    R404,
    R409,
    R422,
    REPLACEMENT,
    StorageDep,
    add_location,
    check_unique,
    check_unused,
    read_or_404,
)
from app.schemas import Environment, EnvironmentCreation, EnvironmentUpdate
from app.storage import Storage

router = APIRouter(prefix="/environments", tags=["Environnements"])
OBJECT = "Environnement"


@router.get("", response_model=list[Environment], summary="Lister les environnements")
def list_all(storage: StorageDep):
    # Les environnements sans ordre viennent en dernier.
    return sorted(
        storage.environments.list_all(),
        key=lambda e: (e["promotion_order"] is None, e["promotion_order"] or 0, e["code"]),
    )


@router.get("/{environment_id}", response_model=Environment, responses=R404, summary="Lire un environnement")
def read(environment_id: int, storage: StorageDep):
    return read_or_404(storage.environments, environment_id, OBJECT)


def add(storage: Storage, environment: dict) -> dict:
    """Vérifie et enregistre un nouvel élément (route POST, et import de la configuration)."""
    code = environment["code"]
    check_unique(storage.environments, f"Le code {code} est déjà utilisé", code=code)
    return storage.environments.add(environment)


@router.post(
    "",
    response_model=Environment,
    status_code=status.HTTP_201_CREATED,
    responses=R409,
    summary="Créer un environnement",
)
def create(data: EnvironmentCreation, request: Request, response: Response, storage: StorageDep):
    environment = add(storage, data.model_dump())
    add_location(request, response, environment["id"])
    return environment


def save(storage: Storage, environment_id: int, changes: dict):
    """Enregistre une modification : les champs envoyés (PATCH) ou tous les champs (PUT)."""
    read_or_404(storage.environments, environment_id, OBJECT)
    if "code" in changes:
        check_unique(
            storage.environments,
            f"Le code {changes['code']} est déjà utilisé",
            excluding_id=environment_id,
            code=changes["code"],
        )
    return apply_if_consistent(storage, lambda s: s.environments.update(environment_id, changes))


@router.patch(
    "/{environment_id}",
    response_model=Environment,
    responses={**R404, **R409},
    summary="Modifier un environnement",
    description="Seuls les champs envoyés sont modifiés.",
)
def update(environment_id: int, data: EnvironmentUpdate, storage: StorageDep):
    # Uniquement les champs envoyés.
    return save(storage, environment_id, data.model_dump(exclude_unset=True))


@router.put(
    "/{environment_id}",
    response_model=Environment,
    responses={**R404, **R409, **R422},
    summary="Remplacer un environnement",
    description=REPLACEMENT,
)
def replace(environment_id: int, data: EnvironmentCreation, storage: StorageDep):
    return save(storage, environment_id, data.model_dump())  # tous les champs


@router.delete(
    "/{environment_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={**R404, **R409},
    summary="Supprimer un environnement",
)
def delete(environment_id: int, storage: StorageDep) -> None:
    read_or_404(storage.environments, environment_id, OBJECT)
    check_unused(storage.namespaces, "Environnement utilisé par au moins un namespace", environment_id=environment_id)
    storage.environments.delete(environment_id)


def _promotion_order(environment: dict) -> tuple:
    """Clé de tri : l'ordre de promotion ; les environnements sans ordre viennent en dernier."""
    return (environment["promotion_order"] is None, environment["promotion_order"] or 0, environment["code"])
