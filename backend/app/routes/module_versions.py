"""Routes /api/module-versions : les versions d'un module (release ou snapshot).

Le numéro de version est unique pour un module donné.

  GET    /api/module-versions               200  liste
  GET    /api/module-versions?module_id=3   200  uniquement les versions du module 3
  GET    /api/module-versions/{id}          200  | 404
  POST   /api/module-versions               201  + Location | 409 numéro déjà utilisé | 422
  PATCH  /api/module-versions/{id}          200  | 404 | 409 | 422
  PUT    /api/module-versions/{id}          200  remplace tout | 404 | 409 | 422
  DELETE /api/module-versions/{id}          204  | 404 | 409 déjà installée ou a des compatibilités

Modifier le numéro d'une version installée est refusé (409) s'il rend des versions incompatibles.
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
    check_reference,
    check_unique,
    check_unused,
    read_or_404,
)
from app.schemas import ModuleVersion, ModuleVersionCreation, ModuleVersionUpdate
from app.storage import Storage

router = APIRouter(prefix="/module-versions", tags=["Versions de module"])
OBJECT = "Version de module"


def check(storage: Storage, version: dict, excluding_id: int | None = None) -> None:
    """Vérifications communes à la création et à la modification (version complète)."""
    check_reference(storage.modules, version["module_id"], "Module")
    check_unique(
        storage.module_versions,
        f"La version {version['number']} existe déjà pour ce module",
        excluding_id=excluding_id,
        module_id=version["module_id"],
        number=version["number"],
    )


@router.get("", response_model=list[ModuleVersion], summary="Lister les versions de module")
def list_all(storage: StorageDep, module_id: int | None = None):
    criteria = {} if module_id is None else {"module_id": module_id}
    return sorted(storage.module_versions.list_all(**criteria), key=lambda v: (v["module_id"], v["number"]))


@router.get("/{version_id}", response_model=ModuleVersion, responses=R404, summary="Lire une version de module")
def read(version_id: int, storage: StorageDep):
    return read_or_404(storage.module_versions, version_id, OBJECT)


def add(storage: Storage, version: dict) -> dict:
    """Vérifie et enregistre un nouvel élément (route POST, et import de la configuration)."""
    check(storage, version)
    return storage.module_versions.add(version)


@router.post(
    "",
    response_model=ModuleVersion,
    status_code=status.HTTP_201_CREATED,
    responses={**R409, **R422},
    summary="Créer une version de module",
)
def create(data: ModuleVersionCreation, request: Request, response: Response, storage: StorageDep):
    version = add(storage, data.model_dump())
    add_location(request, response, version["id"])
    return version


def save(storage: Storage, version_id: int, changes: dict):
    """Enregistre une modification : les champs envoyés (PATCH) ou tous les champs (PUT)."""
    current = read_or_404(storage.module_versions, version_id, OBJECT)
    check(storage, {**current, **changes}, excluding_id=version_id)
    return apply_if_consistent(storage, lambda s: s.module_versions.update(version_id, changes))


@router.patch(
    "/{version_id}",
    response_model=ModuleVersion,
    responses={**R404, **R409, **R422},
    summary="Modifier une version de module",
    description="Seuls les champs envoyés sont modifiés.",
)
def update(version_id: int, data: ModuleVersionUpdate, storage: StorageDep):
    # Uniquement les champs envoyés.
    return save(storage, version_id, data.model_dump(exclude_unset=True))


@router.put(
    "/{version_id}",
    response_model=ModuleVersion,
    responses={**R404, **R409, **R422},
    summary="Remplacer une version de module",
    description=REPLACEMENT,
)
def replace(version_id: int, data: ModuleVersionCreation, storage: StorageDep):
    return save(storage, version_id, data.model_dump())  # tous les champs


@router.delete(
    "/{version_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={**R404, **R409},
    summary="Supprimer une version de module",
)
def delete(version_id: int, storage: StorageDep) -> None:
    read_or_404(storage.module_versions, version_id, OBJECT)
    check_unused(storage.installations, "Version déjà installée", module_version_id=version_id)
    check_unused(storage.compatibilities, "Version qui a encore des compatibilités", module_version_id=version_id)
    storage.module_versions.delete(version_id)
