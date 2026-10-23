"""Règles de cohérence d'ensemble : ce qui doit rester vrai quoi qu'on saisisse.

Règles vérifiées :
  0. Le module d'un emplacement appartient à l'application du namespace de l'emplacement.
  1. Un namespace est sur un cluster du même type (prod ou hors prod) que son environnement.
  2. En prod, seules des versions RELEASE tournent (pas de SNAPSHOT).
  3. Dans chaque environnement, chaque version qui tourne trouve les modules dont son module
     dépend : présents, et dans une version compatible si une condition de version est
     déclarée. Le module requis peut tourner dans n'importe quel namespace de l'environnement
     (un module métier et la capacité du socle dont il dépend n'ont pas le même code appli).

« Ce qui tourne » sur un emplacement = sa dernière installation (date la plus récente).

Toute saisie qui casserait une règle est refusée (409). Pour le savoir sans risque, on fait
un essai (apply_if_consistent) :
  1. la saisie est faite ;
  2. les règles sont vérifiées ;
  3. si une règle est cassée, la saisie est annulée et rien n'est modifié.
En mémoire, l'essai se fait sur une copie des données ; dans SQLite, dans un point de
sauvegarde de la transaction (app/storage.py, Storage.attempt).

Import de la configuration (app/import_configuration.py) : le fichier est jugé en entier, pas
ligne par ligne, car une ligne peut avoir besoin d'une ligne plus bas (par exemple une dépendance
déclarée avant l'installation du module requis). Dans le bloc « with deferred_consistency() »,
apply_if_consistent fait donc le changement sans vérifier, et l'import vérifie tout à la fin
(incoherences).

"""

from collections.abc import Callable, Generator
from contextlib import contextmanager
from contextvars import ContextVar

from fastapi import HTTPException, status

from app.schemas import VersionType
from app.storage import Storage
from app.versions import describe, satisfied


def versions_in_service(storage: Storage) -> dict[int, list[dict]]:
    """Par environnement : les versions de module qui tournent (une par emplacement occupé)."""
    last: dict[int, dict] = {}  # slot_id → sa dernière installation
    for installation in storage.installations.list_all():
        current = last.get(installation["slot_id"])
        if current is None or (installation["date"], installation["id"]) > (current["date"], current["id"]):
            last[installation["slot_id"]] = installation

    by_environment: dict[int, list[dict]] = {}
    for slot_id, installation in last.items():
        namespace = storage.namespaces.read_existing(storage.slots.read_existing(slot_id)["namespace_id"])
        version = storage.module_versions.read_existing(installation["module_version_id"])
        by_environment.setdefault(namespace["environment_id"], []).append(version)
    return by_environment


def inconsistencies(storage: Storage) -> list[str]:
    """Liste, en français, tout ce qui ne respecte pas les règles (une fonction par règle, ci-dessous)."""
    problems = _slots_outside_application(storage) + _clusters_of_wrong_type(storage)
    for environment_id, versions in versions_in_service(storage).items():
        environment = storage.environments.read_existing(environment_id)
        for version in versions:
            problems += _snapshot_in_prod(storage, environment, version)
            problems += _required_modules(storage, environment, version, versions)
    return problems


def _slots_outside_application(storage: Storage) -> list[str]:
    """Règle 0 : module de l'emplacement = même application que le namespace."""
    problems = []
    for slot in storage.slots.list_all():
        namespace = storage.namespaces.read_existing(slot["namespace_id"])
        module = storage.modules.read_existing(slot["module_id"])
        if module["application_id"] != namespace["application_id"]:
            problems.append(
                f"l'emplacement {slot['release_name']} est réservé au module {module['code']}, "
                "qui n'appartient pas à l'application de son namespace"
            )
    return problems


def _clusters_of_wrong_type(storage: Storage) -> list[str]:
    """Règle 1 : type du cluster = type de l'environnement."""
    problems = []
    for namespace in storage.namespaces.list_all():
        environment = storage.environments.read_existing(namespace["environment_id"])
        cluster = storage.clusters.read_existing(namespace["cluster_id"])
        if cluster["is_prod"] != environment["is_prod"]:
            problems.append(
                f"l'environnement {environment['code']} et le cluster {cluster['code']} "
                "ne sont pas du même type (prod / hors prod)"
            )
    return problems


def _snapshot_in_prod(storage: Storage, environment: dict, version: dict) -> list[str]:
    """Règle 2 : pas de snapshot en prod."""
    if not (environment["is_prod"] and version["type"] == VersionType.SNAPSHOT):
        return []
    module = storage.modules.read_existing(version["module_id"])["code"]
    return [f"{module} {version['number']} est un snapshot : interdit en prod ({environment['code']})"]


def _required_modules(storage: Storage, environment: dict, version: dict, versions: list[dict]) -> list[str]:
    """Règle 3 : les modules requis par cette version sont présents dans l'environnement, en version compatible.

    `versions` : toutes les versions qui tournent dans l'environnement.
    """
    problems = []
    module = storage.modules.read_existing(version["module_id"])["code"]
    for dependency in storage.dependencies.list_all(module_id=version["module_id"]):
        required_id = dependency["depends_on_id"]
        required = storage.modules.read_existing(required_id)["code"]
        need = storage.compatibilities.find(module_version_id=version["id"], required_module_id=required_id)
        condition = "" if need is None else " " + describe(need["condition"], need["version"], need["version_max"])
        present = [v["number"] for v in versions if v["module_id"] == required_id]
        if not present:
            problems.append(
                f"{module} {version['number']} a besoin de {required}{condition}, "
                f"qui n'est pas installé en {environment['code']}"
            )
        if need is None:
            continue
        problems += [
            f"{module} {version['number']} a besoin de {required}{condition}, "
            f"mais {required} {number} tourne en {environment['code']}"
            for number in present
            if not satisfied(number, need["condition"], need["version"], need["version_max"])
        ]
    return problems


# Vrai dans le bloc « with deferred_consistency() » (import de la configuration).
_DEFERRED: ContextVar[bool] = ContextVar("deferred_consistency", default=False)


@contextmanager
def deferred_consistency() -> Generator[None]:
    """Bloc « with » : les règles d'ensemble ne sont plus vérifiées à chaque changement ; c'est à
    l'appelant d'appeler inconsistencies() à la fin (import de la configuration)."""
    token = _DEFERRED.set(True)
    try:
        yield
    finally:
        _DEFERRED.reset(token)


def apply_if_consistent[T](storage: Storage, change: Callable[[Storage], T]) -> T:
    """Fait le changement à l'essai ; s'il casse une règle : 409 et tout est annulé, sinon il est gardé.
    Dans deferred_consistency() : fait le changement, sans vérifier (vérifié plus tard par l'appelant)."""
    if _DEFERRED.get():
        return change(storage)
    with storage.attempt() as attempt:
        result = change(attempt)
        problems = inconsistencies(attempt)
        if problems:  # l'exception sort du bloc « with » : l'essai est annulé
            raise HTTPException(status.HTTP_409_CONFLICT, "Données incohérentes : " + " ; ".join(problems))
    return result
