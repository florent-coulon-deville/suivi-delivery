# 10. Recette : ajouter une ressource

Exemple fictif : on veut gérer des **équipes** (un code et un nom).

## Étape 1 — Les schémas (`schemas.py`)

```python
# --- Équipe -----------------------------------------------------------------


class EquipeCreation(Entry):          # POST et PUT
    code: Code
    name: Label


class EquipeUpdate(Update):   # PATCH
    code: Code | None = None
    name: Label | None = None


class Equipe(BaseModel):               # réponse
    id: int
    code: str
    name: str
```

## Étape 2 — La table (`storage.py` et `app/sql/`)

Dans `Storage.__init__`, et dans la liste `TABLE_NAMES` (au bon endroit : après les tables dont elle dépend) :

```python
self.equipes = self._track("equipes")
```

Puis créer la table dans la base, par un **nouveau** fichier numéroté de `app/sql/` (ici `002-equipes.sql` ; voir [sqlite.md](../sqlite.md#faire-évoluer-la-structure)). L'API l'appliquera toute seule au prochain démarrage, une seule fois :

```sql
-- Équipes (un code et un nom).
create table equipes (
    id   integer      not null constraint pk_equipes primary key autoincrement,
    code varchar(30)  not null constraint uq_equipes_code unique,
    name varchar(100) not null,
    constraint ck_equipes_code_lowercase check (code = lower(code))
);
```

Comme pour les autres tables, chaque contrainte a un nom (`pk_`, `uq_`, `ck_`, `fk_`). Ne jamais modifier `001-tables.sql` : une base qui sert l'a déjà appliqué, et ne le rejouerait pas.

Les colonnes portent les noms des champs du schéma : `SqliteTable` n'a rien d'autre à savoir.

## Étape 3 — Les routes (`routes/equipes.py`)

Le plus simple est de **copier `routes/clusters.py`**, puis de :

1. remplacer `cluster` par `equipe`, et `Cluster` par `Equipe` ;
2. adapter la docstring en tête de fichier ;
3. adapter les vérifications :
   - unicité (`check_unique`) ;
   - références (`check_reference`) si l'objet pointe vers d'autres objets ;
   - suppression interdite si l'objet est utilisé (`check_unused`).

Si une **autre** ressource fait référence aux équipes (par exemple `module.equipe_id`), il faut aussi, dans `routes/equipes.py`, interdire la suppression d'une équipe encore utilisée :

```python
check_unused(storage.modules, "Équipe encore utilisée par un module", equipe_id=equipe_id)
```

## Étape 4 — Le branchement (`main.py`)

Ajouter `equipes` dans l'import `from app.routes import (...)`, dans la liste `routers` de `create_application`, et une ligne dans `TAGS` pour Swagger.

Pas de droits à régler : cette version n'a pas de connexion.

## Étape 5 — Une règle d'ensemble ? (`consistency.py`)

Seulement si la nouvelle donnée participe à une règle qui croise plusieurs objets. Dans ce cas, on écrit la règle dans une petite fonction, appelée par `inconsistencies`, et on fait passer les écritures concernées par `apply_if_consistent`.

## Étape 6 — Les tests (`tests/test_equipes.py`)

Au minimum : créer (201 + `Location`), lire (200 / 404), unicité (409), données invalides (422), modifier en PATCH et en PUT, supprimer (204 puis 404), suppression interdite si l'équipe est utilisée (409).

## Étape 7 — Vérifier et documenter

```bash
uv run pytest
uv run ruff check . && uv run ruff format --check . && uv run ty check
```

Lancer aussi les tests sur un fichier SQLite (`TESTS_DB_FILE=/tmp/suivi-delivery_tests.sqlite uv run pytest`) : ils vérifient que le nouveau fichier de `app/sql/` s'applique bien. Voir [sqlite.md](../sqlite.md#les-tests).

Puis mettre à jour `docs/modele-de-donnees.md` (tableau et schéma Mermaid) et `docs/api.md` (tableau des ressources).
