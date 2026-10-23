"""Stockage dans une base SQLite : les mêmes opérations que le stockage en mémoire (app/storage.py),
traduites en SQL.

SQLite est une base de données rangée dans UN SEUL FICHIER (APP_DB_FILE), lue et écrite
directement par l'API : pas de serveur de base à installer ni à lancer. Le module sqlite3 est
livré avec Python.

Structure de la base (tables, colonnes, contrôles) : décrite dans les fichiers app/sql/NNN-….sql,
appliqués par l'API elle-même au démarrage (open), dans l'ordre, s'ils ne le sont pas déjà. La
base retient le numéro du dernier appliqué (PRAGMA user_version).

Une seule connexion, partagée par toutes les requêtes, et UNE REQUÊTE À LA FOIS : chaque requête
prend un verrou au début de sa transaction et le rend à la fin. C'est simple et sûr (le contrôle
de cohérence, app/consistency.py, voit toujours des données à jour), et largement assez rapide
pour une équipe. Conséquence : un seul exemplaire de l'API à la fois sur un même fichier.

Transactions : une par requête HTTP (app/transactions.py), enregistrée juste avant d'envoyer
la réponse, annulée en cas d'erreur imprévue. La transaction de la requête en cours est rangée
dans SESSION, une « variable de contexte » propre à chaque requête : les tables la retrouvent
sans qu'on ait à la passer de fonction en fonction.

Essai (consistency.py) : un « point de sauvegarde » (savepoint) dans la transaction ; si la
saisie rend les données incohérentes, on revient à ce point, et rien n'a été modifié.
"""

import itertools
import json
import logging
import sqlite3
import threading
from collections.abc import Generator
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import UTC, date, datetime
from enum import Enum
from pathlib import Path
from typing import Any

from app.settings import DatabaseSettings
from app.storage import TABLE_NAMES, Storage, StorageUnavailable, Table

logger = logging.getLogger(__name__)

# Les fichiers de structure, appliqués dans l'ordre de leur numéro (001-tables.sql…).
STRUCTURE = Path(__file__).resolve().parent / "sql"

# Temps d'attente maximal du verrou « une requête à la fois », en secondes.
WAIT_SECONDS = 30

# Champs « liste » rangés dans une table de liaison : champ → (table, colonne du propriétaire, colonne de la valeur).
LISTS = {
    "parameters": {"namespace_ids": ("parameter_namespaces", "parameter_id", "namespace_id")},
}

# Champs à convertir à la lecture : SQLite range les booléens en 0 / 1, les dates et le JSON en texte.
BOOLEANS = {"is_prod"}
DATES = {"date"}
JSONS = {"before", "after"}


class Session:
    """La transaction d'une requête : elle tient le verrou « une requête à la fois » jusqu'à sa fin."""

    def __init__(self, storage: SqliteStorage) -> None:
        if not storage.lock.acquire(timeout=WAIT_SECONDS):
            raise StorageUnavailable(f"Base SQLite occupée depuis plus de {WAIT_SECONDS} s")
        self._storage = storage
        self.connection: sqlite3.Connection | None = storage.connection
        self.failed = False  # une erreur SQL est survenue : la transaction ne peut plus qu'être annulée
        self._savepoints = itertools.count(1)
        try:
            self.connection.execute("begin")
        except BaseException:
            storage.lock.release()
            raise

    def savepoint(self) -> str:
        """Un nom de point de sauvegarde, unique dans la transaction (les essais peuvent s'imbriquer)."""
        return f"attempt_{next(self._savepoints)}"

    def commit(self) -> None:
        self.close(commit=True)

    def rollback(self) -> None:
        self.close(commit=False)

    def close(self, commit: bool) -> None:
        """Enregistre (commit=True) ou annule la transaction, puis rend le verrou.
        Sans effet si c'est déjà fait."""
        connection, self.connection = self.connection, None
        if connection is None:
            return
        try:
            connection.execute("commit" if commit and not self.failed else "rollback")
        finally:
            self._storage.lock.release()


# La session de la requête en cours (None hors requête).
SESSION: ContextVar[Session | None] = ContextVar("session", default=None)


def _value(value: Any) -> Any:
    """Valeur prête pour SQLite : une énumération (SNAPSHOT…) en texte, un booléen en 0 / 1,
    une date en texte ISO 8601 (UTC), un dictionnaire (avant / après du journal) en JSON."""
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, datetime):
        return (value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)).isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return json.dumps(value, ensure_ascii=False) if isinstance(value, dict | list) else value


