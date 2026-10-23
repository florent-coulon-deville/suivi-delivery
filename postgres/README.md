# PostgreSQL : la base de données

La base du suivi de la delivery. Le `Dockerfile` reprend l'**image durcie** `dhi.io/postgres:18.6-alpine3.24` (Docker Hardened Image), sous le nom du projet (`suivi-delivery-postgres-local`), avec la **préparation de la base** au premier démarrage (`initialization/01-schemas.sh`). L'image durcie ne lance pas ce script elle-même : c'est notre point d'entrée, `start.sh`, qui s'en charge.

Une seule base, deux schémas : `suivi_delivery` (nos tables, créées ensuite par Liquibase) et `keycloak` (les tables de Keycloak, avec son propre utilisateur, qui n'a accès qu'à son schéma). Le schéma `public` reste vide.

| Fichier | Rôle |
| --- | --- |
| `Dockerfile` | l'image `suivi-delivery-postgres-local` : `FROM dhi.io/postgres:18.6-alpine3.24`, la préparation et le point d'entrée |
| `start.sh` | le point d'entrée : déclare l'utilisateur du conteneur au système (utilisateur au hasard d'OpenShift), puis au premier démarrage crée la base et lance `initialization/` sur un serveur provisoire, sans réseau ; démarre enfin PostgreSQL |
| `initialization/01-schemas.sh` | au premier démarrage (volume vide) : le schéma de nos tables (`APP_DB_SCHEMA`), l'utilisateur et le schéma de Keycloak (`KC_DB_USERNAME`, `KC_DB_PASSWORD`, `KC_DB_SCHEMA`) |
| `docker.example.env` | modèle des réglages : nom de la base, utilisateur, mot de passe (mis bout à bout avec ceux des autres modules dans `deployment/docker.env`, non suivi par Git) |

La **structure** de la base (les tables) n'est pas ici : elle est dans le module [`liquibase/`](../liquibase/README.md), qui l'applique une fois la base lancée.

## Lancer

```bash
./deployment/docker-deploy.zsh postgres
```

La base est alors joignable sur `localhost:5432`, depuis ce poste seulement. Ses données sont dans le volume Docker `suivi-delivery-postgres-local` : elles sont conservées d'un lancement à l'autre (`--reset` pour repartir de zéro).

Les commandes Docker détaillées, la consultation avec `psql` et la sauvegarde : [docs/postgresql.md](../docs/postgresql.md).

Sur un cluster (Helm), la base est installée par le chart (`database.internal`) ou fournie par l'équipe des bases de données : voir [helm/suivi-delivery/README.md](../helm/suivi-delivery/README.md).
