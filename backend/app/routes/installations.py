"""Routes /api/installations : l'historique des installations.

Une installation = une version de module, posée sur un emplacement, avec un paramètre technique
et un paramètre applicatif du module, à une date donnée.
La dernière installation d'un emplacement est ce qui y tourne actuellement.

Une installation est un fait passé : pas de modification (PATCH → 405).
On peut la supprimer pour corriger une erreur de saisie.

Contrôles à la création et à la suppression :
  - 409 si, après le changement, des versions incompatibles tourneraient ensemble dans
    un environnement (voir app/consistency.py et les compatibilités) ;
422 si :
  - tout ce qui est référencé existe ;
  - la version est une version du module auquel l'emplacement est réservé ;
  - le paramètre technique est bien de type TECHNICAL, l'applicatif de type APPLICATION ;
  - les deux paramètres sont des paramètres du module de l'emplacement ;
  - les deux paramètres sont affectés au namespace de l'emplacement.

  GET    /api/installations                       200  liste, la plus récente en premier
  GET    /api/installations?slot_id=7      200  historique d'un emplacement
  GET    /api/installations?module_version_id=4   200  où cette version a été installée
  GET    /api/installations/{id}                  200  | 404
  POST   /api/installations                       201  + Location | 422
  DELETE /api/installations/{id}                  204  | 404
"""

from fastapi import APIRouter, HTTPException, Request, Response, status

from app.consistency import apply_if_consistent
from app.routes import R404, R409, R422, StorageDep, add_location, check_reference, read_or_404
from app.schemas import Installation, InstallationCreation, ParameterType
from app.storage import Storage

router = APIRouter(prefix="/installations", tags=["Installations"])
OBJECT = "Installation"


def reject(message: str):
    raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, message)


def check_parameter(
    storage: Storage, parameter_id: int, expected_type: ParameterType, namespace_id: int, module_id: int
) -> None:
    """Le paramètre existe, a le bon type, configure le module de l'emplacement et est affecté au namespace."""
    check_reference(storage.parameters, parameter_id, "Paramètre")
    parameter = storage.parameters.read_existing(parameter_id)
    if parameter["type"] != expected_type:
        reject(f"Paramètre {parameter['name']} : il n'est pas {expected_type}")
    if parameter["module_id"] != module_id:
        module = storage.modules.read_existing(module_id)["code"]
        reject(f"Paramètre {parameter['name']} : ce n'est pas un paramètre du module {module}")
    if namespace_id not in parameter["namespace_ids"]:
        reject(f"Paramètre {parameter['name']} : il n'est pas affecté au namespace de l'emplacement")


def check(storage: Storage, installation: dict) -> None:
    check_reference(storage.slots, installation["slot_id"], "Emplacement")
    check_reference(storage.module_versions, installation["module_version_id"], "Version de module")
    slot = storage.slots.read_existing(installation["slot_id"])
    namespace = storage.namespaces.read_existing(slot["namespace_id"])
    if storage.module_versions.read_existing(installation["module_version_id"])["module_id"] != slot["module_id"]:
        module = storage.modules.read_existing(slot["module_id"])["code"]
        reject(f"L'emplacement {slot['release_name']} est réservé au module {module}")
    check_parameter(
        storage,
        installation["technical_parameter_id"],
        ParameterType.TECHNICAL,
        namespace["id"],
        slot["module_id"],
    )
    check_parameter(
        storage,
        installation["application_parameter_id"],
        ParameterType.APPLICATION,
        namespace["id"],
        slot["module_id"],
    )


@router.get("", response_model=list[Installation], summary="Lister les installations")
def list_all(storage: StorageDep, slot_id: int | None = None, module_version_id: int | None = None):
    criteria = {}
    if slot_id is not None:
        criteria["slot_id"] = slot_id
    if module_version_id is not None:
        criteria["module_version_id"] = module_version_id
    return sorted(storage.installations.list_all(**criteria), key=lambda i: (i["date"], i["id"]), reverse=True)


@router.get("/{installation_id}", response_model=Installation, responses=R404, summary="Lire une installation")
def read(installation_id: int, storage: StorageDep):
    return read_or_404(storage.installations, installation_id, OBJECT)


def add(storage: Storage, installation: dict) -> dict:
    """Vérifie et enregistre un nouvel élément (route POST, et import de la configuration)."""
    check(storage, installation)
    return apply_if_consistent(storage, lambda s: s.installations.add(installation))


@router.post(
    "",
    response_model=Installation,
    status_code=status.HTTP_201_CREATED,
    responses={**R409, **R422},
    summary="Enregistrer une installation",
)
def create(data: InstallationCreation, request: Request, response: Response, storage: StorageDep):
    installation = add(storage, data.model_dump())
    add_location(request, response, installation["id"])
    return installation


@router.delete(
    "/{installation_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={**R404, **R409},
    summary="Supprimer une installation",
    description="Pour corriger une erreur de saisie.",
)
def delete(installation_id: int, storage: StorageDep) -> None:
    read_or_404(storage.installations, installation_id, OBJECT)
    # L'emplacement revient à son installation précédente : elle doit rester compatible.
    apply_if_consistent(storage, lambda s: s.installations.delete(installation_id))