def _read(row: sqlite3.Row) -> dict:
    """Une ligne lue dans SQLite, avec ses valeurs remises dans leur type (booléen, date, JSON)."""
    result = dict(row)
    for field, value in result.items():
        if value is None:
            continue
        if field in BOOLEANS:
            result[field] = bool(value)
        elif field in DATES:
            result[field] = datetime.fromisoformat(value)
        elif field in JSONS:
            result[field] = json.loads(value)
    return result


class SqliteTable(Table):
    """Une table de la base : chaque opération est une requête SQL."""

    def __init__(self, name: str, storage: SqliteStorage) -> None:
        self._name = name
        self._storage = storage
        self._lists = LISTS.get(name, {})

    def _execute(self, request: str, parameters: tuple | list = ()) -> list[sqlite3.Row]:
        """Exécute la requête dans la transaction en cours (ou dans une transaction rien que pour elle)."""
        session = SESSION.get()
        if session is None or session.connection is None:
            with self._storage.transaction():
                return self._execute(request, parameters)
        try:
            return session.connection.execute(request, parameters).fetchall()
        except sqlite3.Error:
            session.failed = True
            raise

    def _with_lists(self, rows: list[sqlite3.Row]) -> list[dict]:
        """Les lignes lues, avec leurs champs « liste » lus dans leur table de liaison."""
        result = [_read(row) for row in rows]
        for field, (link, owner, value) in self._lists.items():
            values: dict[int, list[int]] = {row["id"]: [] for row in result}
            if values:
                marks = ", ".join("?" * len(values))
                for link_row in self._execute(
                    f'select "{owner}", "{value}" from "{link}" where "{owner}" in ({marks}) order by position',
                    list(values),
                ):
                    values[link_row[0]].append(link_row[1])
            for row in result:
                row[field] = values[row["id"]]
        return result

    def list_all(self, **criteria) -> list[dict]:
        # « is » : comme « = », mais vrai aussi quand les deux valent null.
        conditions = " and ".join(f'"{field}" is ?' for field in criteria) or "1"
        request = f'select * from "{self._name}" where {conditions} order by id'
        return self._with_lists(self._execute(request, [_value(v) for v in criteria.values()]))

    def read(self, id_: int) -> dict | None:
        rows = self._with_lists(self._execute(f'select * from "{self._name}" where id = ?', (id_,)))
        return rows[0] if rows else None

    def add(self, data: dict) -> dict:
        columns, lists = self._split(data)
        if columns:
            names = ", ".join(f'"{c}"' for c in columns)
            marks = ", ".join("?" * len(columns))
            request = f'insert into "{self._name}" ({names}) values ({marks}) returning id'
        else:
            request = f'insert into "{self._name}" default values returning id'
        id_ = self._execute(request, [_value(v) for v in columns.values()])[0]["id"]
        self._write_lists(id_, lists)
        return self.read_existing(id_)

    def update(self, id_: int, changes: dict) -> dict:
        columns, lists = self._split(changes)
        if columns:
            assignments = ", ".join(f'"{c}" = ?' for c in columns)
            self._execute(
                f'update "{self._name}" set {assignments} where id = ?', [*map(_value, columns.values()), id_]
            )
        self._write_lists(id_, lists)
        return self.read_existing(id_)

    def delete(self, id_: int) -> None:
        # Les lignes des tables de liaison partent avec (« on delete cascade » dans la base).
        self._execute(f'delete from "{self._name}" where id = ?', (id_,))

    def _split(self, data: dict) -> tuple[dict, dict]:
        """Sépare les colonnes de la table et les champs « liste »."""
        columns = {k: v for k, v in data.items() if k not in self._lists and k != "id"}
        lists = {k: v for k, v in data.items() if k in self._lists}
        return columns, lists

    def _write_lists(self, id_: int, lists: dict) -> None:
        """Remplace le contenu des champs « liste » donnés (table de liaison : on efface, puis on réécrit)."""
        for field, values in lists.items():
            link, owner, value = self._lists[field]
            self._execute(f'delete from "{link}" where "{owner}" = ?', (id_,))
            for position, element in enumerate(values):
                self._execute(
                    f'insert into "{link}" ("{owner}", "{value}", position) values (?, ?, ?)', (id_, element, position)
                )


