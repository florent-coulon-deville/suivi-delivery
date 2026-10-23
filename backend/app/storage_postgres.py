"""Stockage dans PostgreSQL : les mêmes opérations que le stockage en mémoire (app/storage.py),
traduites en SQL.

La structure de la base (tables, colonnes, contrôles) n'est PAS créée ici : c'est le rôle de
Liquibase (module liquibase/ à la racine du projet), lancé avant l'API. Au démarrage, l'API vérifie seulement que
toutes ses tables sont là, et s'arrête avec un message clair sinon.

Connexions : psycopg_pool garde quelques connexions ouvertes (« pool ») et les prête aux
requêtes, ce qui évite d'en ouvrir une à chaque appel.

Transactions : une par requête HTTP (app/transactions.py), enregistrée juste avant d'envoyer
la réponse, annulée en cas d'erreur imprévue. La connexion de la requête en cours est rangée
dans SESSION, une « variable de contexte » propre à chaque requête : les tables la retrouvent
sans qu'on ait à la passer de fonction en fonction.

Une écriture à la fois : une requête qui modifie (POST, PUT, PATCH, DELETE) prend d'abord un
verrou de la base (« advisory lock »), rendu à la fin de sa transaction. Deux saisies ne
peuvent donc pas se croiser, même avec plusieurs exemplaires de l'API : le contrôle de
cohérence (app/consistency.py) voit toujours des données à jour. Les lectures ne sont pas bloquées.

Essai (consistency.py) : un « point de sauvegarde » (savepoint) dans la transaction ; si la
saisie rend les données incohérentes, on revient à ce point, et rien n'a été modifié.
"""

import logging
from collections.abc import Generator
from contextlib import contextmanager
from contextvars import ContextVar
from enum import Enum
from typing import Any

import psycopg
from psycopg import sql
from psycopg.pq import TransactionStatus
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from psycopg_pool import ConnectionPool, PoolTimeout

from app.settings import DatabaseSettings
from app.storage import TABLE_NAMES, Storage, StorageUnavailable, Table

logger = logging.getLogger(__name__)

# Numéro (au choix, fixe) du verrou « une écriture à la fois ».
WRITE_LOCK = 7_402_191

# Champs « liste » rangés dans une table de liaison : champ → (table, colonne du propriétaire, colonne de la valeur).
LISTS = {
    "parameters": {"namespace_ids": ("parameter_namespaces", "parameter_id", "namespace_id")},
}


class Session:
    """La connexion d'une requête, avec sa transaction en cours."""

    def __init__(self, pool: ConnectionPool, write: bool) -> None:
        self._pool = pool
        self.connection: psycopg.Connection | None = pool.getconn()
        if write:
            self.connection.execute("select pg_advisory_xact_lock(%s)", (WRITE_LOCK,))

    def commit(self) -> None:
        self.close(commit=True)

    def rollback(self) -> None:
        self.close(commit=False)

    def close(self, commit: bool) -> None:
        """Enregistre (commit=True) ou annule la transaction, puis rend la connexion au pool.
        Sans effet si c'est déjà fait."""
        connection, self.connection = self.connection, None
        if connection is None:
            return
        try:
            # Après une erreur SQL, la transaction ne peut plus qu'être annulée.
            if commit and connection.info.transaction_status != TransactionStatus.INERROR:
                connection.commit()
            else:
                connection.rollback()
        finally:
            self._pool.putconn(connection)


# La session de la requête en cours (None hors requête).
SESSION: ContextVar[Session | None] = ContextVar("session", default=None)


def _value(value: Any) -> Any:
    """Valeur prête pour PostgreSQL : une énumération (SNAPSHOT…) est envoyée sous forme de texte,
    un dictionnaire (avant / après du journal) en JSON (type jsonb)."""
    if isinstance(value, Enum):
        return value.value
    return Jsonb(value) if isinstance(value, dict) else value


