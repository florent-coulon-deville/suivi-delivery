"""Routes /api/network-zones : la liste des zones réseau (interne, partenaires…), gérée dans l'outil.

Chaque namespace est dans une zone de cette liste. Le code est gardé en minuscules (comme tous
les codes) ; l'interface l'affiche en majuscules. Le libellé est libre.

  GET    /api/network-zones        200  liste, triée par code
  GET    /api/network-zones/{id}   200  | 404
  POST   /api/network-zones        201  + Location | 409 code déjà utilisé | 422
  PATCH  /api/network-zones/{id}   200  | 404 | 409 | 422
  PUT    /api/network-zones/{id}   200  remplace tout | 404 | 409 | 422
  DELETE /api/network-zones/{id}   204  | 404 | 409 utilisée par un namespace
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
from app.schemas import NetworkZone, NetworkZoneCreation, NetworkZoneUpdate
from app.storage import Storage

router = APIRouter(prefix="/network-zones", tags=["Zones réseau"])
OBJECT = "Zone réseau"


@router.get("", response_model=list[NetworkZone], summary="Lister les zones réseau")
def list_all(storage: StorageDep):
    return sorted(storage.network_zones.list_all(), key=lambda z: z["code"])


@router.get("/{zone_id}", response_model=NetworkZone, responses=R404, summary="Lire une zone réseau")
def read(zone_id: int, storage: StorageDep):
    return read_or_404(storage.network_zones, zone_id, OBJECT)


def add(storage: Storage, zone: dict) -> dict:
    """Vérifie et enregistre un nouvel élément (route POST, et import de la configuration)."""
    code = zone["code"]
    check_unique(storage.network_zones, f"Le code {code} est déjà utilisé", code=code)
    return storage.network_zones.add(zone)


@router.post(
    "", response_model=NetworkZone, status_code=status.HTTP_201_CREATED, responses=R409, summary="Créer une zone réseau"
)
def create(data: NetworkZoneCreation, request: Request, response: Response, storage: StorageDep):
    zone = add(storage, data.model_dump())
    add_location(request, response, zone["id"])
    return zone


def save(storage: Storage, zone_id: int, changes: dict):
    """Enregistre une modification : les champs envoyés (PATCH) ou tous les champs (PUT)."""
    read_or_404(storage.network_zones, zone_id, OBJECT)
    if "code" in changes:
        check_unique(
            storage.network_zones,
            f"Le code {changes['code']} est déjà utilisé",
            excluding_id=zone_id,
            code=changes["code"],
        )
    return storage.network_zones.update(zone_id, changes)


@router.patch(
    "/{zone_id}",
    response_model=NetworkZone,
    responses={**R404, **R409},
    summary="Modifier une zone réseau",
    description="Seuls les champs envoyés sont modifiés.",
)
def update(zone_id: int, data: NetworkZoneUpdate, storage: StorageDep):
    # Uniquement les champs envoyés.
    return save(storage, zone_id, data.model_dump(exclude_unset=True))


@router.put(
    "/{zone_id}",
    response_model=NetworkZone,
    responses={**R404, **R409, **R422},
    summary="Remplacer une zone réseau",
    description=REPLACEMENT,
)
def replace(zone_id: int, data: NetworkZoneCreation, storage: StorageDep):
    return save(storage, zone_id, data.model_dump())  # tous les champs


@router.delete(
    "/{zone_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={**R404, **R409},
    summary="Supprimer une zone réseau",
)
def delete(zone_id: int, storage: StorageDep) -> None:
    read_or_404(storage.network_zones, zone_id, OBJECT)
    check_unused(storage.namespaces, "Zone réseau utilisée par au moins un namespace", network_zone_id=zone_id)
    storage.network_zones.delete(zone_id)
