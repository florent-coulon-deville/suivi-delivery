# La base SQLite

Toutes les données de l'outil sont dans **un seul fichier SQLite**. Ce guide explique ce que c'est, où se trouve le fichier, comment la structure évolue et comment sauvegarder.

## Qu'est-ce que SQLite ?

**SQLite** est une base de données rangée dans un fichier ordinaire. Il n'y a **pas de serveur de base** à installer, à lancer ou à surveiller : l'API ouvre le fichier et y lit et écrit directement. Le module `sqlite3` est livré avec Python : aucune dépendance en plus.

C'est le choix de la **version légère** de l'outil : deux programmes seulement (l'API et l'interface), au lieu de cinq (avec PostgreSQL, Liquibase et Keycloak).

Ce qu'on gagne et ce qu'on perd :

| | SQLite (version légère) |
| --- | --- |
| Installation | rien à installer : un fichier |
| Sauvegarde | copier un fichier (ou l'export Excel) |
| Exemplaires de l'API | **un seul** à la fois sur un même fichier |
| Saisies simultanées | une requête à la fois (largement assez pour une équipe) |

## Où est le fichier ?

La variable `APP_DB_FILE` donne son chemin. Sans elle, l'API garde tout **en mémoire** (perdu à l'arrêt : tests, essais).

| Où | Fichier | Gardé dans |
| --- | --- | --- |
| Poste, sans Docker | ce que vous mettez dans `APP_DB_FILE` (ex. `donnees/suivi-delivery.sqlite`, depuis `backend/`) | ce dossier (ignoré par Git) |
| Poste, avec `docker-deploy.zsh` | `/data/suivi-delivery.sqlite` dans le conteneur | le volume `suivi-delivery-data-local` |
| Cluster (chart Helm) | `/data/suivi-delivery.sqlite` dans le pod | le disque `<installation>-data` (PersistentVolumeClaim) |

À côté du fichier, SQLite crée parfois deux petits fichiers, `…-wal` et `…-shm` : son **journal d'écriture**, qui protège les données en cas d'arrêt brutal. Ils font partie de la base : ne pas les effacer pendant que l'API tourne.

## La structure (les tables)

La structure est décrite dans `backend/app/sql/`, un fichier SQL par version de la structure :

```Plaintext
backend/app/sql/
└── 001-tables.sql     les 14 tables, leurs contraintes (pk_, uq_, ck_, fk_) et leurs index (ix_)
```

**C'est l'API qui l'applique**, au démarrage : il n'y a pas d'outil à part à lancer avant (comme Liquibase dans la version complète).

1. La base retient le numéro du dernier fichier appliqué (`PRAGMA user_version`, une case réservée dans le fichier SQLite).
2. Au démarrage, l'API applique, dans l'ordre, les fichiers dont le numéro est plus grand. Chaque fichier passe en entier, ou pas du tout (une transaction).
3. Une base préparée par une version **plus récente** de l'API est refusée (l'API ne démarre pas, avec un message clair) : on ne revient pas en arrière sans le savoir.

Détail des tables et des règles : [modele-de-donnees.md](modele-de-donnees.md).

### Faire évoluer la structure

- On **ajoute** un fichier : `002-<ce qui change>.sql` (puis `003-…`).
- On ne **modifie jamais** un fichier déjà appliqué sur une base qui sert : il ne serait pas rejoué.
- La base contrôle elle-même ce qui serait faux (unicité, liens, valeurs permises), en filet de sécurité derrière l'API : une saisie refusée par la base donne un **409**, pas une erreur 500.

## Une requête à la fois

L'API n'a qu'une connexion au fichier, et **une requête à la fois** s'en sert (un verrou, `app/storage_sqlite.py`). C'est simple et sûr : le contrôle de cohérence voit toujours des données à jour, et deux saisies ne peuvent pas se croiser.

Chaque requête est une **transaction** : tout ce qu'elle fait est enregistré ensemble, juste avant la réponse, ou annulé ensemble si quelque chose plante (`app/transactions.py`).

Conséquence : **un seul exemplaire de l'API** sur un même fichier. Le chart Helm l'impose (`backend.replicas` : 0 ou 1, mise à jour en `Recreate`).

## Sauvegarder

Deux façons :

- **L'export Excel** (bouton « Exporter » de l'interface) : toute la configuration, lisible, réimportable dans une autre instance (écran « Import »). Pas le journal.
- **Une copie du fichier**, journal compris. Le plus sûr est de demander à SQLite lui-même une copie cohérente, même pendant que l'API tourne :

```bash
# sur le poste, avec Docker : copier le fichier hors du volume
docker run --rm -v suivi-delivery-data-local:/data -v "$PWD":/sauvegarde alpine \
  cp /data/suivi-delivery.sqlite /sauvegarde/suivi-delivery-$(date +%F).sqlite
```

Pour une copie à chaud sans risque, arrêter d'abord l'API (`docker stop suivi-delivery-backend-local`), copier, puis la relancer (`docker start …`). Sur un cluster : `kubectl scale deployment <installation>-backend --replicas=0`, copier depuis le disque, puis `--replicas=1`.

## Regarder dans la base

N'importe quel outil SQLite ouvre le fichier (par exemple `sqlite3` en ligne de commande, ou *DB Browser for SQLite*). À faire sur une **copie**, ou API arrêtée, pour ne rien abîmer :

```bash
sqlite3 suivi-delivery.sqlite ".tables"
sqlite3 suivi-delivery.sqlite "select code, label from environments"
```

## Les tests

Les tests tournent deux fois en CI : en mémoire, puis sur un vrai fichier SQLite (`TESTS_DB_FILE`, nom finissant par `_tests.sqlite`, effacé avant chaque test). Sur le poste :

```bash
uv run pytest                                              # en mémoire
TESTS_DB_FILE=/tmp/suivi-delivery_tests.sqlite uv run pytest   # sur SQLite
```