class SqliteStorage(Storage):
    """Les tables de l'application, dans un fichier SQLite."""

    def __init__(self, settings: DatabaseSettings) -> None:
        # Le fichier n'est pas ouvert ici, mais par open() : créer l'objet ne touche à rien.
        self._file = settings.file
        self.lock = threading.Lock()  # une requête à la fois (voir Session)
        self._connection: sqlite3.Connection | None = None
        super().__init__()

    @property
    def connection(self) -> sqlite3.Connection:
        if self._connection is None:
            raise StorageUnavailable(f"Base SQLite {self._file} pas encore ouverte")
        return self._connection

    def _table(self, name: str) -> Table:
        return SqliteTable(name, self)

    def open(self) -> None:
        """Ouvre le fichier (créé s'il n'existe pas), puis applique la structure qui manque."""
        try:
            self._file.parent.mkdir(parents=True, exist_ok=True)
            # autocommit=True : aucune transaction implicite, on les ouvre et ferme nous-mêmes (begin, commit).
            # check_same_thread=False : les requêtes s'exécutent dans plusieurs fils, une à la fois (verrou).
            connection = sqlite3.connect(self._file, autocommit=True, check_same_thread=False)
            connection.row_factory = sqlite3.Row
            connection.execute("pragma foreign_keys = on")  # liens vérifiés (désactivés par défaut dans SQLite)
            connection.execute("pragma journal_mode = wal")  # écritures sûres, même en cas d'arrêt brutal
            connection.execute("pragma busy_timeout = 5000")
        except (OSError, sqlite3.Error) as error:
            raise StorageUnavailable(f"Base SQLite {self._file} impossible à ouvrir : {error}") from error
        self._connection = connection
        self._apply_structure()
        logger.info("Base SQLite ouverte : %s", self._file)

    def _apply_structure(self) -> None:
        """Applique, dans l'ordre, les fichiers app/sql/NNN-….sql que la base n'a pas encore."""
        connection = self.connection
        applied = connection.execute("pragma user_version").fetchone()[0]
        files = sorted(STRUCTURE.glob("[0-9][0-9][0-9]-*.sql"))
        latest = int(files[-1].name[:3]) if files else 0
        if applied > latest:
            raise StorageUnavailable(
                f"La base {self._file} a la structure n° {applied}, plus récente que celle de cette version de "
                f"l'API (n° {latest}) : installer une version plus récente de l'API"
            )
        for file in files:
            number = int(file.name[:3])
            if number <= applied:
                continue
            with self.lock:
                connection.execute("begin")
                try:
                    connection.executescript(file.read_text(encoding="utf-8"))
                    connection.execute(f"pragma user_version = {number}")
                    connection.execute("commit")
                except BaseException:
                    connection.execute("rollback")
                    raise
            logger.info("Structure de la base : %s appliqué", file.name)
        present = {row[0] for row in connection.execute("select name from sqlite_master where type = 'table'")}
        missing = [name for name in TABLE_NAMES if name not in present]
        if missing:
            raise StorageUnavailable(f"La base {self._file} n'a pas les tables {', '.join(missing)}")

    def open_session(self, write: bool = True) -> Session:
        """Une nouvelle transaction (app/transactions.py ouvre la sienne à chaque requête).
        write : sans effet ici (une requête à la fois, qu'elle lise ou écrive)."""
        return Session(self)

    @contextmanager
    def transaction(self, write: bool = True) -> Generator[None]:
        in_progress = SESSION.get()
        if in_progress is not None and in_progress.connection is not None:
            yield  # déjà dans une transaction : on la continue
            return
        session = self.open_session(write)
        token = SESSION.set(session)
        try:
            yield
        except BaseException:
            session.close(commit=False)
            raise
        else:
            session.close(commit=True)
        finally:
            SESSION.reset(token)

    @contextmanager
    def attempt(self) -> Generator[Storage]:
        with self.transaction(write=True):
            session = SESSION.get()
            assert session is not None and session.connection is not None
            # Point de sauvegarde : annulé seul si une erreur sort du bloc.
            name = session.savepoint()
            failed = session.failed
            session.connection.execute(f"savepoint {name}")
            try:
                yield self
            except BaseException:
                session.connection.execute(f"rollback to {name}")
                session.connection.execute(f"release {name}")
                session.failed = failed  # l'erreur SQL de l'essai est effacée avec lui
                raise
            else:
                session.connection.execute(f"release {name}")

    def check(self) -> None:
        try:
            with self.transaction(write=False):
                self.connection.execute("select 1")
        except sqlite3.Error as error:
            raise StorageUnavailable(f"Base SQLite inaccessible : {error}") from error

    def close(self) -> None:
        if self._connection is not None:
            self._connection.close()
            self._connection = None
