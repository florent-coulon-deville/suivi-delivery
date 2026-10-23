"""Routes /api/slots : les emplacements (slots) d'un namespace.

Un emplacement est l'endroit où l'on installe un module dans un namespace. Il porte un
nom de release (le nom du déploiement Helm), unique dans le namespace : plusieurs modules
peuvent ainsi cohabiter dans un même namespace. On y installe des versions successives
(helm upgrade) : chaque installation remplace la précédente.

Un emplacement est réservé à un module, dès sa création (même vide) : seules les versions
de ce module peuvent y être installées. Ce module appartient à l'application du namespace
(422). On ne peut changer le module que tant que l'emplacement est vide (409).

  GET    /api/slots                  200  liste, triée par nom de release
  GET    /api/slots?namespace_id=5   200  uniquement les emplacements du namespace 5
  GET    /api/slots?module_id=3      200  où le module 3 a sa place
  GET    /api/slots/{id}             200  | 404
  POST   /api/slots                  201  + Location | 409 nom déjà utilisé | 422
  PATCH  /api/slots/{id}             200  | 404 | 409 | 422
  PUT    /api/slots/{id}             200  remplace tout | 404 | 409 | 422
  DELETE /api/slots/{id}             204  | 404 | 409 a déjà des installations
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
    check_unused,
    read_or_404,
)
from app.schemas import Slot, SlotCreation, SlotUpdate
from app.storage import Storage

router = APIRouter(prefix="/slots", tags=["Emplacements"])
OBJECT = "Emplacement"


def check(storage: Storage, slot: dict, excluding_id: int | None = None) -> None:
    """Vérifications communes à la création et à la modification (emplacement complet)."""
    check_reference(storage.namespaces, slot["namespace_id"], "Namespace")
    check_reference(storage.modules, slot["module_id"], "Module")
    namespace = storage.namespaces.read_existing(slot["namespace_id"])
    if storage.modules.read_existing(slot["module_id"])["application_id"] != namespace["application_id"]:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "Le module n'appartient pas à l'application du namespace"
        )
    check_unique(
        storage.slots,
        f"Le nom de release {slot['release_name']} est déjà utilisé dans ce namespace",
        excluding_id=excluding_id,
        namespace_id=slot["namespace_id"],
        release_name=slot["release_name"],
    )


@router.get("", response_model=list[Slot], summary="Lister les emplacements")
def list_all(storage: StorageDep, namespace_id: int | None = None, module_id: int | None = None):
    criteria = {} if namespace_id is None else {"namespace_id": namespace_id}
    if module_id is not None:
        criteria["module_id"] = module_id
    return sorted(storage.slots.list_all(**criteria), key=lambda e: (e["namespace_id"], e["release_name"]))


@router.get("/{slot_id}", response_model=Slot, responses=R404, summary="Lire un emplacement")
def read(slot_id: int, storage: StorageDep):
    return read_or_404(storage.slots, slot_id, OBJECT)


def add(storage: Storage, slot: dict) -> dict:
    """Vérifie et enregistre un nouvel élément (route POST, et import de la configuration)."""
    check(storage, slot)
    return storage.slots.add(slot)


@router.post(
    "",
    response_model=Slot,
    status_code=status.HTTP_201_CREATED,
    responses={**R409, **R422},
    summary="Créer un emplacement",
)
def create(data: SlotCreation, request: Request, response: Response, storage: StorageDep):
    slot = add(storage, data.model_dump())
    add_location(request, response, slot["id"])
    return slot


def save(storage: Storage, slot_id: int, changes: dict):
    """Enregistre une modification : les champs envoyés (PATCH) ou tous les champs (PUT)."""
    current = read_or_404(storage.slots, slot_id, OBJECT)
    check(storage, {**current, **changes}, excluding_id=slot_id)
    if changes.get("module_id", current["module_id"]) != current["module_id"]:
        check_unused(
            storage.installations,
            "On ne change pas le module d'un emplacement qui a déjà des installations",
            slot_id=slot_id,
        )
    # Changer de namespace peut changer d'environnement : refusé (409) si cela crée une incompatibilité.
    return apply_if_consistent(storage, lambda s: s.slots.update(slot_id, changes))


@router.patch(
    "/{slot_id}",
    response_model=Slot,
    responses={**R404, **R409, **R422},
    summary="Modifier un emplacement",
    description="Seuls les champs envoyés sont modifiés.",
)
def update(slot_id: int, data: SlotUpdate, storage: StorageDep):
    # Uniquement les champs envoyés.
    return save(storage, slot_id, data.model_dump(exclude_unset=True))


@router.put(
    "/{slot_id}",
    response_model=Slot,
    responses={**R404, **R409, **R422},
    summary="Remplacer un emplacement",
    description=REPLACEMENT,
)
def replace(slot_id: int, data: SlotCreation, storage: StorageDep):
    return save(storage, slot_id, data.model_dump())  # tous les champs


@router.delete(
    "/{slot_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={**R404, **R409},
    summary="Supprimer un emplacement",
)
def delete(slot_id: int, storage: StorageDep) -> None:
    read_or_404(storage.slots, slot_id, OBJECT)
    check_unused(storage.installations, "Emplacement qui a déjà des installations", slot_id=slot_id)
    storage.slots.delete(slot_id)
