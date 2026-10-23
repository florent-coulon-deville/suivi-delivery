# Intégration continue (CI)

À chaque push, sur n'importe quelle branche, le code est vérifié automatiquement (les mêmes contrôles que sur votre poste), puis les images de la branche sont publiées pour pouvoir l'essayer : c'est le **pipeline snapshot**. Sur `main`, le **pipeline release** prépare les versions et publie leurs images. **Rien n'est déployé** : pas de déploiement continu (CD) pour l'instant.

## 1. Deux pipelines, faits de briques

Sur GitHub, chaque fichier de `.github/workflows/` part tout seul, en parallèle des autres : un workflow ne sait pas en attendre un autre. Pour retrouver des étapes enchaînées, comme les `stages` / `needs` de GitLab, on a **deux pipelines** qui appellent des **briques réutilisables** (`uses:`, appelées *reusable workflows* ; le `_` en tête de nom les distingue, GitHub les voulant toutes dans `.github/workflows/`) :

| Fichier | Rôle |
| --- | --- |
| `snapshot.yml` | **pipeline snapshot** : chaque push, toutes branches (sauté sur le commit de version) ; bouton *Run workflow* |
| `release.yml` | **pipeline release** : chaque push sur `main` (release-please) ; bouton pour relancer une publication |
| `_tests-backend.yml` | brique : backend, en mémoire puis sur SQLite |
| `_tests-frontend.yml` | brique : frontend |
| `_tests-helm.yml` | brique : chart Helm (chart-verifier) |
| `_version.yml` | brique : version unique |
| `_images.yml` | brique : fabrication et publication des deux images (étiquette, processeurs, cache… donnés par le pipeline) |
| `.github/actions/connexion-docker-hub/` | action du dépôt : connexion à Docker Hub, réessayée en cas de coupure (§ 3) |
| `.github/dependabot.yml` | réglages des PR de **Dependabot** : corrections de sécurité seulement, titre `fix(deps): …` (voir [git.md § 4](git.md#4-réglages-du-dépôt-github)) |
| `.github/workflows/pr-title.yml` | sur chaque PR vers `main` : le titre suit Conventional Commits (seul contrôle lancé par une PR, en lecture seule) |

```PlainText
snapshot.yml   (chaque push, toutes branches ; sauté sur le commit de version)
  étape 1 : backend · frontend · chart Helm · version          (en parallèle)
  étape 2 : images <branche>-snapshot, Intel/AMD + ARM, ghcr.io  ← seulement si l'étape 1 est verte

pr-title.yml   (chaque PR vers main) : le titre de la PR

release.yml    (chaque push sur main)
  étape 1 : release-please (met à jour sa PR de version, ou crée la version à sa fusion)
  étape 2 : si une version vient d'être créée :
            vérifier la version → backend · frontend · chart Helm (sur l'étiquette)
                                  → images <version>, Intel/AMD + ARM, ghcr.io
```

Dans l'onglet *Actions*, chaque pipeline apparaît avec son graphe. **Tout est lancé à chaque push**, sans filtre sur les fichiers modifiés (choix de l'utilisateur : pas de script maison ni d'action tierce pour le filtre) : les caches de uv, de npm et de Docker rendent rapides les parties qui n'ont pas changé (une image dont le dossier n'a pas bougé est « refabriquée » en quelques secondes). Si les durées deviennent gênantes, l'action `dorny/paths-filter` pourra être ajoutée à l'étape 1 du snapshot (surtout pas `tj-actions/changed-files`, piratée en mars 2025).

**Sur une PR**, les vérifications du push (même commit) s'affichent déjà dans la PR : l'évènement « PR » ne lance que la vérification du titre, dans son propre workflow (`pr-title.yml`), en lecture seule. Il tourne ainsi aussi sur la PR de version de release-please : GitHub ne donne à ce robot que la lecture, et refusait au démarrage le snapshot, qui demande le droit de publier des images (« workflow file issue », sans aucun job).

**Sur le commit de version** (« chore: version X.Y.Z », fusion de la PR de release-please), tous les jobs du snapshot sont sautés : `release.yml` y refait les vérifications et publie la version, inutile de tout faire deux fois. La branche de la PR de version (`release-please--branches--main`) n'a pas non plus de snapshot.

### Les vérifications

| Vérification | Ce qu'elle fait |
| --- | --- |
| **Backend** | `uv sync --frozen --no-build`, ruff (erreurs), ruff format (mise en forme), ty (types), pytest (tests, données en mémoire) |
| **Backend sur SQLite** | **les mêmes tests**, sur un vrai fichier SQLite (`TESTS_DB_FILE`, dans le dossier temporaire de la machine), dont l'API crée elle-même la structure (voir [sqlite.md](sqlite.md#les-tests)). Une erreur dans `app/sql/`, ou une différence entre la mémoire et la base, se voit tout de suite |
| **Frontend** | `npm ci --ignore-scripts`, `npm run typecheck`, `npm run build` |
| **Chart Helm** | **chart-verifier de Red Hat**, profil `developer-console` (voir ci-dessous) |
| **Version unique** | `cicd/check_versions.py` : le même numéro partout (`pyproject.toml`, `uv.lock`, `package.json`, `package-lock.json`, `Chart.yaml`) |
| **Secrets** (`_secrets.yml`) | **gitleaks v8.30.1** (image officielle `ghcr.io/gitleaks/gitleaks`) relit **tout l'historique** Git : un secret ajouté puis effacé y reste, lisible par tous (dépôt public). Complète la détection des secrets de GitHub, qui ne reconnaît que les jetons des grands fournisseurs. Secrets masqués dans le journal |
| **Titre de la PR** (PR seulement, `pr-title.yml`) | le titre suit Conventional Commits (`feat: …`, `fix: …`) : fusionnée en squash, la PR devient un commit qui porte ce titre, dont release-please déduit la version (§ 5) |

Un Dockerfile cassé se voit à l'étape « images » du snapshot (il n'y a plus de fabrication séparée « sans publication »).

**Failles connues des images (Docker Scout).** Après la publication, chaque image (snapshot comme version) passe à **Docker Scout 1.26.0**, l'outil de Docker (image officielle `docker/scout-cli`), avec le compte Docker du dépôt : il compte les failles connues (CVE) par gravité, critique, élevée, moyenne, faible, et dit lesquelles ont déjà une correction. **Rapport seulement** (choix de l'utilisateur), jamais d'échec du pipeline, à deux endroits :

- un tableau par image dans le **résumé de l'exécution** (onglet *Actions* → l'exécution → *Summary*) ;
- des **alertes** dans l'onglet **Security** → *Code scanning* du dépôt : le rapport complet (faibles comprises) est envoyé au format SARIF par l'action de GitHub `github/codeql-action/upload-sarif` (v4.38.3, figée par son empreinte), une catégorie par image (`docker-scout-backend`…). Chaque faille y est suivie d'une exécution à l'autre, rattachée au Dockerfile de l'image, et se ferme d'elle-même une fois corrigée. Les alertes sont tenues par branche.

