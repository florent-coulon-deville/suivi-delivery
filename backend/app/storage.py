"""Stockage des données : ce que les routes utilisent pour lire et écrire.

Chaque type d'objet a sa « table » : des lignes rangées par identifiant (1, 2, 3…), où
chaque ligne est un dictionnaire de champs. Les liens entre objets se font par
identifiant : un module contient par exemple « application_id: 3 ».

Les routes ne voient que les opérations de Table (lister, lire, trouver, ajouter,
modifier, supprimer) et de Stockage. Deux façons de les réaliser :
  MemoryStorage   tout en mémoire, perdu à l'arrêt : tests, essais rapides sur un poste ;
  SqliteStorage   dans un fichier SQLite (app/storage_sqlite.py) : le vrai stockage.
La structure de la base est décrite dans app/sql/, appliquée par l'API au démarrage.

Trois notions communes :
  transaction  un ensemble de lectures et d'écritures qui réussit en entier, ou pas du tout.
               L'API en ouvre une par requête (app/transactions.py).
  essai        consistency.py fait la saisie « pour voir » : si elle rend les données
               incohérentes, elle est annulée et rien n'est modifié.
  journal      chaque saisie est notée automatiquement dans la table « journal » (TrackedTable,
               app/audit_log.py), dans la même transaction : refusée ou annulée, elle ne laisse rien.
"""

import copy
from abc import ABC, abstractmethod
from collections.abc import Generator
from contextlib import contextmanager

from app.audit_log import UNTRACKED_TABLES, audit_entry
from app.schemas import AuditAction

# Les tables de l'application, dans l'ordre des liens (une table ne dépend que des précédentes).
TABLE_NAMES = (
    # Listes gérées dans l'outil
    "environments",
    "clusters",
    "network_zones",
    # Commande des ressources
    "applications",
    "namespaces",
    "modules",
    "dependencies",
    # Déploiement
    "module_versions",
    "compatibilities",
    "parameters",
    "slots",
    "installations",
    # Journal des actions (app/audit_log.py)
    "audit_log",
)


class StorageUnavailable(Exception):
    """Le stockage ne répond pas (base arrêtée, réseau coupé…) : probe /readyz."""


class Table(ABC):
    """Une table : des lignes rangées par identifiant."""

    @abstractmethod
    def list_all(self, **criteria) -> list[dict]:
        """Toutes les lignes, ou celles dont les champs valent les critères. Ex. : list_all(application_id=3)."""

    @abstractmethod
    def read(self, id_: int) -> dict | None:
        """Renvoie la ligne, ou None si l'identifiant n'existe pas."""

    def read_existing(self, id_: int) -> dict:
        """Renvoie une ligne qui doit exister (déjà vérifiée par ailleurs) ; KeyError sinon."""
        row = self.read(id_)
        if row is None:
            raise KeyError(id_)
        return row

    def find(self, **criteria) -> dict | None:
        """Renvoie la première ligne dont les champs valent les critères, ou None."""
        rows = self.list_all(**criteria)
        return rows[0] if rows else None

    @abstractmethod
    def add(self, data: dict) -> dict:
        """Ajoute une ligne en lui attribuant un nouvel identifiant, et la renvoie."""

    @abstractmethod
    def update(self, id_: int, changes: dict) -> dict:
        """Met à jour les champs indiqués de la ligne (qui doit exister), et la renvoie."""

    @abstractmethod
    def delete(self, id_: int) -> None:
        """Supprime la ligne (qui doit exister)."""


class TrackedTable(Table):
    """Une table dont chaque saisie (ajout, modification, suppression) est notée au journal
    (app/audit_log.py), dans la même transaction. Les lectures passent directement."""

    def __init__(self, name: str, table: Table, audit_log: Table) -> None:
        self._name = name
        self._table = table
        self._audit_log = audit_log

    def list_all(self, **criteria) -> list[dict]:
        return self._table.list_all(**criteria)

    def read(self, id_: int) -> dict | None:
        return self._table.read(id_)

    def add(self, data: dict) -> dict:
        row = self._table.add(data)
        self._log(AuditAction.CREATE, row["id"], None, row)
        return row

    def update(self, id_: int, changes: dict) -> dict:
        before = self._table.read_existing(id_)
        after = self._table.update(id_, changes)
        self._log(AuditAction.UPDATE, id_, before, after)
        return after

    def delete(self, id_: int) -> None:
        before = self._table.read_existing(id_)
        self._table.delete(id_)
        self._log(AuditAction.DELETE, id_, before, None)

    def _log(self, action: AuditAction, id_: int, before: dict | None, after: dict | None) -> None:
        row = audit_entry(self._name, action, id_, before, after)
        if row is not None:
            self._audit_log.add(row)


