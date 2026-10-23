"""Routes /api/parameters.

Un paramètre appartient à un MODULE (celui qu'il configure) et est TECHNICAL ou APPLICATION. Son nom
est libre (une version comme « 2.3 », ou tout autre chose), en minuscules, unique par module et par
type. Il est affecté à aucun, un ou plusieurs namespaces de l'application de son module
(namespace_ids). Une installation choisit un paramètre technique et un paramètre applicatif.
Un paramètre utilisé par une installation ne peut plus changer de module ni de type, ni perdre le
namespace où il est installé (409) : l'installation deviendrait fausse.

  GET    /api/parameters                    200  liste, triée par nom
  GET    /api/parameters?module_id=3        200  uniquement les paramètres du module 3
  GET    /api/parameters?application_id=2   200  uniquement les paramètres des modules de l'application 2
  GET    /api/parameters?namespace_id=5     200  uniquement les paramètres affectés au namespace 5
  GET    /api/parameters/{id}               200  | 404
  POST   /api/parameters                    201  + Location | 409 nom déjà utilisé | 422
  PATCH  /api/parameters/{id}               200  | 404 | 409 | 422
  PUT    /api/parameters/{id}               200  remplace tout | 404 | 409 | 422
  DELETE /api/parameters/{id}               204  | 404 | 409 utilisé par une installation
"""

from fastapi import APIRouter, HTTPException, Request, Response, status

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
from app.schemas import Parameter, ParameterCreation, ParameterType, ParameterUpdate
from app.storage import Storage

router = APIRouter(prefix="/parameters", tags=["Paramètres"])
OBJECT = "Paramètre"


def check(storage: Storage, parameter: dict, excluding_id: int | None = None) -> None:
    """Vérifications communes à la création et à la modification (paramètre complet)."""
    check_reference(storage.modules, parameter["module_id"], "Module")
    module = storage.modules.read_existing(parameter["module_id"])
    check_unique(
        storage.parameters,
        f"Le paramètre {parameter['type']} {parameter['name']} existe déjà pour le module {module['code']}",
        excluding_id=excluding_id,
        module_id=parameter["module_id"],
        type=parameter["type"],
        name=parameter["name"],
    )
    for namespace_id in parameter["namespace_ids"]:
        check_reference(storage.namespaces, namespace_id, "Namespace")
        if storage.namespaces.read_existing(namespace_id)["application_id"] != module["application_id"]:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                f"Namespace {namespace_id} : il n'appartient pas à l'application du module {module['code']}",
            )


def is_used(storage: Storage, parameter_id: int) -> bool:
    """Une installation utilise-t-elle ce paramètre ?"""
    return any(
        parameter_id in (i["technical_parameter_id"], i["application_parameter_id"])
        for i in storage.installations.list_all()
    )


def check_installations(storage: Storage, current: dict, new: dict) -> None:
    """409 si le changement rend fausse une installation qui utilise ce paramètre : autre module,
    autre type, ou plus affecté au namespace où il est installé (règle d'or : rien d'incohérent)."""
    for installation in storage.installations.list_all():
        if current["id"] == installation["technical_parameter_id"]:
            expected_type = ParameterType.TECHNICAL
        elif current["id"] == installation["application_parameter_id"]:
            expected_type = ParameterType.APPLICATION
        else:
            continue
        slot = storage.slots.read_existing(installation["slot_id"])
        if (
            new["type"] != expected_type
            or new["module_id"] != slot["module_id"]
            or slot["namespace_id"] not in new["namespace_ids"]
        ):
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                f"Le paramètre {current['name']} est utilisé par l'installation de l'emplacement "
                f"{slot['release_name']} : son module, son type et ce namespace ne peuvent plus changer",
            )


def without_duplicates(ids: list[int]) -> list[int]:
    return sorted(set(ids))


@router.get("", response_model=list[Parameter], summary="Lister les paramètres")
def list_all(
    storage: StorageDep,
    module_id: int | None = None,
    application_id: int | None = None,
    namespace_id: int | None = None,
):
    criteria = {} if module_id is None else {"module_id": module_id}
    parameters = storage.parameters.list_all(**criteria)
    if application_id is not None:
        modules = {m["id"] for m in storage.modules.list_all(application_id=application_id)}
        parameters = [p for p in parameters if p["module_id"] in modules]
    if namespace_id is not None:
        parameters = [p for p in parameters if namespace_id in p["namespace_ids"]]
    return sorted(parameters, key=lambda p: p["name"])


@router.get("/{parameter_id}", response_model=Parameter, responses=R404, summary="Lire un paramètre")
def read(parameter_id: int, storage: StorageDep):
    return read_or_404(storage.parameters, parameter_id, OBJECT)


def add(storage: Storage, parameter: dict) -> dict:
    """Vérifie et enregistre un nouvel élément (route POST, et import de la configuration)."""
    parameter = {**parameter, "namespace_ids": without_duplicates(parameter["namespace_ids"])}
    check(storage, parameter)
    return storage.parameters.add(parameter)


@router.post(
    "",
    response_model=Parameter,
    status_code=status.HTTP_201_CREATED,
    responses={**R409, **R422},
    summary="Créer un paramètre",
)
def create(data: ParameterCreation, request: Request, response: Response, storage: StorageDep):
    parameter = add(storage, data.model_dump())
    add_location(request, response, parameter["id"])
    return parameter


def save(storage: Storage, parameter_id: int, changes: dict):
    """Enregistre une modification : les champs envoyés (PATCH) ou tous les champs (PUT)."""
    current = read_or_404(storage.parameters, parameter_id, OBJECT)
    if "namespace_ids" in changes:
        changes["namespace_ids"] = without_duplicates(changes["namespace_ids"])
    check(storage, {**current, **changes}, excluding_id=parameter_id)
    check_installations(storage, current, {**current, **changes})
    return storage.parameters.update(parameter_id, changes)


@router.patch(
    "/{parameter_id}",
    response_model=Parameter,
    responses={**R404, **R409, **R422},
    summary="Modifier un paramètre",
    description="Seuls les champs envoyés sont modifiés. `namespace_ids` remplace toute la liste.",
)
def update(parameter_id: int, data: ParameterUpdate, storage: StorageDep):
    # Uniquement les champs envoyés.
    return save(storage, parameter_id, data.model_dump(exclude_unset=True))


@router.put(
    "/{parameter_id}",
    response_model=Parameter,
    responses={**R404, **R409, **R422},
    summary="Remplacer un paramètre",
    description=REPLACEMENT,
)
def replace(parameter_id: int, data: ParameterCreation, storage: StorageDep):
    return save(storage, parameter_id, data.model_dump())  # tous les champs


@router.delete(
    "/{parameter_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={**R404, **R409},
    summary="Supprimer un paramètre",
)
def delete(parameter_id: int, storage: StorageDep) -> None:
    read_or_404(storage.parameters, parameter_id, OBJECT)
    if is_used(storage, parameter_id):
        raise HTTPException(status.HTTP_409_CONFLICT, "Paramètre utilisé par au moins une installation")
    storage.parameters.delete(parameter_id)