class TablePostgres(Table):
    """Une table de la base : chaque opération est une requête SQL."""

    def __init__(self, name: str, storage: PostgresStorage) -> None:
        self._name = name
        self._storage = storage
        self._lists = LISTS.get(name, {})

    def _execute(self, request: sql.Composed, parameters: tuple | list = (), write: bool = False) -> list[dict]:
        """Exécute la requête dans la transaction en cours (ou dans une transaction rien que pour elle)."""
        session = SESSION.get()
        if session is None or session.connection is None:
            with self._storage.transaction(write=write):
                return self._execute(request, parameters, write)
        with session.connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(request, parameters)
            return cursor.fetchall() if cursor.description is not None else []

    def _selection(self) -> sql.Composed:
        """« select » de la table, avec ses champs « liste » lus dans leur table de liaison."""
        columns: list[sql.Composable] = [sql.SQL("t.*")]
        for field, (link, owner, value) in self._lists.items():
            columns.append(
                sql.SQL(
                    "array(select l.{value} from {link} l where l.{owner} = t.id order by l.position) as {field}"
                ).format(
                    value=sql.Identifier(value),
                    link=sql.Identifier(link),
                    owner=sql.Identifier(owner),
                    field=sql.Identifier(field),
                )
            )
        return sql.SQL("select {columns} from {table} t").format(
            columns=sql.SQL(", ").join(columns), table=sql.Identifier(self._name)
        )

    def list_all(self, **criteria) -> list[dict]:
        # « is not distinct from » : comme « = », mais vrai aussi quand les deux valent null.
        conditions = [sql.SQL("t.{} is not distinct from %s").format(sql.Identifier(field)) for field in criteria] or [
            sql.SQL("true")
        ]
        request = sql.SQL("{selection} where {conditions} order by t.id").format(
            selection=self._selection(), conditions=sql.SQL(" and ").join(conditions)
        )
        return self._execute(request, [_value(v) for v in criteria.values()])

    def read(self, id_: int) -> dict | None:
        rows = self._execute(sql.SQL("{} where t.id = %s").format(self._selection()), (id_,))
        return rows[0] if rows else None

    def add(self, data: dict) -> dict:
        columns, lists = self._split(data)
        if columns:
            request = sql.SQL("insert into {table} ({columns}) values ({values}) returning id").format(
                table=sql.Identifier(self._name),
                columns=sql.SQL(", ").join(map(sql.Identifier, columns)),
                values=sql.SQL(", ").join([sql.Placeholder()] * len(columns)),
            )
        else:
            request = sql.SQL("insert into {table} default values returning id").format(
                table=sql.Identifier(self._name)
            )
        id_ = self._execute(request, [_value(v) for v in columns.values()], write=True)[0]["id"]
        self._write_lists(id_, lists)
        return self.read_existing(id_)

    def update(self, id_: int, changes: dict) -> dict:
        columns, lists = self._split(changes)
        if columns:
            request = sql.SQL("update {table} set {assignments} where id = %s").format(
                table=sql.Identifier(self._name),
                assignments=sql.SQL(", ").join(sql.SQL("{} = %s").format(sql.Identifier(c)) for c in columns),
            )
            self._execute(request, [*map(_value, columns.values()), id_], write=True)
        self._write_lists(id_, lists)
        return self.read_existing(id_)

    def delete(self, id_: int) -> None:
        # Les lignes des tables de liaison partent avec (« on delete cascade » dans la base).
        request = sql.SQL("delete from {} where id = %s").format(sql.Identifier(self._name))
        self._execute(request, (id_,), write=True)

    def _split(self, data: dict) -> tuple[dict, dict]:
        """Sépare les colonnes de la table et les champs « liste »."""
        columns = {k: v for k, v in data.items() if k not in self._lists and k != "id"}
        lists = {k: v for k, v in data.items() if k in self._lists}
        return columns, lists

    def _write_lists(self, id_: int, lists: dict) -> None:
        """Remplace le contenu des champs « liste » donnés (table de liaison : on efface, puis on réécrit)."""
        for field, values in lists.items():
            link, owner, value = self._lists[field]
            self._execute(
                sql.SQL("delete from {} where {} = %s").format(sql.Identifier(link), sql.Identifier(owner)),
                (id_,),
                write=True,
            )
            for position, element in enumerate(values):
                self._execute(
                    sql.SQL("insert into {} ({}, {}, position) values (%s, %s, %s)").format(
                        sql.Identifier(link), sql.Identifier(owner), sql.Identifier(value)
                    ),
                    (id_, element, position),
                    write=True,
                )


class PostgresStorage(Storage):
    """Les tables de l'application, dans la base PostgreSQL."""

    def __init__(self, settings: DatabaseSettings, size_max: int = 10) -> None:
        # Le pool n'est pas ouvert ici, mais par open() : créer l'objet ne contacte pas la base.
        self._pool = ConnectionPool(
            kwargs={
                **settings.connection(),  # dont le schéma de nos tables (search_path) et les dates en UTC
                "application_name": "suivi-delivery-backend",  # visible côté base (pg_stat_activity)
                "connect_timeout": 5,
            },
            min_size=1,
            max_size=size_max,
            open=False,
            name="suivi-delivery",
        )
        self._description = f"{settings.user}@{settings.host}:{settings.port}/{settings.name} ({settings.schema})"
        super().__init__()

    def _table(self, name: str) -> Table:
        return TablePostgres(name, self)

    def open(self, wait_seconds: float = 30) -> None:
        """Se connecte à la base (en attendant qu'elle réponde) et vérifie que ses tables sont là."""
        try:
            self._pool.open(wait=True, timeout=wait_seconds)
        except PoolTimeout as error:
            raise StorageUnavailable(
                f"Base PostgreSQL injoignable ({self._description}) après {wait_seconds:g} s"
            ) from error
        with self._pool.connection() as connection:
            present = {
                row[0]
                for row in connection.execute(
                    "select table_name from information_schema.tables where table_schema = current_schema()"
                )
            }
        missing = [name for name in TABLE_NAMES if name not in present]
        if missing:
            self._pool.close()
            raise StorageUnavailable(
                f"La base {self._description} n'a pas les tables {', '.join(missing)} : "
                "appliquer d'abord la structure avec Liquibase (voir docs/postgresql.md)"
            )
        logger.info("Connecté à la base PostgreSQL %s", self._description)

    def open_session(self, write: bool) -> Session:
        """Une nouvelle transaction (app/transactions.py ouvre la sienne à chaque requête)."""
        return Session(self._pool, write)

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
            # Transaction imbriquée = point de sauvegarde : annulée seule si une erreur sort du bloc.
            with session.connection.transaction():
                yield self

    def check(self) -> None:
        try:
            with self._pool.connection(timeout=2) as connection:
                connection.execute("select 1")
        except (psycopg.Error, PoolTimeout) as error:
            raise StorageUnavailable(f"Base PostgreSQL injoignable : {error}") from error

    def close(self) -> None:
        self._pool.close()