Sur Docker Hub, l'analyse continue de Docker Scout (un seul dépôt en offre gratuite) est **activée sur `florentcoulon/suivi-delivery`**, qui contient toutes les images des versions : leurs failles s'affichent aussi sur Docker Hub et sur [scout.docker.com](https://scout.docker.com). Pour voir une image sur le poste :

```bash
docker scout quickview ghcr.io/florent-coulon-deville/suivi-delivery-backend:0.6.0
```

Premier relevé (0.5.0, Intel/AMD, version complète) : backend 0 critique / 7 élevées, frontend 2 / 1, note C. Une fois ces chiffres suivis quelque temps, on pourra décider de faire échouer le pipeline sur les failles **critiques corrigeables**.

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
| `astral-sh/setup-uv` | v10.2.0 (uv 0.13.4, comme `backend/Dockerfile`, image `astral/uv`) | `c18668ad3cf93ea998bef934396af7bb5c839dc7` | Astral |
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
2. GitHub : trouver l'empreinte de la nouvelle version, puis remplacer l'empreinte après `@` **et** la version en commentaire, dans tous les fichiers `.github/workflows/*.yml` et `.github/actions/*/action.yml` :

   ```bash
   git ls-remote --tags https://github.com/actions/checkout v7.0.1 'v7.0.1^{}'
   ```

   S'il y a deux lignes, prendre celle qui finit par `^{}` (le commit ; l'autre est l'étiquette elle-même). Pour chart-verifier, changer la version de l'image dans `_tests-helm.yml` ; les versions sont listées sur `quay.io/repository/redhat-certification/chart-verifier`.
3. Mettre à jour le tableau ci-dessus.

## 3. Sécurité

- **Droits minimaux.** GitHub : `permissions: contents: read`, la CI ne peut que lire le code ; `persist-credentials: false`, le jeton n'est pas gardé après la récupération du code.
- **Deux secrets à créer sur GitHub** (Settings → Secrets and variables → Actions) : `DHI_USERNAME` (identifiant Docker Hub) et `DHI_TOKEN` (jeton d'accès personnel Docker, droits **Read, Write, Delete**). Noms gardés de l'époque des images durcies (`dhi.io`) : c'est le compte Docker du dépôt. Ils servent à télécharger les images de base depuis Docker Hub sans y être limité, au rapport Docker Scout, et, à chaque version, à **publier sur Docker Hub** les images et le chart (d'où le droit d'écrire) ; `docker login` s'en sert directement, aucune action tierce ne les voit. Les PR venant d'un fork n'y ont pas accès : leur fabrication d'images échoue.
- **Connexion à Docker Hub tolérante aux coupures** (action du dépôt `.github/actions/connexion-docker-hub`, utilisée par `_images.yml`) : jusqu'à 5 essais, avec des pauses de 30, 60, 90 et 120 s ; ensuite, réessayer plus tard (*Re-run failed jobs*) ou refaire le secret.
- **Fabrication des images réessayée** (`_images.yml`) : un registre peut aussi ne pas répondre pendant la fabrication (vu avec dhi.io), quand BuildKit lit les images de base (« DeadlineExceeded »). L'étape de fabrication est donc écrite trois fois : l'essai 2 (après 60 s) ne se lance que si l'essai 1 a échoué, l'essai 3 (après 120 s) que si l'essai 2 a échoué. Un essai raté apparaît en orange dans le journal, sans faire échouer la tâche ; seul l'échec du troisième la fait échouer. Un Dockerfile vraiment cassé échoue donc trois fois (quelques minutes de plus). Durée maximale de ces tâches : 40 minutes.
- La publication utilise le jeton fourni automatiquement à chaque exécution (`GITHUB_TOKEN`, avec le droit `packages: write` pour les seuls jobs d'images). Il expire à la fin de l'exécution, et n'est **confié à aucune action tierce** : c'est `docker login` qui s'en sert, directement.
- **Images de version publiées seulement à la création d'une version** (fusion de la PR de version de release-please sur `main`), ou à la main pour une étiquette existante. Les snapshots sont publiés au push d'une branche du dépôt ; jamais depuis une PR venant d'un fork (pas de secrets, pas de droit d'écriture).
- **release-please** n'a que les droits du job `release-please` de `release.yml` (`contents`, `pull-requests`, `issues` en écriture), avec le jeton `GITHUB_TOKEN` de l'exécution ; aucun jeton personnel.
- **Aucun script de paquet n'est exécuté** pendant l'installation (`npm ci --ignore-scripts`), comme dans les images Docker.
- **SonarCloud** (service qui analyse la qualité du code) n'est pas dans ces workflows. Il utilise son **analyse automatique** (application GitHub de SonarSource), qui contrôle les PR et `main`.
  - Pour voir les problèmes plus tôt, avant même le commit, l'extension VS Code *SonarQube for IDE* applique les mêmes règles dans l'éditeur (voir README.md, « Dans VS Code »).
  - Ses réglages sont dans **`.sonarcloud.properties`** (racine) : version de Python (`sonar.python.version=3.14`) et code de test (`sonar.tests=backend/tests`, retiré du code de l'application par `sonar.exclusions`). Les tests sont jugés avec les règles propres aux tests.

## 4. Rendre les vérifications obligatoires

Pour qu'une PR ne puisse pas être fusionnée si une vérification échoue :

*Settings* → *Branches* → règle sur `main` → *Require status checks to pass*, puis choisir les vérifications.

Toutes les vérifications sont lancées à chaque push (§ 1) : aucune ne reste « en attente » faute de fichier modifié, on peut donc les rendre obligatoires telles quelles (pipeline snapshot : « Backend », « Frontend », « Chart Helm », « Version », « Secrets » ; workflow à part : « Titre de la PR »).

## 5. Publier les images : sortir une version

OpenShift ne fabrique pas les images : il les télécharge dans un **registre d'images**. Elles y sont publiées par la CI, **une fois par version**, jamais à chaque PR, sur **ghcr.io** et sur **Docker Hub** (les mêmes images, recopiées depuis ghcr.io). Le **chart Helm** est publié sur Docker Hub seulement ; il s'installe aussi depuis le dépôt Git, à l'étiquette de la version ([deploiement.md § 9.1](deploiement.md#91-avec-helm-pas-à-pas)).

| Registre | Images | Chart Helm |
| --- | --- | --- |
| GitHub Container Registry | `ghcr.io/florent-coulon-deville/suivi-delivery-backend:<version>`, `…-frontend:<version>` (et les snapshots) | pas publié |
| Docker Hub (**un seul dépôt public**, `florentcoulon/suivi-delivery`, compte `DHI_USERNAME`) | `docker.io/florentcoulon/suivi-delivery:backend-<version>`, `…:frontend-<version>` (versions seulement) | le même dépôt, étiquette `<version>` : `oci://registry-1.docker.io/florentcoulon/suivi-delivery` |

### Sortir une version : release-please

Le numéro de version est géré par **release-please** (outil de Google, action `googleapis/release-please-action`, workflow `release.yml`). On ne change plus jamais le numéro à la main.

**1. Donner aux PR un titre selon Conventional Commits.** Les PR sont fusionnées en squash ([git.md § 1](git.md#1-la-façon-de-travailler)) : chacune devient un seul commit sur `main`, qui porte son titre. release-please lit ces commits et en déduit la prochaine version :

| Début du message | Sens | Effet sur la version (avant la 1.0) |
| --- | --- | --- |
| `fix: …` | correction | `0.5.0` → `0.5.1` |
| `feat: …` | nouveauté | `0.5.0` → `0.6.0` |
| `feat!: …`, `fix!: …` (ou ligne `BREAKING CHANGE: …` dans le message) | change ce qui existait (API, données…) | `0.5.0` → `0.6.0` (avant la 1.0 : `bump-minor-pre-major`) ; `1.2.0` → `2.0.0` après |
| `docs:`, `refactor:`, `test:`, `build:`, `ci:`, `chore:`, `style:`, `perf:`, `revert:` | le reste | pas de nouvelle version à elle seule (`perf` et `revert` apparaissent dans le journal) |

Une précision facultative entre parenthèses : `fix(frontend): …`, `feat(api): …`. Le texte après les deux-points reste en français. La vérification « Titre de la PR » (`pr-title.yml`) refuse un titre qui ne suit pas la règle : le corriger sur GitHub suffit, la vérification se relance. Les messages des commits de la branche sont libres.

**2. Fusionner les PR comme d'habitude.** À chaque fusion sur `main`, release-please ouvre ou met à jour **une PR de version**, intitulée « chore: version X.Y.Z », qui :

- change le numéro **partout à la fois** (`release-please-config.json`, rubrique `extra-files`) : `backend/pyproject.toml`, `backend/uv.lock`, `frontend/package.json`, `frontend/package-lock.json` (deux endroits), `helm/suivi-delivery/Chart.yaml` (`version` et `appVersion`, repérées par le commentaire `# x-release-please-version`) ;
- complète **`CHANGELOG.md`** (rubriques « Nouveautés », « Corrections », etc.) ;
- note la nouvelle version dans `.release-please-manifest.json` (la dernière version sortie, point de départ du calcul).

Cette PR attend : on peut fusionner plusieurs PR, elle se met à jour à chaque fois.

**3. Sortir la version = fusionner la PR de version.** release-please pose alors l'étiquette `vX.Y.Z` et crée la *Release* GitHub (avec le journal). Puis, dans le même pipeline `release.yml` :
    - **vérifier la version** : l'étiquette est égale à la version unique, sinon arrêt ; **refus de republier une version existante** (une image publiée ne change jamais : pour corriger, on sort une nouvelle version, un `fix:`) ;
    - **refaire les vérifications** (backend, frontend, chart Helm) sur le commit de l'étiquette : une version publiée a forcément été testée ;
    - **fabriquer et publier les deux images** (backend, frontend) à partir d'images de base à jour, **pour deux types de processeurs** (voir ci-dessous). **Jamais d'étiquette `latest`** : on sait toujours quelle version tourne.

Publication ratée (panne d'un registre…) : onglet *Actions* → « Release » → *Run workflow*, en donnant l'étiquette (`v0.5.0`) : les vérifications et la publication reprennent pour elle.

**À savoir :**
    - **Réglage du dépôt requis**, une fois : *Settings* → *Actions* → *General* → *Workflow permissions* → cocher « Allow GitHub Actions to create and approve pull requests ». Sans lui, release-please ne peut pas ouvrir sa PR.
    - La PR de version est ouverte avec le jeton de la CI (`GITHUB_TOKEN`) : GitHub n'y lance **aucune vérification** (il évite ainsi les boucles). Elle ne change que des numéros et le journal ; si des vérifications deviennent obligatoires (§ 4), les lancer en fermant puis rouvrant la PR.
    - Pour la même raison, l'étiquette posée par release-please ne lance aucun workflow : tout se passe donc dans `release.yml`, dans la même exécution.
    - **Forcer un numéro** (par exemple passer en `1.0.0`) : un commit dont le message contient la ligne `Release-As: 1.0.0`.
    - Point de départ : `0.4.3` dans `.release-please-manifest.json`, et `bootstrap-sha` (le premier commit du dépôt) dans `release-please-config.json` : les commits d'avant ne sont pas relus.

**Docker Hub** (job « Docker Hub » de `release.yml`, après les images) : **un seul dépôt pour toute l'application**, `florentcoulon/suivi-delivery` (choix de l'utilisateur : une application, plusieurs images ; et Docker Scout gratuit ne suit qu'un dépôt). Les deux images de la version y sont **recopiées** depuis ghcr.io sous `<partie>-<version>` (`backend-0.7.0`…) (`docker buildx imagetools create`, avec leurs deux processeurs : rien n'est refabriqué), puis le chart est emballé (`helm package`) et publié en OCI (`helm push`) sous `<version>` : Helm range toujours un chart dans le dépôt qui porte son nom. Compte et jeton Docker du dépôt (`DHI_USERNAME`, `DHI_TOKEN`). Dépôt public. Les snapshots ne vont pas sur Docker Hub. Le chart prend ses images sur ghcr.io (`images.registry`) : celles de Docker Hub servent au `docker pull`, pas au chart. La 0.6.0 a été publiée avec l'ancien rangement, un dépôt par image (`florentcoulon/suivi-delivery-backend:0.6.0`…).

**Le chart Helm n'est pas publié sur GitHub** (décision de l'utilisateur) : il reste vérifié à chaque push (chart-verifier, § 2), et s'installe depuis Docker Hub ou depuis le dépôt Git, à l'étiquette de la version. Les versions déjà publiées dans `oci://ghcr.io/florent-coulon-deville/charts/suivi-delivery` y restent. Le paquet ne contient que les modèles de réglages (`.helmignore` écarte `values-secret*.yaml` et `values-crc.yaml`).

### Snapshots : les images de chaque branche, à chaque push

Entre deux versions, on veut pouvoir essayer le travail en cours sur un cluster. **À chaque push, sur n'importe quelle branche** (`main` comprise), le pipeline `snapshot.yml`, **une fois ses vérifications vertes**, fabrique les deux images et les publie dans **ghcr.io seulement** (jamais sur Docker Hub), sous **une étiquette par branche, écrasée à chaque push** :

| Branche | Étiquette des deux images |
| --- | --- |
| `main` | `main-snapshot` |
| `feat/export-excel` | `feat-export-excel-snapshot` |
| `Fix/Menu_Saisie` | `fix-menu_saisie-snapshot` (minuscules ; tout caractère interdit devient `-`) |

- **Écrasée** : l'étiquette désigne toujours le dernier état de la branche. Le commit d'où vient l'image est noté dans l'image (`org.opencontainers.image.revision`) : `docker buildx imagetools inspect <image> --format '{{json .Image}}'`, ou `skopeo inspect`.
- **Une étiquette par branche** : deux branches ne s'écrasent jamais l'une l'autre.
- **Jamais un numéro de version** : `0.5.0` n'est publiée que par la release (ci-dessus), une seule fois.
- **Intel/AMD et ARM** (`amd64` et `arm64`, comme une release) : OpenShift et les serveurs, et aussi un Mac à processeur ARM, qui peut récupérer et lancer un snapshot (`docker pull` prend tout seul la bonne version). Chaque image est fabriquée sur une machine GitHub de chaque processeur, puis les deux sont réunies sous `<branche>-snapshot`.
- Deux pushes rapprochés sur la même branche : le premier est annulé, seul le dernier est publié.
- **À la demande** : onglet *Actions* → « Snapshot » → *Run workflow*, choisir la branche ; case « Tout refabriquer, sans cache » pour recréer entièrement les images (images de base retéléchargées). Le bouton n'apparaît qu'une fois `snapshot.yml` sur `main` ; avant : `gh workflow run snapshot.yml --ref <branche> -f no_cache=true`.

**Installer un snapshot** avec le chart : donner l'étiquette des deux images, et `pullPolicy: Always`, sinon un nœud qui a déjà l'ancienne image sous cette étiquette la garde :

```bash
TAG=feat-export-excel-snapshot
helm upgrade --install suivi-delivery helm/suivi-delivery -f values-secret.yaml \
  --set images.backend.tag=$TAG --set images.frontend.tag=$TAG --set images.pullPolicy=Always
```

Pour qu'un Deployment reprenne une image écrasée, le relancer : `kubectl rollout restart deployment/<nom>`.

**À prévoir** : une image écrasée perd son étiquette mais reste stockée dans ghcr.io, de même que l'étiquette d'une branche supprimée. Un nettoyage régulier sera à ajouter.

### Deux types de processeurs : Intel/AMD et ARM

Une image Docker ne tourne que sur le type de processeur pour lequel elle a été fabriquée. Les serveurs, donc OpenShift, ont des processeurs **Intel/AMD** (`amd64`) ; les Mac à puce Apple ont des processeurs **ARM** (`arm64`). Sans version ARM, `docker pull` sur un Mac répond « no matching manifest for linux/arm64 ».

Le pipeline release fabrique donc chaque image **deux fois, sur une vraie machine de chaque type** fournie par GitHub (`ubuntu-24.04` et `ubuntu-24.04-arm`) : aucune émulation, aucun outil en plus. Puis :

| Étape (job) | Ce qu'elle publie |
| --- | --- |
| `build` de `_images.yml` (4 en parallèle : 2 images × 2 processeurs) | `suivi-delivery-backend:<version>-amd64`, `…:<version>-arm64`, idem pour le frontend |
| `merge` de `_images.yml` (`docker buildx imagetools create`, commande de Docker) | `suivi-delivery-backend:<version>` et `suivi-delivery-frontend:<version>`, qui renvoient chacune vers les deux précédentes |

On utilise toujours `<version>` (sans suffixe) : `docker pull`, comme OpenShift, y prend tout seul la version qui convient à la machine. Les étiquettes `-amd64` et `-arm64` ne servent qu'à l'assemblage.

Vérifier, sans connexion (les images sont publiques) :

```bash
docker buildx imagetools inspect ghcr.io/florent-coulon-deville/suivi-delivery-backend:0.5.0
```

La réponse doit lister `linux/amd64` et `linux/arm64`.

### Qui peut télécharger les images

Les images sont **publiques** (dépôt public depuis le 2026-10-23) : tout le monde peut les télécharger **sans connexion**, `docker pull` comme le cluster. Rien à donner au chart pour ghcr.io.

Une image de `ghcr.io` ne prend la visibilité du dépôt qu'**à sa création** : passer le dépôt en public n'a pas rendu publiques les images déjà publiées. Chacune a été passée en public à la main (profil GitHub → *Packages* → l'image → *Package settings* → *Change visibility*) ; une nouvelle image, créée depuis, l'est d'office.

Seule la **publication** demande une connexion : la CI la fait avec son jeton `GITHUB_TOKEN` (droit `packages: write`).

L'accès au registre du chart (`registry` de `values-secret.yaml`) ne sert plus que pour un **registre privé** (un miroir d'entreprise, par exemple) : adresse, compte de préférence « robot » en lecture seule, et un jeton, jamais un vrai mot de passe.
