# 3. Le stockage : `storage.py`, `storage_postgres.py`, `transactions.py`

## L'idée

Les routes rangent et relisent les données par quelques opérations simples : « liste-moi les modules de l'application 3 », « ajoute ce cluster ». Ces opérations sont définies une fois, dans `storage.py`. Elles existent en deux versions :

| Version | Où sont les données | Qui s'en sert |
| --- | --- | --- |
| `MemoryStorage` (`storage.py`) | en mémoire, perdues à l'arrêt | les tests, les essais rapides (sans `APP_DB_HOST`) |
| `PostgresStorage` (`storage_postgres.py`) | dans la base PostgreSQL | l'API déployée (avec `APP_DB_HOST`) |

**Les routes ne savent pas laquelle elles utilisent** : elles appellent les mêmes méthodes. On peut donc changer de stockage sans toucher aux routes.

La **structure** de la base (tables, colonnes) n'est pas créée ici, mais par Liquibase : voir [postgresql.md](../postgresql.md).

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

`Table` (dans `storage.py`) est une classe **abstraite** (`ABC`) : elle dit quelles méthodes existent, sans les écrire (`@abstractmethod`). `MemoryTable` et `TablePostgres` les écrivent chacune à leur façon. `read_existing` et `find`, elles, sont écrites une fois pour toutes dans `Table`, à partir des autres.

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

Chaque version fabrique ses propres tables (`_table`) : des `MemoryTable` pour l'une, des `TablePostgres` pour l'autre. Les routes écrivent donc `storage.clusters.list_all()` ou `storage.modules.add(...)`, quelle que soit la version.

### Le journal : `TrackedTable` et `audit_log.py`

`_track` enveloppe la table dans une `TrackedTable`. Les lectures passent telles quelles. Chaque écriture (`add`, `update`, `delete`) lit la ligne avant, fait l'écriture, puis ajoute une ligne à la table `audit_log`, **dans la même transaction**. Les deux sont donc enregistrées ensemble, ou annulées ensemble : une saisie refusée par [la cohérence](07-coherence.md) ne laisse aucune trace. Les routes n'ont rien à faire.

D'où vient l'auteur de la saisie ?

1. Pour chaque requête, le middleware `RequestAuthor` prépare une case vide, `AUTHOR` (une « variable de contexte », expliquée plus bas).
2. Une fois le jeton vérifié, `access.py` y range la personne ou le programme qui appelle.
3. Sans auteur (par exemple au démarrage), rien n'est noté.

Les comptes sont gardés dans Keycloak, pas dans nos tables. Leur gestion est donc notée par la route elle-même (`log_edit`, objet `accounts`). Un mot de passe ou une clé n'y apparaît jamais : on note seulement `"changé"`.

Le `Storage` offre aussi :

| Méthode | Rôle |
| --- | --- |
| `transaction()` | un bloc `with` dont tout le contenu est enregistré ensemble, ou annulé ensemble |
| `dry_run()` | un bloc `with` pour faire une saisie « pour voir », annulée si une erreur sort du bloc (utilisé par [la cohérence](07-coherence.md)) |
| `check()` | la base répond-elle ? (probe `/readyz`) ; lève `StorageUnavailable` sinon |
| `close()` | ferme les connexions, à l'arrêt de l'API |

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

## Dans PostgreSQL : `PostgresStorage`

Chaque méthode devient une requête SQL, écrite avec le module `psycopg.sql`.

- Les noms de tables et de colonnes sont protégés par `sql.Identifier`.
- Les valeurs passent toujours à part (`%s`), jamais collées dans le texte de la requête.

Ainsi, aucune *injection SQL* n'est possible (une injection SQL, c'est une valeur saisie qui serait exécutée comme du SQL).

| Méthode | SQL |
| --- | --- |
| `list_all(application_id=3)` | `select t.* from modules t where t.application_id is not distinct from %s order by t.id` |
| `add({...})` | `insert into clusters (code, label, is_prod) values (%s, %s, %s) returning id` |
| `update(2, {"label": …})` | `update clusters set label = %s where id = %s` |
| `delete(2)` | `delete from clusters where id = %s` |

