"""Routes /api/dependencies : « le module A dépend du module B ».

Les dépendances traversent les applications : un module projet métier dépend
typiquement de modules capacité (socle) d'autres applications.

La dépendance porte sur le module. Les compatibilités (/api/compatibilities) précisent
ensuite avec quelles versions de B chaque version de A fonctionne.

  GET    /api/dependencies                   200  liste
  GET    /api/dependencies?module_id=3       200  ce dont le module 3 a besoin
  GET    /api/dependencies?depends_on_id=3    200  qui utilise le module 3
  GET    /api/dependencies/{id}              200  | 404
  POST   /api/dependencies                   201  + Location | 409 déjà existante, boucle, ou module requis
                                                  absent là où le module tourne | 422
  DELETE /api/dependencies/{id}              204  | 404 | 409 des compatibilités s'appuient dessus

Pas de modification (PATCH → 405) : on supprime le lien et on en crée un autre.
"""

from fastapi import APIRouter, HTTPException, Request, Response, status

from app.consistency import apply_if_consistent
from app.routes import (
    R404,
    R409,
    R422,
    StorageDep,
    add_location,
    check_reference,
    check_unique,
    read_or_404,
)
from app.schemas import Dependency, DependencyCreation
from app.storage import Storage

router = APIRouter(prefix="/dependencies", tags=["Dépendances"])
OBJECT = "Dépendance"


def needs(storage: Storage, module_id: int, searched_id: int) -> bool:
    """Vrai si module_id a besoin de searched_id, directement ou par l'intermédiaire d'autres modules."""
    to_see, seen = [module_id], set()
    while to_see:
        current = to_see.pop()
        if current == searched_id:
            return True
        if current not in seen:
            seen.add(current)
            to_see += [d["depends_on_id"] for d in storage.dependencies.list_all(module_id=current)]
    return False


@router.get("", response_model=list[Dependency], summary="Lister les dépendances")
def list_all(storage: StorageDep, module_id: int | None = None, depends_on_id: int | None = None):
    criteria = {}
    if module_id is not None:
        criteria["module_id"] = module_id
    if depends_on_id is not None:
        criteria["depends_on_id"] = depends_on_id
    return sorted(storage.dependencies.list_all(**criteria), key=lambda d: (d["module_id"], d["depends_on_id"]))


@router.get("/{dependency_id}", response_model=Dependency, responses=R404, summary="Lire une dépendance")
def read(dependency_id: int, storage: StorageDep):
    return read_or_404(storage.dependencies, dependency_id, OBJECT)


@router.post(
    "",
    response_model=Dependency,
    status_code=status.HTTP_201_CREATED,
    responses={**R409, **R422},
    summary="Déclarer une dépendance",
)
def create(data: DependencyCreation, request: Request, response: Response, storage: StorageDep):
    dependency = add(storage, data.model_dump())
    add_location(request, response, dependency["id"])
    return dependency


def add(storage: Storage, dependency: dict) -> dict:
    """Vérifie et enregistre un nouvel élément (route POST, et import de la configuration)."""
    check_reference(storage.modules, dependency["module_id"], "Module")
    check_reference(storage.modules, dependency["depends_on_id"], "Module")
    if dependency["module_id"] == dependency["depends_on_id"]:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Un module ne peut pas dépendre de lui-même")
    check_unique(storage.dependencies, "Cette dépendance existe déjà", **dependency)
    # Si B a déjà besoin de A, ajouter « A dépend de B » créerait une boucle.
    if needs(storage, dependency["depends_on_id"], dependency["module_id"]):
        raise HTTPException(status.HTTP_409_CONFLICT, "Cette dépendance créerait une boucle")
    # Le module requis doit tourner partout où le module tourne déjà.
    return apply_if_consistent(storage, lambda s: s.dependencies.add(dependency))


@router.delete(
    "/{dependency_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={**R404, **R409},
    summary="Supprimer une dépendance",
)
def delete(dependency_id: int, storage: StorageDep) -> None:
    dependency = read_or_404(storage.dependencies, dependency_id, OBJECT)
    versions = {v["id"] for v in storage.module_versions.list_all(module_id=dependency["module_id"])}
    if any(
        c["module_version_id"] in versions
        for c in storage.compatibilities.list_all(required_module_id=dependency["depends_on_id"])
    ):
        raise HTTPException(status.HTTP_409_CONFLICT, "Des compatibilités de version s'appuient sur cette dépendance")
    storage.dependencies.delete(dependency_id)