class Storage(ABC):
    """Toutes les tables de l'application."""

    def __init__(self) -> None:
        # Le journal d'abord : les autres tables y notent leurs saisies (TrackedTable).
        self.audit_log = self._table("audit_log")
        # Listes gérées dans l'outil
        self.environments = self._track("environments")
        self.clusters = self._track("clusters")
        self.network_zones = self._track("network_zones")
        # Commande des ressources
        self.applications = self._track("applications")
        self.namespaces = self._track("namespaces")
        self.modules = self._track("modules")
        self.dependencies = self._track("dependencies")
        # Déploiement
        self.module_versions = self._track("module_versions")
        self.compatibilities = self._track("compatibilities")
        self.parameters = self._track("parameters")
        self.slots = self._track("slots")
        self.installations = self._track("installations")

    @abstractmethod
    def _table(self, name: str) -> Table:
        """Fabrique la table de ce nom."""

    def _track(self, name: str) -> Table:
        """La table de ce nom, avec ses saisies notées au journal (sauf tables techniques)."""
        table = self._table(name)
        return table if name in UNTRACKED_TABLES else TrackedTable(name, table, self.audit_log)

    @abstractmethod
    @contextmanager
    def transaction(self, write: bool = True) -> Generator[None]:
        """Tout ce qui est fait dans le bloc « with » est enregistré ensemble, ou annulé ensemble
        (si une erreur sort du bloc). SQLite : une requête à la fois (voir storage_sqlite.py)."""
        yield

    @abstractmethod
    @contextmanager
    def attempt(self) -> Generator[Storage]:
        """Bloc « with » : les changements faits sur le stockage renvoyé sont gardés si le bloc se
        termine normalement, et annulés si une erreur en sort (utilisé par consistency.py)."""
        yield self

    def check(self) -> None:
        """Vérifie que le stockage répond (probe /readyz) ; lève StorageUnavailable sinon.
        Par défaut (en mémoire) : il répond toujours."""
        return None

    def close(self) -> None:
        """Libère ce qui doit l'être, à l'arrêt de l'API. Par défaut (en mémoire) : rien."""
        return None


# --- En mémoire -----------------------------------------------------------------


class MemoryTable(Table):
    """Une table en mémoire : un dictionnaire { identifiant: ligne }."""

    def __init__(self) -> None:
        self._rows: dict[int, dict] = {}
        self._last_id = 0  # le dernier identifiant attribué : jamais réutilisé

    def list_all(self, **criteria) -> list[dict]:
        return [dict(row) for row in self._rows.values() if _matches(row, criteria)]

    def read(self, id_: int) -> dict | None:
        row = self._rows.get(id_)
        return dict(row) if row is not None else None

    def add(self, data: dict) -> dict:
        self._last_id += 1
        row = {"id": self._last_id, **data}
        self._rows[row["id"]] = row
        return dict(row)

    def update(self, id_: int, changes: dict) -> dict:
        self._rows[id_].update(changes)
        return dict(self._rows[id_])

    def delete(self, id_: int) -> None:
        del self._rows[id_]


def _matches(row: dict, criteria: dict) -> bool:
    return all(row.get(field) == value for field, value in criteria.items())


class MemoryStorage(Storage):
    """Tout en mémoire, perdu à l'arrêt de l'API (tests, essais rapides)."""

    def _table(self, name: str) -> Table:
        return MemoryTable()

    @contextmanager
    def transaction(self, write: bool = True) -> Generator[None]:
        # En mémoire, chaque écriture est immédiate : rien à valider ni à annuler.
        yield

    @contextmanager
    def attempt(self) -> Generator[Storage]:
        # L'essai se fait sur une copie ; si tout s'est bien passé, la copie devient les données.
        # Essai raté : l'erreur remonte depuis « yield », la copie est oubliée, les données ne changent pas.
        clone = copy.deepcopy(self)
        succeeded = False
        try:
            yield clone
            succeeded = True  # jamais atteint si une erreur sort du bloc « with »
        finally:
            if succeeded:  # un essai raté n'est pas recopié
                self.__dict__.update(clone.__dict__)