`is not distinct from` : comme `=`, mais vrai aussi quand les deux valent `null` (ex. `list_all(promotion_order=None)`).

**Un champ « liste »** : les `namespace_ids` d'un paramètre ne sont pas une colonne. Ils sont rangés dans une table de liaison, `parameter_namespaces` (une ligne par couple paramètre / namespace). `TablePostgres` s'en charge : elle les relit avec un `array(select …)` et les réécrit à chaque modification. Ces champs sont listés dans `LISTS`.

### Les connexions : le « pool »

Ouvrir une connexion à PostgreSQL prend du temps. `psycopg_pool` en garde quelques-unes ouvertes (1 à 10) et les prête aux requêtes, qui les rendent ensuite.

Le pool est ouvert au démarrage de l'API (`open()`). L'API vérifie au passage que toutes ses tables existent. Sinon, elle s'arrête avec ce message : « appliquer d'abord la structure avec Liquibase ».

### Une transaction par requête : `transactions.py`

`RequestTransaction` est un **middleware** : une fonction placée devant l'application, qui voit passer chaque requête et chaque morceau de réponse. Pour chaque appel sous `/api` :

1. il prend une connexion et ouvre une transaction (une `Session`) ;
2. il la range dans `SESSION`, une **variable de contexte** (`ContextVar`) : une variable propre à chaque requête, que les tables retrouvent sans qu'on ait à la passer de fonction en fonction ;
3. la route travaille ;
4. **juste avant d'envoyer la réponse**, il enregistre (`commit`). Le client ne reçoit donc jamais « 201 Créé » pour une donnée qui ne serait pas enregistrée ;
5. si une erreur imprévue sort de la route (500), il annule tout (`rollback`).

Une réponse d'erreur prévue (404, 409…) enregistre ce qui a été fait avant elle, comme en mémoire. Les saisies incohérentes, elles, ont déjà été annulées par l'essai.

### Une écriture à la fois

Une requête qui modifie (POST, PUT, PATCH, DELETE) prend d'abord un **verrou de la base** (`pg_advisory_xact_lock`). Elle le rend automatiquement à la fin de sa transaction. Les autres écritures attendent leur tour.

Deux saisies ne peuvent donc pas se croiser, même si plusieurs exemplaires de l'API tournent. Le contrôle de cohérence voit toujours des données à jour. Les lectures, elles, n'attendent jamais.

### L'essai : un point de sauvegarde

Dans PostgreSQL, l'essai n'a pas besoin de copier les données. On pose un **point de sauvegarde** (savepoint) dans la transaction, on fait la saisie, on vérifie les règles. Si une règle est cassée, on revient au point de sauvegarde : la saisie disparaît, le reste de la transaction est intact.

### Le filet de sécurité

La base vérifie elle-même liens, unicité, valeurs autorisées et minuscules (voir [postgresql.md § 3](../postgresql.md#3-la-structure-des-données)). Si elle refuse une saisie que l'API aurait laissée passer, `main.py` transforme son erreur (`IntegrityError`) en **409** « Saisie refusée par la base de données », et non en erreur 500.

## Ce qu'il faut retenir

- **Le stockage ne vérifie rien lui-même.** Il range ce qu'on lui donne. Les vérifications sont faites avant, par les schémas, les routes et la cohérence. La base n'est qu'un filet de sécurité.
- **Les routes ne changent pas** d'un stockage à l'autre : elles ne voient que `list_all`, `read`, `add`…
- **Une requête = une transaction** : tout est enregistré ensemble, juste avant la réponse.
- **Une écriture à la fois**, même avec plusieurs exemplaires de l'API.
- **Chaque saisie est notée au journal**, automatiquement, dans la même transaction.

Page suivante : [les schémas](04-schemas.md).
