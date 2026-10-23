# Chart Helm « Suivi de la delivery »

Installe tout l'outil de suivi des mises en production : l'**API** (backend), l'**interface** (frontend), **Keycloak** (comptes et connexion), la **base PostgreSQL** (ou le lien vers une base fournie) et ce qu'il leur faut. Cible : **OpenShift** ; fonctionne aussi sur un Kubernetes classique (kind pour les essais).

## Ce qui est installé

| Objet | Rôle |
| --- | --- |
| Deployment `<installation>-backend` | l'API, en `backend.replicas` exemplaires qui partagent la base ; probes `/startupz`, `/readyz`, `/livez`. Avant elle, deux conteneurs de préparation : `wait-for-database` (attend que la base réponde) et `structure` (Liquibase applique les changements de structure qui manquent, voir `docs/postgresql.md`) |
| StatefulSet et Service `<installation>-postgresql` | la base PostgreSQL intégrée (image `suivi-delivery-postgres` : l'officielle, au nom du projet, qui crée au premier démarrage le schéma de nos tables, et l'utilisateur et le schéma de Keycloak ; un exemplaire), si `database.internal: true` (par défaut). Son disque `data-<installation>-postgresql-0` est **conservé** par `helm uninstall` |
| Deployment et Service `<installation>-keycloak` | Keycloak : comptes, page de connexion, jetons (`docs/keycloak.md`). Ses pages sont servies par l'interface sous `/auth` (ni Route ni Ingress) ; sa console n'est jamais exposée. Avant lui, `wait-for-database` |
| Deployment `<installation>-frontend` | l'interface (serveur Next.js) ; probe `/health` |
| Services `-backend`, `-frontend` | adresses internes ; l'API n'est jamais exposée à l'extérieur |
| Route (OpenShift) **ou** Ingress | l'adresse publique de l'interface, en HTTPS. La Route n'est créée que sur OpenShift |
| Secret `<installation>-application` | `APP_ADMIN_PASSWORD` (mot de passe initial de l'admin, importé dans Keycloak), `APP_DB_PASSWORD`, `APP_KEYCLOAK_CLIENT_SECRET` (client de l'API dans Keycloak), `KC_DB_PASSWORD`, `KC_BOOTSTRAP_ADMIN_PASSWORD` : fournis, ou générés à la première installation puis conservés (sauf les mots de passe d'une base fournie, obligatoires) ; **jamais supprimé** par `helm uninstall` |
| Secret `<installation>-registre` | accès au registre des images, si values-secret.yaml en donne un |
| NetworkPolicy | seule l'interface (et le test Helm) peut joindre l'API ; seuls l'interface et l'API peuvent joindre Keycloak ; seuls l'API et Keycloak peuvent joindre la base intégrée |
| ServiceAccount | sans droits, sans jeton monté : l'application ne parle pas à Kubernetes |

Tous les conteneurs tournent **sans droits administrateur**, sans numéro d'utilisateur imposé sur OpenShift (il en choisit un ; ailleurs, les conteneurs de l'image PostgreSQL prennent son utilisateur `postgres`, 70), avec un système de fichiers en lecture seule, et des ressources (processeur, mémoire, disque temporaire) réservées et plafonnées.

## Version

**Le chart suit la version de l'application** : `version` et `appVersion` de `Chart.yaml` sont égales, et égales aux versions de `backend/pyproject.toml` et `frontend/package.json` (vérifié par la CI). Par défaut, le chart déploie les images de sa propre version : `suivi-delivery-backend:<version>`, `suivi-delivery-frontend:<version>`, `suivi-delivery-liquibase:<version>`, `suivi-delivery-keycloak:<version>` et `suivi-delivery-postgres:<version>` (l'image officielle de PostgreSQL, sous le nom du projet ; sa version est figée dans `postgres/Dockerfile`).

Ces images sont publiées par la CI à la sortie de chaque version (étiquette Git `vX.Y.Z`), dans `ghcr.io/florent-coulon-deville/` : voir `docs/ci.md` § 5. C'est là que le chart les cherche par défaut (`images.registry: ghcr.io/florent-coulon-deville`, placé devant le nom de chaque image). Si le dépôt est privé, donner l'accès au registre dans `values-secret.yaml` (`registry`). Pour un autre registre : changer seulement `images.registry`. Vide : noms courts, pour des images chargées à la main sur le nœud (kind).

