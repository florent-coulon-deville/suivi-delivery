# 3. Le stockage : `storage.py`, `storage_sqlite.py`, `transactions.py`

## L'idée

Les routes rangent et relisent les données par quelques opérations simples : « liste-moi les modules de l'application 3 », « ajoute ce cluster ». Ces opérations sont définies une fois, dans `storage.py`. Elles existent en deux versions :

| Version | Où sont les données | Qui s'en sert |
| --- | --- | --- |
| `MemoryStorage` (`storage.py`) | en mémoire, perdues à l'arrêt | les tests, les essais rapides (sans `APP_DB_FILE`) |
| `SqliteStorage` (`storage_sqlite.py`) | dans un fichier SQLite | l'API déployée (avec `APP_DB_FILE`) |

**Les routes ne savent pas laquelle elles utilisent** : elles appellent les mêmes méthodes. On peut donc changer de stockage sans toucher aux routes.

La **structure** de la base (tables, colonnes) est décrite dans `app/sql/`, et appliquée par `SqliteStorage.open()` au démarrage : voir [sqlite.md](../sqlite.md).

## Une `Table`

Une table est faite de **lignes** rangées par identifiant (1, 2, 3…). Chaque ligne est un dictionnaire de champs. La table des clusters, par exemple :

```python
{"id": 1, "code": "cb01", "label": "Cluster hors prod", "is_prod": False}
{"id": 2, "code": "cb02", "label": "Cluster prod",      "is_prod": True}
```

Les **liens entre objets** se font par identifiant, comme dans une base de données. Un module contient `"application_id": 3` : on ne recopie jamais l'application dans le module.

## Ses méthodes

| Méthode | Ce qu'elle fait | Exemple |
| --- | --- | --- |
| `list_all(**criteria)` | toutes les lignes, ou celles qui correspondent aux critères | `storage.modules.list_all(application_id=3)` |
| `read(id_)` | une ligne, ou `None` si elle n'existe pas | `storage.clusters.read(2)` |
| `read_existing(id_)` | une ligne dont on **sait** qu'elle existe (vérifiée juste avant) | |
| `find(**criteria)` | la première ligne qui correspond, ou `None` | `storage.clusters.find(code="cb01")` |
| `add(data)` | attribue le numéro suivant et range la ligne | |
| `update(id_, changes)` | change seulement les champs donnés | `update(2, {"label": "Prod"})` |
| `delete(id_)` | retire la ligne | |

`Table` (dans `storage.py`) est une classe **abstraite** (`ABC`) : elle dit quelles méthodes existent, sans les écrire (`@abstractmethod`). `MemoryTable` et `SqliteTable` les écrivent chacune à leur façon. `read_existing` et `find`, elles, sont écrites une fois pour toutes dans `Table`, à partir des autres.

Deux détails importants :

- **Chaque méthode renvoie une copie** de la ligne. Celui qui la reçoit peut la modifier sans abîmer la table.
- **`read` ou `read_existing` ?** On utilise `read` quand l'élément peut ne pas exister : la route répond alors 404 ou 422. On utilise `read_existing` quand une vérification a déjà eu lieu juste avant : il n'y a donc pas de cas « absent » à gérer.

## Le `Storage`

```python
class Storage(ABC):
    def __init__(self) -> None:
        self.audit_log = self._table("audit_log")
        self.environments = self._track("environments")
        self.clusters = self._track("clusters")
        # … une table par type d'objet (liste complète : NOMS_TABLES)
```

Chaque version fabrique ses propres tables (`_table`) : des `MemoryTable` pour l'une, des `SqliteTable` pour l'autre. Les routes écrivent donc `storage.clusters.list_all()` ou `storage.modules.add(...)`, quelle que soit la version.

### Le journal : `TrackedTable` et `audit_log.py`

`_track` enveloppe la table dans une `TrackedTable`. Les lectures passent telles quelles. Chaque écriture (`add`, `update`, `delete`) lit la ligne avant, fait l'écriture, puis ajoute une ligne à la table `audit_log`, **dans la même transaction**. Les deux sont donc enregistrées ensemble, ou annulées ensemble : une saisie refusée par [la cohérence](07-coherence.md) ne laisse aucune trace. Les routes n'ont rien à faire.

Pas d'auteur : cette version n'a pas de comptes. Chaque ligne du journal dit quoi (la table, l'identifiant, l'action, l'avant et l'après) et quand.

Le `Storage` offre aussi :

| Méthode | Rôle |
| --- | --- |
| `transaction()` | un bloc `with` dont tout le contenu est enregistré ensemble, ou annulé ensemble |
| `attempt()` | un bloc `with` pour faire une saisie « pour voir », annulée si une erreur sort du bloc (utilisé par [la cohérence](07-coherence.md)) |
| `check()` | la base répond-elle ? (probe `/readyz`) ; lève `StorageUnavailable` sinon |
| `close()` | ferme le fichier, à l'arrêt de l'API |

## En mémoire : `MemoryStorage`

Chaque table est un dictionnaire `{identifier: line}`, plus le dernier numéro attribué (jamais réutilisé, même après une suppression) :

```python
class MemoryTable(Table):
    def add(self, data: dict) -> dict:
        self._last_id += 1
        line = {"id": self._last_id, **data}
        self._rows[line["id"]] = line
        return dict(line)
```

