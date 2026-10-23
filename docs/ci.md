# Intégration continue (CI)

À chaque pull request vers `main`, et à chaque fusion dans `main`, le code est vérifié automatiquement : les mêmes contrôles que sur votre poste. **Rien n'est déployé** : pas de déploiement continu (CD) pour l'instant.

**Les images Docker ne sont publiées qu'à la sortie d'une version** (étiquette Git `vX.Y.Z`, posée par release-please quand on fusionne sa PR de version), dans un registre d'images où OpenShift va les chercher : voir § 5.

Fichiers (GitHub Actions) : `.github/workflows/ci-backend.yml`, `ci-frontend.yml`, `ci-docker.yml`, `ci-helm.yml`, `ci-version.yml`, `ci-pr-title.yml` ; versions : `release.yml` (release-please), qui appelle la publication : `publication.yml` ; snapshots : `snapshot.yml`.

## 1. Les vérifications

Chacune ne se lance que si les fichiers qui la concernent ont changé.

| Vérification | Se lance si ça change dans… | Ce qu'elle fait |
| --- | --- | --- |
| **Backend** | `backend/` | `uv sync --frozen --no-build`, ruff (erreurs), ruff format (mise en forme), ty (types), pytest (tests, données en mémoire) |
| **Backend sur PostgreSQL** | `backend/`, `liquibase/`, `postgres/` | une base PostgreSQL de test (`dhi.io/postgres:18.6-alpine3.24` ; le schéma `suivi_delivery` y est créé par `psql`, comme le fait l'image du projet), sa structure appliquée par l'image Liquibase du projet (module `liquibase/`), puis **les mêmes tests** sur cette base (voir [postgresql.md § 7](postgresql.md#7-les-tests)). Un changement Liquibase cassé, ou une différence entre la mémoire et la base, se voit tout de suite |
| **Frontend** | `frontend/` | `npm ci --ignore-scripts`, `npm run typecheck`, `npm run build` |
| **Images Docker** | `backend/`, `frontend/`, `liquibase/`, `keycloak/`, `postgres/` | prépare ce que les images copient (dépendances du backend, site du frontend, ), puis construit les cinq images (backend, frontend, Liquibase, Keycloak, PostgreSQL), **sans les publier** : un Dockerfile cassé se voit tout de suite |
| **Chart Helm** | `helm/suivi-delivery/` | **chart-verifier de Red Hat**, profil `developer-console` (voir ci-dessous) |
| **Version unique** | fichiers de version (`pyproject.toml`, `uv.lock`, `package.json`, `package-lock.json`, `Chart.yaml`) | `cicd/check_versions.py` : le même numéro partout |
| **Titre de la PR** | toujours (chaque PR, et à chaque changement de titre) | le titre suit Conventional Commits (`feat: …`, `fix: …`) : fusionnée en squash, la PR devient un commit qui porte ce titre, dont release-please déduit la version (§ 5) |

Modifier le fichier de CI lui-même relance la vérification concernée.

**Backend (uv) : `--frozen --no-build` sur chaque commande uv** (`uv sync` comme `uv run`), exigé par SonarCloud.

Options de uv :

- `--frozen` : uv prend exactement les versions de `uv.lock`, sans rien recalculer ni mettre à jour ;
- `--no-build` : uv n'installe que des paquets déjà fabriqués (« wheels »), il n'exécute jamais le script d'installation d'une dépendance téléchargée. Le backend lui-même n'a rien à fabriquer (pas de `[build-system]` dans `pyproject.toml`), comme dans le `Dockerfile`.

## 2. Les versions, et pourquoi elles sont figées

**Règle : une version précise, jamais « la dernière ».** Une étiquette comme `v7` ou `latest` change de contenu à chaque nouvelle version, sans prévenir. Et on évite une version publiée il y a moins de deux semaines : elle n'a pas encore fait ses preuves.

### GitHub : actions figées par leur empreinte de commit

```yaml
uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1  # v7.0.1
```

Une étiquette de version (`v7.0.1`) est comme une étiquette collée sur un carton : l'éditeur, ou quelqu'un qui aurait piraté son compte, peut la décoller et la recoller sur un autre contenu. L'**empreinte de commit** (les 40 caractères) est calculée à partir du contenu lui-même : elle ne peut pas désigner autre chose. C'est ce qu'exige SonarCloud (« Use full commit SHA hash for this dependency »). La version, en commentaire, reste là pour les humains : GitHub ne lit que l'empreinte.

Toujours l'empreinte **complète** (40 caractères), jamais une version abrégée.

| Action | Version | Empreinte | Éditeur |
| --- | --- | --- | --- |
| `actions/checkout` | v7.0.1 | `3d3c42e5aac5ba805825da76410c181273ba90b1` | GitHub |
| `astral-sh/setup-uv` | v10.2.0 (uv 0.13.4, comme `backend/Dockerfile`, image `dhi.io/uv`) | `c18668ad3cf93ea998bef934396af7bb5c839dc7` | Astral |
| `actions/setup-node` | v7.0.0 (Node 26, comme l'image du frontend) | `820762786026740c76f36085b0efc47a31fe5020` | GitHub |
| `docker/setup-buildx-action` | v4.4.1 | `f87e5991a6d7451dcb8d9637bfbc97413f497069` | Docker |
| `docker/build-push-action` | v7.4.0 | `c3c9e263c25d99ce0380d002d59b67737d91b0dc` | Docker |
| `googleapis/release-please-action` | v5.0.0 (release-please 17.6.0, Node 24) | `45996ed1f6d02564a971a2fa1b5860e934307cf7` | Google |

Le chart Helm n'utilise pas d'action : la vérification lance directement l'image de Red Hat (`quay.io/redhat-certification/chart-verifier:1.16.0`).

### Le chart Helm : chart-verifier de Red Hat

**chart-verifier** est l'outil de Red Hat qui vérifie les charts Helm destinés à OpenShift. On utilise le profil **`developer-console`**, celui des charts proposés dans la console d'OpenShift. Ses six contrôles sont tous obligatoires, et aucun ne demande de cluster :

| Contrôle | Vérifie que le chart… |
| --- | --- |
| `helm-lint` | est bien formé (`helm lint`) |
| `is-helm-v3` | est un chart Helm 3 |
| `contains-values` | a un fichier de réglages `values.yaml` |
| `contains-values-schema` | a un `values.schema.json`, qui vérifie ces réglages |
| `has-kubeversion` | indique dans `Chart.yaml` les versions de Kubernetes supportées (`kubeVersion`) |
| `has-readme` | a un `README.md` |

**Attention** : chart-verifier répond « succès » même si des contrôles échouent. La CI lit donc son rapport et échoue dès qu'une ligne `outcome: FAIL` apparaît.

Pour l'essayer sur votre poste, depuis la racine du projet :

```bash
docker run --rm -v "$PWD/helm/suivi-delivery:/charts/suivi-delivery:ro" quay.io/redhat-certification/chart-verifier:1.16.0 verify --set profile.vendortype=developer-console /charts/suivi-delivery
```

### Mettre une version à jour

1. Choisir une version publiée depuis au moins deux semaines (page « Releases » du projet de l'action, ou le registre de l'image).
2. GitHub : trouver l'empreinte de la nouvelle version, puis remplacer l'empreinte après `@` **et** la version en commentaire, dans tous les fichiers `.github/workflows/*.yml` (vérifications et publication) :

   ```bash
   git ls-remote --tags https://github.com/actions/checkout v7.0.1 'v7.0.1^{}'
   ```

   S'il y a deux lignes, prendre celle qui finit par `^{}` (le commit ; l'autre est l'étiquette elle-même). Pour chart-verifier, changer la version de l'image dans `ci-helm.yml` ; les versions sont listées sur `quay.io/repository/redhat-certification/chart-verifier`.
3. Mettre à jour le tableau ci-dessus.

## 3. Sécurité

- **Droits minimaux.** GitHub : `permissions: contents: read`, la CI ne peut que lire le code ; `persist-credentials: false`, le jeton n'est pas gardé après la récupération du code.
- **Deux secrets à créer sur GitHub** (Settings → Secrets and variables → Actions) : `DHI_USERNAME` (identifiant Docker Hub) et `DHI_TOKEN` (jeton d'accès personnel Docker, en lecture seule). Ils servent seulement à télécharger les images de base durcies (`dhi.io`) ; `docker login` s'en sert directement, aucune action tierce ne les voit. Les PR venant d'un fork n'y ont pas accès : leur fabrication d'images échoue.
- La publication utilise le jeton fourni automatiquement à chaque exécution (`GITHUB_TOKEN`, avec le droit `packages: write` pour ce seul job). Il expire à la fin de l'exécution, et n'est **confié à aucune action tierce** : c'est `docker login` qui s'en sert, directement.
- **Publication seulement à la création d'une version** (fusion de la PR de version de release-please sur `main`), ou à la main pour une étiquette existante ; jamais depuis une PR : le code d'une PR ne peut pas publier d'image.
- **release-please** n'a que les droits du job `release-please` de `release.yml` (`contents`, `pull-requests`, `issues` en écriture), avec le jeton `GITHUB_TOKEN` de l'exécution ; aucun jeton personnel.
- **Aucun script de paquet n'est exécuté** pendant l'installation (`npm ci --ignore-scripts`), comme dans les images Docker.
- **SonarCloud** (service qui analyse la qualité du code) n'est pas dans ces workflows. Il utilise son **analyse automatique** (application GitHub de SonarSource), qui contrôle les PR et `main`.
  - Pour voir les problèmes plus tôt, avant même le commit, l'extension VS Code *SonarQube for IDE* applique les mêmes règles dans l'éditeur (voir README.md, « Dans VS Code »).
  - Ses réglages sont dans **`.sonarcloud.properties`** (racine) : version de Python (`sonar.python.version=3.14`) et code de test (`sonar.tests=backend/tests`, retiré du code de l'application par `sonar.exclusions`). Les tests sont jugés avec les règles propres aux tests.

## 4. Rendre les vérifications obligatoires

Pour qu'une PR ne puisse pas être fusionnée si une vérification échoue :

*Settings* → *Branches* → règle sur `main` → *Require status checks to pass*, puis choisir les vérifications.

**Attention** : une vérification qui ne se lance pas (aucun fichier concerné modifié) est considérée comme « en attente » par une règle obligatoire, et bloque la PR. Il faudra alors ajouter une petite vérification « récapitulative » toujours lancée. À voir au moment de rendre les vérifications obligatoires.

## 5. Publier les images : sortir une version

OpenShift ne fabrique pas les images : il les télécharge dans un **registre d'images**. Elles y sont publiées par la CI, **une fois par version**, jamais à chaque PR. Sur GitHub, le **chart Helm** n'est pas publié : on l'installe depuis le dépôt Git, à l'étiquette de la version ([deploiement.md § 9.1](deploiement.md#91-avec-helm-pas-à-pas)).

| Registre | Images | Chart Helm |
| --- | --- | --- |
| GitHub Container Registry | `ghcr.io/florent-coulon-deville/suivi-delivery-backend:<version>`, `…-frontend:<version>`, `…-liquibase:<version>`, `…-keycloak:<version>`, `…-postgres:<version>` | pas publié : dossier `helm/suivi-delivery` du dépôt Git, à l'étiquette `v<version>` |

### Sortir une version : release-please

Le numéro de version est géré par **release-please** (outil de Google, action `googleapis/release-please-action`, workflow `release.yml`). On ne change plus jamais le numéro à la main.

**1. Donner aux PR un titre selon Conventional Commits.** Les PR sont fusionnées en squash ([git.md § 1](git.md#1-la-façon-de-travailler)) : chacune devient un seul commit sur `main`, qui porte son titre. release-please lit ces commits et en déduit la prochaine version :

| Début du message | Sens | Effet sur la version (avant la 1.0) |
| --- | --- | --- |
| `fix: …` | correction | `0.5.0` → `0.5.1` |
| `feat: …` | nouveauté | `0.5.0` → `0.6.0` |
| `feat!: …`, `fix!: …` (ou ligne `BREAKING CHANGE: …` dans le message) | change ce qui existait (API, données…) | `0.5.0` → `0.6.0` (avant la 1.0 : `bump-minor-pre-major`) ; `1.2.0` → `2.0.0` après |
| `docs:`, `refactor:`, `test:`, `build:`, `ci:`, `chore:`, `style:`, `perf:`, `revert:` | le reste | pas de nouvelle version à elle seule (`perf` et `revert` apparaissent dans le journal) |

Une précision facultative entre parenthèses : `fix(frontend): …`, `feat(api): …`. Le texte après les deux-points reste en français. La CI « Titre de la PR » (`ci-pr-title.yml`) refuse un titre qui ne suit pas la règle : le corriger sur GitHub suffit, la vérification se relance. Les messages des commits de la branche sont libres.

**2. Fusionner les PR comme d'habitude.** À chaque fusion sur `main`, release-please ouvre ou met à jour **une PR de version**, intitulée « chore: version X.Y.Z », qui :

- change le numéro **partout à la fois** (`release-please-config.json`, rubrique `extra-files`) : `backend/pyproject.toml`, `backend/uv.lock`, `frontend/package.json`, `frontend/package-lock.json` (deux endroits), `helm/suivi-delivery/Chart.yaml` (`version` et `appVersion`, repérées par le commentaire `# x-release-please-version`) ;
- complète **`CHANGELOG.md`** (rubriques « Nouveautés », « Corrections », etc.) ;
- note la nouvelle version dans `.release-please-manifest.json` (la dernière version sortie, point de départ du calcul).

Cette PR attend : on peut fusionner plusieurs PR, elle se met à jour à chaque fois.

**3. Sortir la version = fusionner la PR de version.** release-please pose alors l'étiquette `vX.Y.Z`, crée la *Release* GitHub (avec le journal), puis `release.yml` lance la **publication des images** (`publication.yml`). Elle :
    - vérifie que l'étiquette est égale à la version unique, sinon s'arrête ;
    - **refuse de republier une version existante** : une image publiée ne change jamais. Pour corriger, on sort une nouvelle version (un `fix:`) ;
    - fabrique les cinq images (backend, frontend, Liquibase, Keycloak, PostgreSQL) à partir d'images de base à jour, et les publie. **Jamais d'étiquette `latest`** : on sait toujours quelle version tourne.
    - fabrique chaque image **pour deux types de processeurs** (voir ci-dessous).

Publication ratée (panne de GitHub…) : onglet *Actions* → « Publication des images » → *Run workflow*, en donnant l'étiquette (`v0.5.0`).

**À savoir :**
    - **Réglage du dépôt requis**, une fois : *Settings* → *Actions* → *General* → *Workflow permissions* → cocher « Allow GitHub Actions to create and approve pull requests ». Sans lui, release-please ne peut pas ouvrir sa PR.
    - La PR de version est ouverte avec le jeton de la CI (`GITHUB_TOKEN`) : GitHub n'y lance **aucune vérification** (il évite ainsi les boucles). Elle ne change que des numéros et le journal ; si des vérifications deviennent obligatoires (§ 4), les lancer en fermant puis rouvrant la PR.
    - Pour la même raison, l'étiquette posée par release-please ne lance aucun workflow : c'est `release.yml` qui appelle la publication, dans la même exécution.
    - **Forcer un numéro** (par exemple passer en `1.0.0`) : un commit dont le message contient la ligne `Release-As: 1.0.0`.
    - Point de départ : `0.4.3` dans `.release-please-manifest.json`, et `bootstrap-sha` (le premier commit du dépôt) dans `release-please-config.json` : les commits d'avant ne sont pas relus.

**Le chart Helm n'est plus publié sur GitHub** (décision de l'utilisateur) : il reste vérifié à chaque PR (chart-verifier, § 2), et s'installe depuis le dépôt Git, à l'étiquette de la version. Les versions déjà publiées dans `oci://ghcr.io/florent-coulon-deville/charts/suivi-delivery` y restent.

### Snapshots : les images de chaque branche, à chaque push

Entre deux versions, on veut pouvoir essayer le travail en cours sur un cluster. **À chaque push, sur n'importe quelle branche** (`main` comprise), `snapshot.yml` fabrique les cinq images et les publie dans **ghcr.io seulement** (jamais sur Docker Hub), sous **une étiquette par branche, écrasée à chaque push** :

| Branche | Étiquette des cinq images |
| --- | --- |
| `main` | `main-snapshot` |
| `feat/export-excel` | `feat-export-excel-snapshot` |
| `Fix/Menu_Saisie` | `fix-menu_saisie-snapshot` (minuscules ; tout caractère interdit devient `-`) |

- **Écrasée** : l'étiquette désigne toujours le dernier état de la branche. Le commit d'où vient l'image est noté dans l'image (`org.opencontainers.image.revision`) : `docker buildx imagetools inspect <image> --format '{{json .Image}}'`, ou `skopeo inspect`.
- **Une étiquette par branche** : deux branches ne s'écrasent jamais l'une l'autre.
- **Jamais un numéro de version** : `0.5.0` n'est publiée que par la release (ci-dessus), une seule fois.
- **Intel/AMD seulement** (`amd64`) : OpenShift et les serveurs. Sur un Mac, kind fabrique ses images en local (`k8s-deploy.zsh`).
- La vérification « Images Docker » (`ci-docker.yml`, fabrication sans publication sur les PR) est gardée pour l'instant (choix de l'utilisateur).
- Deux pushes rapprochés sur la même branche : le premier est annulé, seul le dernier est publié.
- **À la demande** : onglet *Actions* → « Snapshot des images » → *Run workflow*, choisir la branche ; case « Tout refabriquer, sans cache » pour recréer entièrement les images (images de base retéléchargées). Le bouton n'apparaît qu'une fois `snapshot.yml` sur `main` ; avant : `gh workflow run snapshot.yml --ref <branche> -f no_cache=true`.

**Installer un snapshot** avec le chart : donner l'étiquette des cinq images, et `pullPolicy: Always`, sinon un nœud qui a déjà l'ancienne image sous cette étiquette la garde :

```bash
TAG=feat-export-excel-snapshot
helm upgrade --install suivi-delivery helm/suivi-delivery -f values-secret.yaml \
  --set images.backend.tag=$TAG --set images.frontend.tag=$TAG --set images.liquibase.tag=$TAG \
  --set images.keycloak.tag=$TAG --set images.postgresql.tag=$TAG --set images.pullPolicy=Always
```

Pour qu'un Deployment reprenne une image écrasée, le relancer : `kubectl rollout restart deployment/<nom>`.

**À prévoir** : une image écrasée perd son étiquette mais reste stockée dans ghcr.io, de même que l'étiquette d'une branche supprimée. Un nettoyage régulier sera à ajouter.

### Deux types de processeurs : Intel/AMD et ARM

Une image Docker ne tourne que sur le type de processeur pour lequel elle a été fabriquée. Les serveurs, donc OpenShift, ont des processeurs **Intel/AMD** (`amd64`) ; les Mac à puce Apple ont des processeurs **ARM** (`arm64`). Sans version ARM, `docker pull` sur un Mac répond « no matching manifest for linux/arm64 ».

La publication GitHub fabrique donc chaque image **deux fois, sur une vraie machine de chaque type** fournie par GitHub (`ubuntu-24.04` et `ubuntu-24.04-arm`) : aucune émulation, aucun outil en plus. Puis :

| Étape (job) | Ce qu'elle publie |
| --- | --- |
| `publish` (10 en parallèle : 5 images × 2 processeurs) | `suivi-delivery-backend:<version>-amd64`, `…:<version>-arm64`, idem pour le frontend, Liquibase, Keycloak et PostgreSQL |
| `merge` (`docker buildx imagetools create`, commande de Docker) | `suivi-delivery-backend:<version>`, `suivi-delivery-frontend:<version>`, `suivi-delivery-liquibase:<version>`, `suivi-delivery-keycloak:<version>` et `suivi-delivery-postgres:<version>`, qui renvoient chacune vers les deux précédentes |

On utilise toujours `<version>` (sans suffixe) : `docker pull`, comme OpenShift, y prend tout seul la version qui convient à la machine. Les étiquettes `-amd64` et `-arm64` ne servent qu'à l'assemblage.

Vérifier, après connexion à `ghcr.io` (`docker login ghcr.io`, avec un jeton `read:packages`) :

```bash
docker buildx imagetools inspect ghcr.io/florent-coulon-deville/suivi-delivery-backend:0.3.1
```

La réponse doit lister `linux/amd64` et `linux/arm64`.

### Qui peut télécharger les images

Une image de `ghcr.io` prend la **visibilité du dépôt** : si le dépôt est privé, les images le sont aussi. Le cluster a alors besoin d'un accès en lecture, donné dans `values-secret.yaml` du chart (`registry`) :

- `url` : `ghcr.io` ;
- `user_args` : le compte GitHub ;
- `password` : un **jeton personnel GitHub** (*Settings* → *Developer settings* → *Personal access tokens* → *Tokens (classic)*) avec **le seul droit `read:packages`**, et une date d'expiration. Jamais un vrai mot de passe.
