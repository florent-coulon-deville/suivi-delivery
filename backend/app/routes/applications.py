"""Routes /api/applications.

Une application est identifiée par son « identifiant », unique. Son trigramme
(3 caractères) peut être partagé par plusieurs applications.

  GET    /api/applications        200  liste, triée par identifiant
  GET    /api/applications/{id}   200  | 404
  POST   /api/applications        201  + Location | 409 identifiant déjà utilisé | 422
  PATCH  /api/applications/{id}   200  | 404 | 409 | 422
  PUT    /api/applications/{id}   200  remplace tout | 404 | 409 | 422
  DELETE /api/applications/{id}   204  | 404 | 409 encore liée à un namespace ou à un module
"""

from fastapi import APIRouter, Request, Response, status

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
from app.schemas import Application, ApplicationCreation, ApplicationUpdate
from app.storage import Storage

router = APIRouter(prefix="/applications", tags=["Applications"])
OBJECT = "Application"


@router.get("", response_model=list[Application], summary="Lister les applications")
def list_all(storage: StorageDep):
    return sorted(storage.applications.list_all(), key=lambda a: a["identifier"])


@router.get("/{application_id}", response_model=Application, responses=R404, summary="Lire une application")
def read(application_id: int, storage: StorageDep):
    return read_or_404(storage.applications, application_id, OBJECT)


def add(storage: Storage, application: dict) -> dict:
    """Vérifie et enregistre un nouvel élément (route POST, et import de la configuration)."""
    identifier = application["identifier"]
    check_unique(storage.applications, f"L'identifiant {identifier} est déjà utilisé", identifier=identifier)
    return storage.applications.add(application)


@router.post(
    "", response_model=Application, status_code=status.HTTP_201_CREATED, responses=R409, summary="Créer une application"
)
def create(data: ApplicationCreation, request: Request, response: Response, storage: StorageDep):
    application = add(storage, data.model_dump())
    add_location(request, response, application["id"])
    return application


def save(storage: Storage, application_id: int, changes: dict):
    """Enregistre une modification : les champs envoyés (PATCH) ou tous les champs (PUT)."""
    read_or_404(storage.applications, application_id, OBJECT)
    if "identifier" in changes:
        check_unique(
            storage.applications,
            f"L'identifiant {changes['identifier']} est déjà utilisé",
            excluding_id=application_id,
            identifier=changes["identifier"],
        )
    return storage.applications.update(application_id, changes)


@router.patch(
    "/{application_id}",
    response_model=Application,
    responses={**R404, **R409},
    summary="Modifier une application",
    description="Seuls les champs envoyés sont modifiés.",
)
def update(application_id: int, data: ApplicationUpdate, storage: StorageDep):
    # Uniquement les champs envoyés.
    return save(storage, application_id, data.model_dump(exclude_unset=True))


@router.put(
    "/{application_id}",
    response_model=Application,
    responses={**R404, **R409, **R422},
    summary="Remplacer une application",
    description=REPLACEMENT,
)
def replace(application_id: int, data: ApplicationCreation, storage: StorageDep):
    return save(storage, application_id, data.model_dump())  # tous les champs


@router.delete(
    "/{application_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={**R404, **R409},
    summary="Supprimer une application",
)
def delete(application_id: int, storage: StorageDep) -> None:
    read_or_404(storage.applications, application_id, OBJECT)
    check_unused(storage.namespaces, "Application liée à au moins un namespace", application_id=application_id)
    check_unused(storage.modules, "Application liée à au moins un module", application_id=application_id)
    storage.applications.delete(application_id)
