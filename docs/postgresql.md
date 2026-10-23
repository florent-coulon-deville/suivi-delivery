# Base de données PostgreSQL et Liquibase

Les données sont dans une base **PostgreSQL**. Sa **structure** (tables, colonnes, contrôles) est gérée par **Liquibase**.

Ce guide explique :

- les outils choisis et leur version ;
- la structure des données ;
- comment faire évoluer la structure (le geste le plus courant) ;
- les commandes Liquibase utiles ;
- comment l'API utilise la base.

## 1. Les outils et leurs versions

| Rôle | Outil | Éditeur | Version |
| --- | --- | --- | --- |
| Base de données | image `dhi.io/postgres:18.6-alpine3.24` | Docker Hardened Image (PostgreSQL) | 18.6 |
| Gestion de la structure | image `dhi.io/liquibase:4.33.0-debian13` | Docker Hardened Image (Liquibase) | 4.33.0 |
| Connecteur PostgreSQL de Liquibase (Java, JDBC) | `postgresql`, déjà inclus dans l'image de Liquibase | PostgreSQL JDBC (pgjdbc) | 42.7.12 |
| Connecteur PostgreSQL de l'API (Python) | `psycopg[binary]` | Psycopg | 3.3.6 |
| Connexions réutilisées par l'API | `psycopg-pool` | Psycopg | 3.3.3 |

**Pourquoi Liquibase 4 et pas 5.** L'image durcie de Liquibase (Docker Hardened Image) n'existe qu'en 4.x. Nos fichiers de changements n'utilisent rien de propre à la version 5 : la 4.33.0 les applique tels quels (vérifié sur une base neuve).

