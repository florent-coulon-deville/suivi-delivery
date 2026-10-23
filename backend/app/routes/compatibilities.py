"""Routes /api/compatibilities : de quelles versions de ses dépendances une version a besoin.

Exemple : « le batch de paie 2.3 a besoin de l'authentification en 1.4 ou plus ».
  module_version_id = batch de paie 2.3, required_module_id = authentification,
  condition = AT_LEAST, version = 1.4

Conditions (bornes comprises) :
  EXACT        précisément « version »
  AT_LEAST   « version » ou plus récente
  BETWEEN         de « version » à « version_max »

Règles (422) : le module de la version doit avoir déclaré qu'il dépend du module requis ;
version_max est obligatoire pour BETWEEN (et supérieure ou égale à version), interdite sinon.
Une seule compatibilité par version et par module requis (409).
Refus (409) si la compatibilité rend incompatible ce qui tourne déjà dans un environnement.

  GET    /api/compatibilities                        200  liste
  GET    /api/compatibilities?module_version_id=4    200  les besoins de la version 4
  GET    /api/compatibilities?required_module_id=2     200  les versions qui ont besoin du module 2
  GET    /api/compatibilities/{id}                   200  | 404
  POST   /api/compatibilities                        201  + Location | 409 | 422
  PATCH  /api/compatibilities/{id}                   200  modifie la condition | 404 | 409 | 422
  PUT    /api/compatibilities/{id}                   200  remplace tout | 404 | 409 | 422
  DELETE /api/compatibilities/{id}                   204  | 404
"""

from fastapi import APIRouter, HTTPException, Request, Response, status

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
    read_or_404,
)
from app.schemas import Compatibility, CompatibilityCreation, CompatibilityUpdate, ConditionType
from app.storage import Storage
from app.versions import key

router = APIRouter(prefix="/compatibilities", tags=["Compatibilités"])
OBJECT = "Compatibilité"


def reject(message: str):
    raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, message)


def check(storage: Storage, compatibility: dict, excluding_id: int | None = None) -> None:
    """Vérifications communes à la création et à la modification (compatibilité complète)."""
    check_reference(storage.module_versions, compatibility["module_version_id"], "Version de module")
    check_reference(storage.modules, compatibility["required_module_id"], "Module")
    module_id = storage.module_versions.read_existing(compatibility["module_version_id"])["module_id"]
    if storage.dependencies.find(module_id=module_id, depends_on_id=compatibility["required_module_id"]) is None:
        reject("Il faut d'abord déclarer que le module dépend du module requis")
    if compatibility["condition"] == ConditionType.BETWEEN:
        if compatibility["version_max"] is None:
            reject("version_max est obligatoire pour la condition BETWEEN")
        if key(compatibility["version_max"]) < key(compatibility["version"]):
            reject("version_max doit être supérieure ou égale à version")
    elif compatibility["version_max"] is not None:
        reject("version_max ne sert qu'avec la condition BETWEEN")
    check_unique(
        storage.compatibilities,
        "Cette version a déjà une compatibilité pour ce module",
        excluding_id=excluding_id,
        module_version_id=compatibility["module_version_id"],
        required_module_id=compatibility["required_module_id"],
    )


@router.get("", response_model=list[Compatibility], summary="Lister les compatibilités")
def list_all(storage: StorageDep, module_version_id: int | None = None, required_module_id: int | None = None):
    criteria = {}
    if module_version_id is not None:
        criteria["module_version_id"] = module_version_id
    if required_module_id is not None:
        criteria["required_module_id"] = required_module_id
    return sorted(storage.compatibilities.list_all(**criteria), key=lambda c: (c["module_version_id"], c["id"]))


@router.get("/{compatibility_id}", response_model=Compatibility, responses=R404, summary="Lire une compatibilité")
def read(compatibility_id: int, storage: StorageDep):
    return read_or_404(storage.compatibilities, compatibility_id, OBJECT)


def add(storage: Storage, compatibility: dict) -> dict:
    """Vérifie et enregistre un nouvel élément (route POST, et import de la configuration)."""
    check(storage, compatibility)
    return apply_if_consistent(storage, lambda s: s.compatibilities.add(compatibility))


@router.post(
    "",
    response_model=Compatibility,
    status_code=status.HTTP_201_CREATED,
    responses={**R409, **R422},
    summary="Déclarer une compatibilité",
)
def create(data: CompatibilityCreation, request: Request, response: Response, storage: StorageDep):
    compatibility = add(storage, data.model_dump())
    add_location(request, response, compatibility["id"])
    return compatibility


def save(storage: Storage, compatibility_id: int, changes: dict):
    """Enregistre une modification : les champs envoyés (PATCH) ou tous les champs (PUT)."""
    current = read_or_404(storage.compatibilities, compatibility_id, OBJECT)
    check(storage, {**current, **changes}, excluding_id=compatibility_id)
    return apply_if_consistent(storage, lambda s: s.compatibilities.update(compatibility_id, changes))


@router.patch(
    "/{compatibility_id}",
    response_model=Compatibility,
    responses={**R404, **R409, **R422},
    summary="Modifier une condition",
    description="Seuls les champs envoyés sont modifiés.",
)
def update(compatibility_id: int, data: CompatibilityUpdate, storage: StorageDep):
    # Uniquement les champs envoyés.
    return save(storage, compatibility_id, data.model_dump(exclude_unset=True))


@router.put(
    "/{compatibility_id}",
    response_model=Compatibility,
    responses={**R404, **R409, **R422},
    summary="Remplacer une condition",
    description=REPLACEMENT,
)
def replace(compatibility_id: int, data: CompatibilityCreation, storage: StorageDep):
    return save(storage, compatibility_id, data.model_dump())  # tous les champs


@router.delete(
    "/{compatibility_id}", status_code=status.HTTP_204_NO_CONTENT, responses=R404, summary="Supprimer une compatibilité"
)
def delete(compatibility_id: int, storage: StorageDep) -> None:
    read_or_404(storage.compatibilities, compatibility_id, OBJECT)
    storage.compatibilities.delete(compatibility_id)  # retirer un besoin ne peut rien casser