## Deux fichiers de réglages

| Fichier | Publié | Contenu |
| --- | --- | --- |
| `values.yaml` | oui | tous les réglages **non secrets**, commentés : images, nom de l'instance, base (intégrée ou fournie, schémas), Keycloak, Route, ressources… |
| `values-secret.yaml` | **jamais** (ignoré par Git et par Helm) | les **secrets** : accès au registre des images, mot de passe initial de l'admin, mots de passe de la base (nos tables, Keycloak), clé du client de l'API dans Keycloak, administrateur de la console Keycloak. Modèle : `values-secret.example.yaml` |
| `values-<instance>.yaml` | **non** (ignoré par Git) ; le modèle `values-<instance>.exemple.yaml` oui | les réglages **non secrets propres à une instance** (nom affiché, couleur, base fournie, Route…), seulement ce qui diffère de `values.yaml`. Exemple : `values-crc.example.yaml` (OpenShift Local), à copier en `values-crc.yaml` |

Helm applique les fichiers dans l'ordre (`values.yaml`, puis chaque `-f`) : le dernier l'emporte.

Chaque réglage est vérifié par `values.schema.json` : un réglage inconnu, du mauvais type, une étiquette `latest` ou un mot de passe trop court arrêtent l'installation avec un message clair.

**Ne jamais passer de secret en `--set`** : il resterait dans l'historique du terminal. Toujours passer par `values-secret.yaml`.

## Installer

### OpenShift

Guide complet, étape par étape (connexion, fichiers de réglages, vérification, mise à jour, retour en arrière, désinstallation) : `docs/deploiement.md` § 9.1. En bref :

```bash
cp helm/suivi-delivery/values-secret.example.yaml helm/suivi-delivery/values-secret.yaml   # puis le remplir
helm upgrade --install suivi-delivery ./helm/suivi-delivery -n <area-names> \
  -f helm/suivi-delivery/values-secret.yaml -f helm/suivi-delivery/values-<instance>.yaml
helm test suivi-delivery -n <area-names>
```

**Une version publiée** : seules les images sont publiées (`ghcr.io/florent-coulon-deville/suivi-delivery-*:<version>`), pas le chart. On prend le chart dans le dépôt Git, à l'étiquette de la version :

```bash
git clone --branch v0.4.3 --depth 1 https://github.com/florent-coulon-deville/suivi-delivery.git suivi-delivery-0.4.3
helm upgrade --install suivi-delivery ./suivi-delivery-0.4.3/helm/suivi-delivery \
  -n <area-names> -f values-secret.yaml -f values-<instance>.yaml
```

**Base fournie** (par l'équipe des bases de données, un opérateur PostgreSQL…) plutôt que la base intégrée :

- réglages : `database.internal: false`, `database.host`, et si besoin `database.port`, `database.name`, `database.user`, `database.schema`, `database.keycloakUser`, `database.keycloakSchema` ;
- mots de passe dans `values-secret.yaml` : `database.password`, `database.keycloakPassword` ;
- l'équipe crée d'abord les deux schémas et l'utilisateur de Keycloak (commandes : `docs/keycloak.md` § 8). Ensuite, Liquibase crée nos tables, et Keycloak les siennes.

### kind (essais sur son poste)

Le script `k8s-deploy.zsh`, dans le dossier `deployment/` du projet, fait tout : `./deployment/k8s-deploy.zsh --context kind-suivi-delivery` crée le cluster kind s'il manque, y charge les images du poste, installe le chart et lance `helm test`. Le même script installe aussi sur OpenShift ou tout autre cluster (contexte kubectl). Voir `docs/deploiement.md` § 9.2.

## Vérification

```bash
helm lint helm/suivi-delivery --strict
docker run --rm -v "$PWD/helm/suivi-delivery:/charts/suivi-delivery:ro" quay.io/redhat-certification/chart-verifier:1.16.0 \
  verify --set profile.vendortype=developer-console /charts/suivi-delivery
```

La CI fait la même vérification (chart-verifier de Red Hat, profil `developer-console`) : voir `docs/ci.md`.

## Désinstaller

```bash
helm uninstall suivi-delivery -n <area-names>
```

Le disque de la base et le Secret de l'application sont **conservés** (pour les supprimer vraiment : `kubectl delete pvc data-<installation>-postgresql-0` et `kubectl delete secret <installation>-application`).