L'**essai** se fait sur une copie complète des données (`copy.deepcopy`). Si tout s'est bien passé, la copie devient les données ; sinon, elle est simplement oubliée.

## Dans SQLite : `SqliteStorage`

SQLite est une base rangée dans **un seul fichier** (`APP_DB_FILE`), que l'API ouvre elle-même avec le module `sqlite3`, livré avec Python. Chaque méthode devient une requête SQL.

- Les noms de tables et de colonnes viennent du code, jamais d'une saisie, et sont mis entre guillemets.
- Les valeurs passent toujours à part (`?`), jamais collées dans le texte de la requête.

Ainsi, aucune *injection SQL* n'est possible (une injection SQL, c'est une valeur saisie qui serait exécutée comme du SQL).

| Méthode | SQL |
| --- | --- |
| `list_all(application_id=3)` | `select * from "modules" where "application_id" is ? order by id` |
| `add({...})` | `insert into "clusters" ("code", "label", "is_prod") values (?, ?, ?) returning id` |
| `update(2, {"label": …})` | `update "clusters" set "label" = ? where id = ?` |
| `delete(2)` | `delete from "clusters" where id = ?` |

`is` : comme `=`, mais vrai aussi quand les deux valent `null` (ex. `list_all(promotion_order=None)`).

**Les types** : SQLite range tout en texte ou en nombres. `storage_sqlite.py` convertit à l'écriture et à la lecture : un booléen devient 0 / 1, une date du texte ISO en UTC, l'avant / après du journal du JSON ; et inversement (`_value`, `_read`).

**Un champ « liste »** : les `namespace_ids` d'un paramètre ne sont pas une colonne. Ils sont rangés dans une table de liaison, `parameter_namespaces` (une ligne par couple paramètre / namespace). `SqliteTable` s'en charge : elle les relit en une requête et les réécrit à chaque modification. Ces champs sont listés dans `LISTS`.

### L'ouverture : la structure appliquée au démarrage

`open()` ouvre le fichier (créé s'il n'existe pas), active la vérification des liens (`pragma foreign_keys`, éteinte par défaut dans SQLite) et le journal d'écriture (`pragma journal_mode = wal`). Puis il applique, dans l'ordre, les fichiers de `app/sql/` que la base n'a pas encore : la base retient le numéro du dernier (`pragma user_version`). Une base plus récente que l'API est refusée.

### Une transaction par requête : `transactions.py`

`RequestTransaction` est un **middleware** : une fonction placée devant l'application, qui voit passer chaque requête et chaque morceau de réponse. Pour chaque appel sous `/api` :

1. il ouvre une transaction (une `Session`), qui prend le verrou « une requête à la fois » ;
2. il la range dans `SESSION`, une **variable de contexte** (`ContextVar`) : une variable propre à chaque requête, que les tables retrouvent sans qu'on ait à la passer de fonction en fonction ;
3. la route travaille ;
4. **juste avant d'envoyer la réponse**, il enregistre (`commit`) et rend le verrou. Le client ne reçoit donc jamais « 201 Créé » pour une donnée qui ne serait pas enregistrée ;
5. si une erreur imprévue sort de la route (500), il annule tout (`rollback`).

Une réponse d'erreur prévue (404, 409…) enregistre ce qui a été fait avant elle, comme en mémoire. Les saisies incohérentes, elles, ont déjà été annulées par l'essai.

### Une requête à la fois

L'API n'a qu'**une connexion** au fichier. Chaque requête prend un **verrou** (`threading.Lock`) au début de sa transaction, et le rend à la fin. Les autres attendent leur tour (30 s au plus).

Deux saisies ne peuvent donc pas se croiser, et le contrôle de cohérence voit toujours des données à jour. C'est largement assez rapide pour une équipe. Conséquence : **un seul exemplaire de l'API** sur un même fichier.

### L'essai : un point de sauvegarde

Dans SQLite, l'essai n'a pas besoin de copier les données. On pose un **point de sauvegarde** (`savepoint`) dans la transaction, on fait la saisie, on vérifie les règles. Si une règle est cassée, on revient au point de sauvegarde (`rollback to`) : la saisie disparaît, le reste de la transaction est intact. Les essais peuvent s'imbriquer : chaque point a son propre nom.

### Le filet de sécurité

La base vérifie elle-même liens, unicité, valeurs autorisées et minuscules (`app/sql/001-tables.sql`). Si elle refuse une saisie que l'API aurait laissée passer, `main.py` transforme son erreur (`sqlite3.IntegrityError`) en **409** « Saisie refusée par la base de données », et non en erreur 500.

## Ce qu'il faut retenir

- **Le stockage ne vérifie rien lui-même.** Il range ce qu'on lui donne. Les vérifications sont faites avant, par les schémas, les routes et la cohérence. La base n'est qu'un filet de sécurité.
- **Les routes ne changent pas** d'un stockage à l'autre : elles ne voient que `list_all`, `read`, `add`…
- **Une requête = une transaction** : tout est enregistré ensemble, juste avant la réponse.
- **Une requête à la fois**, et un seul exemplaire de l'API sur un même fichier.
- **Chaque saisie est notée au journal**, automatiquement, dans la même transaction.

Page suivante : [les schémas](04-schemas.md).