**Licence de Liquibase.** La version 4 est sous licence **Apache 2.0** (libre, sans restriction). À partir de la version 5, Liquibase passe sous FSL (Functional Source License : gratuit, y compris en production, mais interdit d'en faire un produit concurrent ; chaque version repasse sous Apache 2.0 deux ans après sa sortie).

L'image durcie **inclut déjà le connecteur PostgreSQL** (le pilote qui permet à Liquibase de parler à PostgreSQL). Notre image `suivi-delivery-liquibase` ([liquibase/Dockerfile](../liquibase/Dockerfile)) n'ajoute donc que nos fichiers de changements : rien n'est téléchargé à la fabrication.

## 2. Ce que fait chaque outil

Dans le projet, ce sont deux **modules**, à côté de `backend/` et `frontend/` :

| Module | Contenu |
| --- | --- |
| [`postgres/`](../postgres/README.md) | la base : un `Dockerfile` qui reprend l'image durcie sous le nom du projet (`suivi-delivery-postgres`), avec la **préparation de la base** au premier démarrage (`initialization/01-schemas.sh`, lancé par notre point d'entrée `start.sh`, car l'image durcie ne le fait pas), et son modèle de réglages (`docker.example.env`) |
| [`liquibase/`](../liquibase/README.md) | la structure : le `Dockerfile` de l'image `suivi-delivery-liquibase` et les changements (`changelog/`) |

```Plaintext
          ┌────────────────────────────┐
          │    liquibase/changelog     │  les changements de structure, en SQL (dans Git)
          └──────────────┬─────────────┘
                         │ « liquibase update » : applique ce qui manque, avant l'API
                         ▼
 API (Python) ──psycopg──► PostgreSQL ◄── psql, DBeaver… (consultation, pour apprendre)
   lit et écrit les        les tables, et deux tables de Liquibase :
   DONNÉES                 databasechangelog (ce qui a été appliqué),
                           databasechangeloglock (un seul Liquibase à la fois)
```

- **PostgreSQL** garde les données. Il vérifie lui-même ce qu'il peut : liens entre tables, unicité, valeurs autorisées, minuscules. C'est un filet de sécurité derrière les contrôles de l'API.
- **Une seule base, deux schémas** (deux « dossiers » de tables, séparés) :
  - `suivi_delivery` pour nos tables ;
  - `keycloak` pour celles de Keycloak (les comptes, voir [keycloak.md](keycloak.md)). Keycloak a son propre utilisateur, qui n'a accès qu'à ce schéma.
  - Le schéma `public` reste vide.

  Au premier démarrage (volume vide), l'image `suivi-delivery-postgres` crée les deux schémas et l'utilisateur de Keycloak (`postgres/initialization/01-schemas.sh`, réglages `APP_DB_SCHEMA`, `KC_DB_USERNAME`, `KC_DB_PASSWORD`). C'est nécessaire, car Liquibase ne sait pas créer son propre schéma : il faut qu'il existe avant lui.
- **Liquibase** tient le registre des changements de **structure**. À chaque lancement, il compare ce registre à la table `databasechangelog` de la base et applique ce qui manque, dans l'ordre. Il ne touche jamais aux données saisies.
- **L'API** ne crée ni ne modifie aucune table. Au démarrage, elle vérifie seulement que ses tables sont là. Si ce n'est pas le cas, elle s'arrête avec ce message : « appliquer d'abord la structure avec Liquibase ».

Liquibase passe toujours **avant** l'API :

| Où | Qui lance Liquibase |
| --- | --- |
| Poste (Docker) | `./deployment/docker-deploy.zsh` (tout) ou `./deployment/docker-deploy.zsh liquibase` (la structure seule) |
| kind, OpenShift (Helm) | le conteneur de préparation `structure` du pod de l'API (un « initContainer ») |
| CI | le job « postgresql » (GitHub), avant les tests |

## 3. La structure des données

Il y a une table par objet (15 au total, avec le journal et les préférences), toutes dans le schéma `suivi_delivery`. Leur création est découpée en cinq fichiers, appliqués dans cet ordre. Chaque évolution future aura son propre fichier.

| Fichier | Contenu |
| --- | --- |
| [001-tables.sql](../liquibase/changelog/001-tables.sql) | les tables, avec **seulement leurs colonnes** : type, `not null`, `default`, numérotation de l'identifiant |
| [002-primary-keys.sql](../liquibase/changelog/002-primary-keys.sql) | les clés primaires (`alter table … add constraint pk_…`) |
| [003-unique-and-check-constraints.sql](../liquibase/changelog/003-unique-and-check-constraints.sql) | les unicités (`uq_…`) et les contrôles (`ck_…`) |
| [004-foreign-keys.sql](../liquibase/changelog/004-foreign-keys.sql) | les liens entre tables (`fk_…`) |
| [005-index.sql](../liquibase/changelog/005-index.sql) | les index (`ix_…`) |

**Chaque contrainte a un nom**, ajoutée à part avec `alter table … add constraint` :

| Préfixe | Sorte | Exemple |
| --- | --- | --- |
| `pk_<table>` | clé primaire | `pk_modules` |
| `uq_<table>_<columns>` | unicité | `uq_modules_application_code` |
| `ck_<table>_<règle>` | contrôle | `ck_modules_code_lowercase`, `ck_modules_type` |
| `fk_<table>_<link>` | clé étrangère | `fk_modules_application` |
| `ix_<table>_<columns>` | index | `ix_namespaces_environment` |

Ce nom se lit dans les messages d'erreur de la base (« duplicate key value violates unique constraint "uq_clusters_code" »), et sert à retirer une contrainte (`alter table clusters drop constraint uq_clusters_code`). La liste d'une table : `\d clusters` dans `psql`.

Les tables :

| Partie | Tables |
| --- | --- |
| Listes | `environments`, `clusters`, `network_zones` |
| Commande des ressources | `applications`, `namespaces`, `modules`, `dependencies` |
| Déploiement | `module_versions`, `compatibilities`, `parameters`, `parameter_namespaces` (liens paramètre ↔ namespace), `slots`, `installations` |
| Personnes | `preferences` : le thème de chaque personne, repérée par son identifiant Keycloak (`subject`) ; les comptes eux-mêmes sont dans Keycloak |
| Journal | `audit_log` : une ligne par saisie acceptée ; l'objet avant et après en JSON (`jsonb`) ; l'auteur est recopié (identifiant Keycloak et identifiant de connexion) |

Règles communes :

- **Identifiant** `id` : numéroté par la base (1, 2, 3…), jamais réutilisé après une suppression (`generated by default as identity`).
- **Liens** (`references`) : la ligne liée doit exister, et la base refuse de supprimer une ligne encore utilisée. Une seule exception : supprimer un paramètre retire ses liens vers les namespaces (`on delete cascade`).
- **Unicité au sein de l'application** : `unique (application_id, code)`, etc. L'identifiant d'application, le code d'environnement et le code de cluster sont uniques partout.
- **Tout en minuscules** : `check (code = lower(code))`.
- **Listes fermées** : `check (type in ('RELEASE', 'SNAPSHOT'))`. Les zones réseau sont une table (`network_zones`) : chaque namespace y est relié par une clé étrangère.
- **Dates** : `timestamptz`, une date avec son fuseau horaire, relue en UTC.

Le schéma des liens entre objets est dans [modele-de-donnees.md](modele-de-donnees.md).

## 4. Faire évoluer la structure

C'est le geste le plus courant. Exemple : ajouter une colonne `commentaire` aux installations.

**Règle d'or : on ne modifie JAMAIS un changement déjà appliqué.** Liquibase garde l'empreinte (somme de contrôle) de chaque changement appliqué. S'il voit qu'un changement a été modifié, il refuse de continuer. On **ajoute** toujours un nouveau changement.

1. Créer un nouveau fichier `liquibase/changelog/006-commentaire-des-installations.sql` :

   ```sql
   --liquibase formatted sql

   --changeset suivi-delivery:006-01-commentaire-installation
   --comment: Commentaire libre sur une installation.
   alter table installations add column commentaire varchar(500);
   --rollback alter table installations drop column commentaire;
   ```

   - `--changeset author:identifier` : le début d'un changement. Le couple auteur + identifiant doit être unique.
   - `--comment` : une description, gardée dans la table `databasechangelog`.
   - `--rollback` : comment annuler le changement (commande `rollback`, voir § 5).

2. L'ajouter **à la fin** de [main.yaml](../liquibase/changelog/main.yaml) :

   ```yaml
     - include:
         file: 006-commentaire-des-installations.sql
         relativeToChangelogFile: true
   ```

3. Adapter l'API (`app/schemas.py`, les routes, les tests). Le stockage, lui, n'a rien à changer : il lit toutes les colonnes de chaque table.

4. Appliquer la structure sur le poste (la base doit tourner : `./deployment/docker-deploy.zsh postgres`), puis lancer les tests sur la base (§ 7) :

   ```bash
   ./deployment/docker-deploy.zsh liquibase
   ```

**Changements délicats.** Liquibase applique chaque changement dans une transaction : entièrement, ou pas du tout. Certains cas demandent quand même de la réflexion :

- **Renommer une colonne** : l'ancienne version de l'API, encore en marche pendant la mise à jour, ne la trouve plus. Mieux vaut le faire en deux versions : ajouter la nouvelle colonne, puis retirer l'ancienne.
- **Colonne obligatoire** (`not null`) sur une table déjà remplie : donner une valeur par défaut, ou remplir les lignes existantes dans le même changement.
- **Données à corriger** (passer des codes en minuscules…) : un changement peut contenir des `update`. Il passe une seule fois, comme les autres.

## 5. Les commandes Liquibase utiles

On les lance avec l'image du projet, sur la base du poste (lancée par `./deployment/docker-deploy.zsh postgres`, puis `liquibase`). Pour ne pas répéter la commande, on la met une fois dans une variable :

```bash
LB=(docker run --rm --network suivi-delivery-local --env-file deployment/docker.env suivi-delivery-liquibase-local)
```

- La commande se lance depuis la racine du projet. L'adresse de la base, l'utilisateur et le mot de passe sont les `LIQUIBASE_COMMAND_*` de `deployment/docker.env`.
- Pour essayer un changement pas encore dans l'image : `./deployment/docker-deploy.zsh liquibase` la refabrique et l'applique.

| Commande | Ce qu'elle fait |
| --- | --- |
| `$LB status --verbose` | les changements **pas encore appliqués** |
| `$LB history` | les changements déjà appliqués, avec leur date |
| `$LB validate` | vérifie les fichiers de changements, sans rien appliquer |
| `$LB update-sql` | montre le SQL que `update` **exécuterait**, sans l'exécuter. À montrer à un administrateur de bases de données avant une mise en production |
| `$LB update` | applique ce qui manque (c'est la commande par défaut de l'image) |
| `$LB rollback-count --count=1` | annule le dernier changement (avec son `--rollback`). À éviter sur une base qui sert : les données de la colonne retirée sont perdues |

Pour regarder la base elle-même, avec `psql` (l'outil en ligne de commande de PostgreSQL, présent dans le conteneur) :

```bash
docker exec -it suivi-delivery-postgres-local psql -U suivi_delivery -d suivi_delivery
```

Quelques commandes, une fois dans `psql` :

- `\dn` : les schémas (`suivi_delivery`, `keycloak`, `public` vide) ;
- `\dt suivi_delivery.*` : la liste de nos tables (le schéma `suivi_delivery` est celui par défaut de l'utilisateur `suivi_delivery` : `\dt` suffit) ;
- `\d installations` : les colonnes et les contrôles d'une table ;
- `select * from databasechangelog;` : ce que Liquibase a appliqué ;
- `\q` : quitter.

Un outil graphique comme DBeaver peut aussi s'y connecter : `localhost:5432`, base `suivi_delivery`, utilisateur `suivi_delivery`. La base n'est ouverte que sur ce poste.

## 6. Comment l'API utilise la base

Le code est dans [app/storage_postgres.py](../backend/app/storage_postgres.py) et [app/transactions.py](../backend/app/transactions.py). Le guide du code l'explique en détail : [comprendre-le-code/03-stockage.md](comprendre-le-code/03-stockage.md).

- **Les routes ne connaissent pas la base.** Elles utilisent `storage.modules.list_all(...)`, `add(...)`, etc. C'est le stockage qui traduit ces opérations en SQL.
- **Une transaction par requête.** Tout ce que fait une requête est enregistré ensemble, juste avant d'envoyer la réponse. Une erreur imprévue (500) annule tout.
- **Une écriture à la fois.** Une requête qui modifie prend d'abord un verrou de la base. Le contrôle de cohérence (`app/consistency.py`) voit donc toujours des données à jour, même avec **plusieurs exemplaires** de l'API.
- **Saisie incohérente.** La saisie est faite « pour voir » dans un point de sauvegarde de la transaction. Si elle casse une règle, on revient à ce point (409) et rien n'est modifié.
- **Filet de sécurité.** Si la base refuse une saisie que l'API aurait laissée passer (doublon, lien manquant…), l'API répond 409 « Saisie refusée par la base de données », et non une erreur 500.
- **Sans base** (`APP_DB_HOST` absente), l'API garde ses données **en mémoire**. Elles sont perdues à l'arrêt : c'est pratique pour les tests et les essais rapides.

Réglages (variables d'environnement, [app/settings.py](../backend/app/settings.py)) :

| Variable | Rôle | Défaut |
| --- | --- | --- |
| `APP_DB_HOST` | adresse du serveur PostgreSQL | aucune : données en mémoire |
| `APP_DB_PORT` | port | `5432` |
| `APP_DB_NAME` | nom de la base | `suivi_delivery` |
| `APP_DB_SCHEMA` | schéma de nos tables (l'API s'y place à la connexion : `search_path`) | `suivi_delivery` |
| `APP_DB_USER` | utilisateur | `suivi_delivery` |
| `APP_DB_PASSWORD` | mot de passe (obligatoire avec `APP_DB_HOST`) | aucun |

Lancer l'API sur le poste avec la base du poste :

```bash
./deployment/docker-deploy.zsh postgres
```

```bash
./deployment/docker-deploy.zsh liquibase
```

```bash
cd backend && APP_DB_HOST=localhost APP_DB_PASSWORD=$(sed -n 's/^POSTGRES_PASSWORD=//p' ../deployment/docker.env) uv run python -m app --reload
```

`$(sed -n 's/^POSTGRES_PASSWORD=//p' ../deployment/docker.env)` lit le mot de passe de la base dans `docker.env` : il n'est écrit nulle part ailleurs (le script le tire au hasard quand il crée ce fichier).

## 7. Les tests

Les tests tournent de deux façons :

- **en mémoire** : `uv run pytest`, rapide, sans rien installer ;
- **sur une vraie base** : exactement les mêmes tests, plus ceux qui n'ont de sens qu'avec une base (données relues après un redémarrage, transaction annulée, refus de la base…).

La base des tests est **vidée avant chaque test**. Son nom doit donc finir par `_tests`, pour ne jamais effacer une base qui sert. Sur le poste, une fois `./deployment/docker-deploy.zsh postgres` lancé :

```bash
docker exec suivi-delivery-postgres-local createdb -U suivi_delivery suivi_delivery_tests
```

```bash
docker exec suivi-delivery-postgres-local psql -U suivi_delivery -d suivi_delivery_tests -c "create schema suivi_delivery"
```

```bash
docker run --rm --network suivi-delivery-local --env-file deployment/docker.env -e "LIQUIBASE_COMMAND_URL=jdbc:postgresql://suivi-delivery-postgres-local:5432/suivi_delivery_tests?currentSchema=suivi_delivery" suivi-delivery-liquibase-local
```

```bash
cd backend && TESTS_DB_HOST=localhost TESTS_DB_NAME=suivi_delivery_tests TESTS_DB_PASSWORD=$(sed -n 's/^POSTGRES_PASSWORD=//p' ../deployment/docker.env) uv run pytest
```

(Le `-e` remplace l'adresse de `docker.env` par celle de la base des tests ; l'utilisateur et le mot de passe restent ceux de `docker.env`.)

Les variables s'appellent `TESTS_DB_*` et non `APP_DB_*` : lancer les tests dans un terminal réglé pour l'API ne touche donc pas à sa base. La CI fait les deux passages (voir [ci.md](ci.md)).

## 8. Sauvegarde

Sur le poste, les données sont dans le volume Docker `suivi-delivery-postgres-local`. Pour en faire une copie (un fichier SQL lisible, qui se recharge avec `psql`) :

```bash
docker exec suivi-delivery-postgres-local pg_dump -U suivi_delivery -d suivi_delivery > sauvegarde.sql
```

La copie contient les deux schémas : nos données, et les comptes de Keycloak.

En production, la sauvegarde est l'affaire de l'équipe qui fournit la base (ou de l'opérateur PostgreSQL d'OpenShift). Elle est à prévoir avant la mise en service.
