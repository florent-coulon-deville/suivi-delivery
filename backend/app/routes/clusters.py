"""Routes /api/clusters : la liste des clusters OpenShift (cb01, cb02…).

Un cluster est de prod ou de hors prod (is_prod). Un namespace va sur un cluster du même
type que son environnement. Changer is_prod est refusé (409) si cela crée un mélange.

  GET    /api/clusters        200  liste, triée par code
  GET    /api/clusters/{id}   200  | 404
  POST   /api/clusters        201  + Location | 409 code déjà utilisé | 422
  PATCH  /api/clusters/{id}   200  | 404 | 409 | 422
  PUT    /api/clusters/{id}   200  remplace tout | 404 | 409 | 422
  DELETE /api/clusters/{id}   204  | 404 | 409 utilisé par un namespace
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
from app.schemas import Cluster, ClusterCreation, ClusterUpdate
from app.storage import Storage

router = APIRouter(prefix="/clusters", tags=["Clusters"])
OBJECT = "Cluster"


@router.get("", response_model=list[Cluster], summary="Lister les clusters")
def list_all(storage: StorageDep):
    return sorted(storage.clusters.list_all(), key=lambda c: c["code"])


@router.get("/{cluster_id}", response_model=Cluster, responses=R404, summary="Lire un cluster")
def read(cluster_id: int, storage: StorageDep):
    return read_or_404(storage.clusters, cluster_id, OBJECT)


def add(storage: Storage, cluster: dict) -> dict:
    """Vérifie et enregistre un nouvel élément (route POST, et import de la configuration)."""
    code = cluster["code"]
    check_unique(storage.clusters, f"Le code {code} est déjà utilisé", code=code)
    return storage.clusters.add(cluster)


@router.post(
    "", response_model=Cluster, status_code=status.HTTP_201_CREATED, responses=R409, summary="Créer un cluster"
)
def create(data: ClusterCreation, request: Request, response: Response, storage: StorageDep):
    cluster = add(storage, data.model_dump())
    add_location(request, response, cluster["id"])
    return cluster


def save(storage: Storage, cluster_id: int, changes: dict):
    """Enregistre une modification : les champs envoyés (PATCH) ou tous les champs (PUT)."""
    read_or_404(storage.clusters, cluster_id, OBJECT)
    if "code" in changes:
        check_unique(
            storage.clusters,
            f"Le code {changes['code']} est déjà utilisé",
            excluding_id=cluster_id,
            code=changes["code"],
        )
    return apply_if_consistent(storage, lambda s: s.clusters.update(cluster_id, changes))


@router.patch(
    "/{cluster_id}",
    response_model=Cluster,
    responses={**R404, **R409},
    summary="Modifier un cluster",
    description="Seuls les champs envoyés sont modifiés.",
)
def update(cluster_id: int, data: ClusterUpdate, storage: StorageDep):
    # Uniquement les champs envoyés.
    return save(storage, cluster_id, data.model_dump(exclude_unset=True))


@router.put(
    "/{cluster_id}",
    response_model=Cluster,
    responses={**R404, **R409, **R422},
    summary="Remplacer un cluster",
    description=REPLACEMENT,
)
def replace(cluster_id: int, data: ClusterCreation, storage: StorageDep):
    return save(storage, cluster_id, data.model_dump())  # tous les champs


@router.delete(
    "/{cluster_id}", status_code=status.HTTP_204_NO_CONTENT, responses={**R404, **R409}, summary="Supprimer un cluster"
)
def delete(cluster_id: int, storage: StorageDep) -> None:
    read_or_404(storage.clusters, cluster_id, OBJECT)
    check_unused(storage.namespaces, "Cluster utilisé par au moins un namespace", cluster_id=cluster_id)
    storage.clusters.delete(cluster_id)
