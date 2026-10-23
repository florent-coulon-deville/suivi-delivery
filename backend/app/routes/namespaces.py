"""Routes /api/namespaces.

Un namespace OpenShift appartient à une application, dans un environnement et sur un cluster.
Son nom n'est pas saisi, il est calculé : trigramme-identifiant-environnement-suffixe.
  Ex. : application abc / paiement, environnement int, suffixe « batch » → abc-paiement-int-batch
Environnement + suffixe + cluster est unique au sein de l'application : un même nom peut exister
une fois par cluster (ex. abc-paiement-int-batch sur cb01 et sur cb02), jamais deux fois sur le même.
Le cluster doit être du même type (prod ou hors prod) que l'environnement (422). La zone réseau
est choisie dans la liste des zones (/api/network-zones ; 422 si elle n'existe pas).

  GET    /api/namespaces                    200  liste, triée par nom
  GET    /api/namespaces?application_id=3   200  uniquement les namespaces de l'application 3
  GET    /api/namespaces/{id}               200  | 404
  POST   /api/namespaces                    201  + Location | 409 déjà existant | 422 (référence inexistante…)
  POST   /api/namespaces/batch                201  le même namespace sur plusieurs clusters, avec un emplacement
                                                 par module de l'application ; tout ou rien | 409 | 422
  PATCH  /api/namespaces/{id}               200  | 404 | 409 | 422
  PUT    /api/namespaces/{id}               200  remplace tout | 404 | 409 | 422
  DELETE /api/namespaces/{id}               204  | 404 | 409 a des emplacements ou des paramètres affectés
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
from app.routes import slots as slot_routes
from app.schemas import Namespace, NamespaceBatch, NamespaceBatchCreation, NamespaceCreation, NamespaceUpdate
from app.storage import Storage

router = APIRouter(prefix="/namespaces", tags=["Namespaces"])
OBJECT = "Namespace"


def with_name(storage: Storage, namespace: dict) -> dict:
    """Ajoute le nom calculé à partir de l'application, de l'environnement et du suffixe.

    Calculé à chaque lecture : si l'identifiant d'une application change, le nom suit.
    """
    application = storage.applications.read_existing(namespace["application_id"])
    environment = storage.environments.read_existing(namespace["environment_id"])
    parts = [application["trigram"], application["identifier"], environment["code"], namespace["suffix"]]
    return {**namespace, "name": "-".join(parts)}


def check(storage: Storage, namespace: dict, excluding_id: int | None = None) -> None:
    """Vérifications communes à la création et à la modification (namespace complet)."""
    check_reference(storage.applications, namespace["application_id"], "Application")
    check_reference(storage.environments, namespace["environment_id"], "Environnement")
    check_reference(storage.clusters, namespace["cluster_id"], "Cluster")
    check_reference(storage.network_zones, namespace["network_zone_id"], "Zone réseau")
    environment = storage.environments.read_existing(namespace["environment_id"])
    if storage.clusters.read_existing(namespace["cluster_id"])["is_prod"] != environment["is_prod"]:
        expected_type = "de prod" if environment["is_prod"] else "de hors prod"
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            f"L'environnement {environment['code']} demande un cluster {expected_type}",
        )
    cluster = storage.clusters.read_existing(namespace["cluster_id"])
    check_unique(
        storage.namespaces,
        f"Cette application a déjà un namespace avec cet environnement et ce suffixe sur le cluster {cluster['code']}",
        excluding_id=excluding_id,
        application_id=namespace["application_id"],
        environment_id=namespace["environment_id"],
        cluster_id=namespace["cluster_id"],
        suffix=namespace["suffix"],
    )


@router.get("", response_model=list[Namespace], summary="Lister les namespaces")
def list_all(storage: StorageDep, application_id: int | None = None):
    criteria = {} if application_id is None else {"application_id": application_id}
    namespaces = [with_name(storage, n) for n in storage.namespaces.list_all(**criteria)]
    return sorted(namespaces, key=lambda n: n["name"])


@router.get("/{namespace_id}", response_model=Namespace, responses=R404, summary="Lire un namespace")
def read(namespace_id: int, storage: StorageDep):
    return with_name(storage, read_or_404(storage.namespaces, namespace_id, OBJECT))


def add(storage: Storage, namespace: dict) -> dict:
    """Vérifie et enregistre un nouvel élément (route POST, et import de la configuration)."""
    check(storage, namespace)
    return storage.namespaces.add(namespace)


@router.post(
    "",
    response_model=Namespace,
    status_code=status.HTTP_201_CREATED,
    responses={**R409, **R422},
    summary="Créer un namespace",
)
def create(data: NamespaceCreation, request: Request, response: Response, storage: StorageDep):
    namespace = add(storage, data.model_dump())
    add_location(request, response, namespace["id"])
    return with_name(storage, namespace)


def add_batch(storage: Storage, batch: dict) -> dict:
    """Crée le même namespace sur chaque cluster du lot et, si demandé, un emplacement par module
    de l'application dans chacun (nom de release = code du module, « _ » remplacé par « - »).

    Tout ou rien : le tout est fait dans un essai du stockage ; au premier refus (409, 422), l'erreur
    sort de l'essai et rien n'est enregistré. Le message du refus nomme le cluster en cause.
    """
    check_reference(storage.applications, batch["application_id"], "Application")
    modules = sorted(storage.modules.list_all(application_id=batch["application_id"]), key=lambda m: m["code"])
    common = {key: batch[key] for key in ("application_id", "environment_id", "suffix", "network_zone_id")}
    with storage.attempt() as attempt:
        namespaces, slots = [], []
        for cluster_id in batch["cluster_ids"]:
            namespace = add(attempt, {**common, "cluster_id": cluster_id})
            namespaces.append(with_name(attempt, namespace))
            if not batch["with_slots"]:
                continue
            for module in modules:
                slot = {
                    "namespace_id": namespace["id"],
                    "module_id": module["id"],
                    "release_name": module["code"].replace("_", "-"),
                }
                slots.append(slot_routes.add(attempt, slot))
    return {"namespaces": namespaces, "slots": slots}


@router.post(
    "/batch",
    response_model=NamespaceBatch,
    status_code=status.HTTP_201_CREATED,
    responses={**R409, **R422},
    summary="Créer un namespace sur plusieurs clusters, avec ses emplacements",
    description=(
        "Crée le même namespace sur chacun des clusters donnés et, sauf `with_slots: false`, "
        "un emplacement par module de l'application dans chacun (nom de release = code du module, "
        "« _ » remplacé par « - »). **Tout ou rien** : au moindre refus, rien n'est créé. "
        "Plusieurs éléments étant créés, pas d'en-tête `Location` : chacun a son `id` dans la réponse."
    ),
)
def create_batch(data: NamespaceBatchCreation, storage: StorageDep):
    return add_batch(storage, data.model_dump())


def save(storage: Storage, namespace_id: int, changes: dict):
    """Enregistre une modification : les champs envoyés (PATCH) ou tous les champs (PUT)."""
    current = read_or_404(storage.namespaces, namespace_id, OBJECT)
    check(storage, {**current, **changes}, excluding_id=namespace_id)  # le namespace tel qu'il serait après
    # Changer d'environnement déplace ce qui y tourne : refusé (409) si cela crée une incompatibilité.
    namespace = apply_if_consistent(storage, lambda s: s.namespaces.update(namespace_id, changes))
    return with_name(storage, namespace)


@router.patch(
    "/{namespace_id}",
    response_model=Namespace,
    responses={**R404, **R409, **R422},
    summary="Modifier un namespace",
    description="Seuls les champs envoyés sont modifiés.",
)
def update(namespace_id: int, data: NamespaceUpdate, storage: StorageDep):
    # Uniquement les champs envoyés.
    return save(storage, namespace_id, data.model_dump(exclude_unset=True))


@router.put(
    "/{namespace_id}",
    response_model=Namespace,
    responses={**R404, **R409, **R422},
    summary="Remplacer un namespace",
    description=REPLACEMENT,
)
def replace(namespace_id: int, data: NamespaceCreation, storage: StorageDep):
    return save(storage, namespace_id, data.model_dump())  # tous les champs


@router.delete(
    "/{namespace_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={**R404, **R409},
    summary="Supprimer un namespace",
)
def delete(namespace_id: int, storage: StorageDep) -> None:
    read_or_404(storage.namespaces, namespace_id, OBJECT)
    check_unused(storage.slots, "Namespace qui a encore des emplacements", namespace_id=namespace_id)
    if any(namespace_id in p["namespace_ids"] for p in storage.parameters.list_all()):
        raise HTTPException(status.HTTP_409_CONFLICT, "Namespace auquel des paramètres sont encore affectés")
    storage.namespaces.delete(namespace_id)
