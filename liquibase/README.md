# Liquibase : la structure de la base

Liquibase crée et fait évoluer les **tables** de la base PostgreSQL. Il applique, dans l'ordre, les changements qui manquent, puis s'arrête. Il passe toujours **avant** l'API, qui ne crée aucune table.

| Fichier | Rôle |
| --- | --- |
| `docker.example.env` | modèle des réglages : adresse de la base (avec le schéma), utilisateur, mot de passe (mis bout à bout avec ceux des autres modules dans `deployment/docker.env`, non suivi par Git) |
| `Dockerfile` | l'image `suivi-delivery-liquibase-local` : Liquibase 4.33.0 (Docker Hardened Image, connecteur PostgreSQL 42.7.12 inclus) + nos changements ; elle ne télécharge rien |
| `changelog/main.yaml` | la liste, dans l'ordre, des fichiers de changements |
| `changelog/001-tables.sql` | les 15 tables (schéma `suivi_delivery`), avec seulement leurs colonnes |
| `changelog/002-primary-keys.sql` … `005-index.sql` | leurs contraintes, chacune nommée (`pk_`, `uq_`, `ck_`, `fk_`), puis leurs index (`ix_`), en `alter table` |

**Règle d'or : on ne modifie jamais un changement déjà appliqué.** On en ajoute un nouveau, à la fin de `main.yaml` (voir [docs/postgresql.md § 4](../docs/postgresql.md#4-faire-évoluer-la-structure)).

Les tables vont dans le schéma de nos tables, donné dans l'adresse de la base (`?currentSchema=suivi_delivery` de `LIQUIBASE_COMMAND_URL`). Ce schéma doit exister avant Liquibase : l'image PostgreSQL du projet le crée au premier démarrage.

## Lancer

La base doit tourner (module [`postgres/`](../postgres/README.md)) :

```bash
./deployment/docker-deploy.zsh liquibase
```

Le script fabrique l'image, puis l'applique sur la base du poste, avec les réglages de `deployment/docker.env`. Il vérifie d'abord qu'ils désignent bien la base (`POSTGRES_*`).

Faire évoluer la structure, les commandes utiles (`status`, `history`, `update-sql`, `rollback`…) : [docs/postgresql.md](../docs/postgresql.md).
