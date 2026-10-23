"""Routes /api/modules.

Un module est un programme (Python, Java…), rattaché à une application.
Il est de type CAPABILITY (brique du socle) ou BUSINESS_PROJECT.
Son code est unique au sein de son application.

  GET    /api/modules                    200  liste, triée par code
  GET    /api/modules?application_id=3   200  uniquement les modules de l'application 3
  GET    /api/modules?type=CAPABILITY      200  uniquement les modules de ce type
  GET    /api/modules/{id}               200  | 404
  POST   /api/modules                    201  + Location | 409 code déjà utilisé | 422 (application inexistante…)
                                              with_slots=true : un emplacement dans chaque namespace de
                                              l'application, tout ou rien (409 si un nom de release est déjà pris)
  PATCH  /api/modules/{id}               200  | 404 | 409 | 422
  PUT    /api/modules/{id}               200  remplace tout | 404 | 409 | 422
  DELETE /api/modules/{id}               204  | 404 | 409 a encore des versions, des paramètres, des dépendances
                                              ou des emplacements

Changer l'application d'un module est refusé (409) s'il a des emplacements dans les namespaces de l'ancienne.
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
from app.routes import slots as slot_routes
from app.schemas import Module, ModuleCreation, ModuleCreationWithSlots, ModuleType, ModuleUpdate
from app.storage import Storage

router = APIRouter(prefix="/modules", tags=["Modules"])
OBJECT = "Module"


def check(storage: Storage, module: dict, excluding_id: int | None = None) -> None:
    """Vérifications communes à la création et à la modification (module complet)."""
    check_reference(storage.applications, module["application_id"], "Application")
    check_unique(
        storage.modules,
        f"Le code {module['code']} est déjà utilisé dans cette application",
        excluding_id=excluding_id,
        application_id=module["application_id"],
        code=module["code"],
    )


@router.get("", response_model=list[Module], summary="Lister les modules")
def list_all(storage: StorageDep, application_id: int | None = None, type: ModuleType | None = None):
    criteria: dict[str, object] = {} if application_id is None else {"application_id": application_id}
    if type is not None:
        criteria["type"] = type
    return sorted(storage.modules.list_all(**criteria), key=lambda m: m["code"])


@router.get("/{module_id}", response_model=Module, responses=R404, summary="Lire un module")
def read(module_id: int, storage: StorageDep):
    return read_or_404(storage.modules, module_id, OBJECT)


def add(storage: Storage, module: dict) -> dict:
    """Vérifie et enregistre un nouvel élément (route POST, et import de la configuration)."""
    check(storage, module)
    return storage.modules.add(module)


@router.post(
    "",
    response_model=Module,
    status_code=status.HTTP_201_CREATED,
    responses={**R409, **R422},
    summary="Créer un module",
    description=(
        "Avec `with_slots: true` (défaut `false`), crée aussi un emplacement pour ce module dans chaque "
        "namespace de son application (nom de release = code du module, « _ » remplacé par « - »). "
        "**Tout ou rien** : si un nom de release est déjà pris dans un namespace, rien n'est créé (409)."
    ),
)
def create(data: ModuleCreationWithSlots, request: Request, response: Response, storage: StorageDep):
    creation = add_with_slots if data.with_slots else add
    module = creation(storage, data.model_dump(exclude={"with_slots"}))
    add_location(request, response, module["id"])
    return module


def add_with_slots(storage: Storage, module: dict) -> dict:
    """Crée le module, puis un emplacement pour lui dans chaque namespace de son application
    (nom de release = code du module, « _ » remplacé par « - »).

    Tout ou rien : le tout est fait dans un essai du stockage ; si un nom de release est déjà pris
    dans un namespace (409, le message le nomme), rien n'est enregistré, pas même le module.
    """
    with storage.attempt() as attempt:
        module = add(attempt, module)
        release_name = module["code"].replace("_", "-")
        for namespace in attempt.namespaces.list_all(application_id=module["application_id"]):
            slot = {"namespace_id": namespace["id"], "module_id": module["id"], "release_name": release_name}
            slot_routes.add(attempt, slot)
    return module


def save(storage: Storage, module_id: int, changes: dict):
    """Enregistre une modification : les champs envoyés (PATCH) ou tous les champs (PUT)."""
    current = read_or_404(storage.modules, module_id, OBJECT)
    check(storage, {**current, **changes}, excluding_id=module_id)  # le module tel qu'il serait après
    if changes.get("application_id", current["application_id"]) != current["application_id"]:
        # Ses paramètres sont affectés à des namespaces de son application : ils deviendraient faux.
        check_unused(
            storage.parameters,
            "Module qui a des paramètres : il ne peut pas changer d'application",
            module_id=module_id,
        )
    return apply_if_consistent(storage, lambda s: s.modules.update(module_id, changes))


@router.patch(
    "/{module_id}",
    response_model=Module,
    responses={**R404, **R409, **R422},
    summary="Modifier un module",
    description="Seuls les champs envoyés sont modifiés.",
)
def update(module_id: int, data: ModuleUpdate, storage: StorageDep):
    # Uniquement les champs envoyés.
    return save(storage, module_id, data.model_dump(exclude_unset=True))


@router.put(
    "/{module_id}",
    response_model=Module,
    responses={**R404, **R409, **R422},
    summary="Remplacer un module",
    description=REPLACEMENT,
)
def replace(module_id: int, data: ModuleCreation, storage: StorageDep):
    return save(storage, module_id, data.model_dump())  # tous les champs


@router.delete(
    "/{module_id}", status_code=status.HTTP_204_NO_CONTENT, responses={**R404, **R409}, summary="Supprimer un module"
)
def delete(module_id: int, storage: StorageDep) -> None:
    read_or_404(storage.modules, module_id, OBJECT)
    check_unused(storage.module_versions, "Module qui a encore des versions", module_id=module_id)
    check_unused(storage.parameters, "Module qui a encore des paramètres", module_id=module_id)
    check_unused(storage.slots, "Module qui a encore des emplacements", module_id=module_id)
    check_unused(storage.dependencies, "Module qui dépend encore d'autres modules", module_id=module_id)
    check_unused(storage.dependencies, "Module dont d'autres modules dépendent encore", depends_on_id=module_id)
    storage.modules.delete(module_id)
