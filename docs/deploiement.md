# Réglages et déploiement

## 1. Le principe

**Une seule version de chaque application, qui marche partout.** Ce qui change d'une installation à l'autre (adresses, ports, fichier des données, nom de l'instance) ne se trouve pas dans le code : on le donne **au lancement**, par des *variables d'environnement*.

- **Sans variable**, les valeurs par défaut sont celles du développement sur un poste : rien à régler en local.
- **Une fois mises en conteneur** (Docker, puis OpenShift), ce sont les mêmes variables qui sont renseignées.

**Version légère** : deux programmes seulement, l'API (backend, avec ses données dans un fichier SQLite) et l'interface (frontend). **Pas de connexion** : tout le monde peut tout faire, l'interface est à réserver à un réseau de confiance.

## 2. Les réglages

### Backend (l'API)

| Variable | Rôle | Défaut |
| --- | --- | --- |
| `APP_HOST` | Adresse d'écoute : `127.0.0.1` = ce poste seulement ; `0.0.0.0` = joignable depuis l'extérieur (obligatoire dans un conteneur) | `127.0.0.1` |
| `APP_PORT` | Port d'écoute | `8000` |
| `APP_LOG_LEVEL` | Détail des journaux : `critical`, `error`, `warning`, `info`, `debug`, `trace` | `info` |
| `APP_DOCS` | Documentation Swagger (`/api/docs`) visible : `oui` ou `non` | `oui` |
| `APP_DB_FILE` | Fichier de la base SQLite, créé s'il n'existe pas, avec ses tables ([sqlite.md](sqlite.md)). **Sans lui, les données sont en mémoire et perdues à l'arrêt** (essais, tests) | aucun (image Docker : `/data/suivi-delivery.sqlite`) |

Code : `backend/app/settings.py`. Une valeur invalide arrête le démarrage avec « Réglage invalide : … ».

### Frontend (l'interface)

| Variable | Rôle | Défaut |
| --- | --- | --- |
| `API_URL` | Adresse **et port** de l'API, appelée par le serveur Next.js (jamais par le navigateur). Sans `/` final | `http://127.0.0.1:8000` |
| `PORT` | Port d'écoute du site. En développement, il se donne au lancement (`PORT=3000 npm run dev`), pas dans `.env` | `5173` en développement, `8080` déployé |
| `INSTANCE_NAME` | Nom affiché dans un bandeau en haut de page et dans le titre de l'onglet (ex. `recette`) | vide : pas de bandeau |
| `INSTANCE_COLOR` | Couleur du bandeau (ex. `#2f9e44`, `green`) | rouge si le nom est `prod` ou `production`, orange sinon |

Tous ces réglages sont lus **au lancement** du serveur Next.js, et non à la construction du site : la même image sert pour toutes les instances. Code : `frontend/lib/settings.ts`.

### Script de données de démonstration

| Variable | Rôle | Défaut |
| --- | --- | --- |
| `API_URL` | Adresse de l'API à remplir (la même que celle du frontend). Un paramètre sur la ligne de commande est prioritaire | `http://127.0.0.1:8000` |

## 3. Comment les services se trouvent

```Plaintext
navigateur ──► frontend : serveur Next.js (PORT) ──── API_URL ────► backend (APP_HOST:APP_PORT) ──► fichier SQLite (APP_DB_FILE)
```

- Le **navigateur ne connaît que l'adresse du frontend**. Il ne parle jamais à l'API : il reçoit des pages déjà prêtes, préparées par le serveur Next.js.
- Le **serveur Next.js connaît le backend** par `API_URL`, qui contient son adresse et son port. C'est lui qui lit et écrit dans l'API.
- **Le backend n'a donc pas besoin d'être ouvert vers l'extérieur** : seul le frontend l'est. Sur OpenShift, une NetworkPolicy (une règle réseau du cluster) n'autorise que le frontend à le joindre.
- Le frontend cherche l'adresse du backend **à chaque appel**. Les deux applications sont donc **indépendantes** :
  - le frontend démarre même si le backend n'est pas lancé. L'interface s'affiche avec le message « Les données sont momentanément indisponibles » jusqu'à ce que le backend soit là ;
  - un backend relancé, même s'il change d'adresse interne, est retrouvé tout seul : pas besoin de relancer le frontend.

Exemple de valeurs sur OpenShift (posées par le chart Helm) :

| Application | Variable | Valeur |
| --- | --- | --- |
| Backend | `APP_HOST`, `APP_PORT` | `0.0.0.0`, `8000` |
| Backend | `APP_DB_FILE` | `/data/suivi-delivery.sqlite`, sur le disque `<installation>-data` |
| Backend | `APP_DOCS` | `non` en production de l'outil |
| Frontend | `PORT` | `8080` |
| Frontend | `API_URL` | `http://suivi-delivery-backend:8000` : nom du service backend, puis son port |
| Frontend | `INSTANCE_NAME` | `recette` ou `prod` |

Le nom court du service suffit : le serveur de noms (DNS) du cluster le complète.

## 4. Régler en local

**Backend** (depuis `backend/`), au choix :

- directement sur la ligne de commande :

  ```bash
  APP_PORT=9000 APP_DB_FILE=donnees/suivi-delivery.sqlite uv run python -m app --reload
  ```

- ou avec un fichier `.env` : copier `backend/.env.example` en `backend/.env`, l'adapter, puis lancer :

  ```bash
  uv run --env-file .env python -m app --reload
  ```

**Frontend** (depuis `frontend/`), au choix :

- directement sur la ligne de commande :

  ```bash
  INSTANCE_NAME=recette npm run dev
  ```

- ou avec un fichier `.env` : copier `frontend/.env.example` en `frontend/.env` et l'adapter. `npm run dev` le lit tout seul (sauf `PORT`, à donner sur la ligne de commande).

Les fichiers `.env` et les bases SQLite restent sur votre poste : ils ne sont pas envoyés sur GitHub.

## 5. Une fois déployé : le serveur Next.js

En développement, `npm run dev` fait tourner le serveur Next.js et le recharge à chaque modification.

Pour le déploiement, le site est construit (`npm run build`) en un **serveur autonome** (`.next/standalone`, voir `frontend/next.config.ts`). C'est un seul programme Node.js (`node server.js`), avec seulement les bibliothèques nécessaires. Il sert les pages, lit l'API et répond à la probe `/health`. Il n'y a pas de serveur web à part (comme nginx) : le serveur Next.js fait tout.

## 6. Les images Docker

**Règle : des Docker Hardened Images quand elles existent, sinon uniquement des images publiées par l'éditeur du logiciel.**

Les **Docker Hardened Images** (registre `dhi.io`, publiées par Docker) sont réduites au strict nécessaire : pas de shell ni de gestionnaire de paquets dans l'image d'exécution, utilisateur non root, presque aucune faille connue, signées et accompagnées de la liste de leur contenu. Une variante `-dev` (avec shell) sert à l'étape de fabrication. Il faut **se connecter** avec un compte Docker (identifiant Docker Hub, jeton d'accès personnel en lecture seule comme mot de passe) : soit une fois à la main, `docker login dhi.io` (ou `podman login dhi.io`), soit en remplissant `DHI_USERNAME` et `DHI_TOKEN` dans `deployment/docker.env` : les scripts `docker-deploy` et `k8s-deploy` se connectent alors eux-mêmes avant de fabriquer les images (§ 7). Pour entrer dans un conteneur sans shell : `docker debug <conteneur>`.

| Usage | Image | Éditeur |
| --- | --- | --- |
| Backend (fabrication) | `dhi.io/python:3.14.8-debian13-dev` + uv recopié de `dhi.io/uv:0.13.4-debian13` | Docker Hardened Images |
| Backend (exécution) | `dhi.io/python:3.14.8-debian13` | Docker Hardened Images |
| Frontend (fabrication) | `dhi.io/node:26.12.1-alpine3.24-dev` | Docker Hardened Images |
| Frontend (exécution) | `dhi.io/node:26.12.1-alpine3.24` | Docker Hardened Images |

Pour comprendre une étiquette : `dhi.io/python:3.14.8-debian13-dev` = Python **3.14.8** (version exacte, figée), système **Debian 13**, variante **dev** (avec shell, pour l'étape de fabrication ; sans `-dev` : l'image d'exécution). `dhi.io/node:26.12.1-alpine3.24` = Node **26.12.1**, système **Alpine 3.24** (plus petit que Debian).

Pour limiter les failles de sécurité :

- **Seul le nécessaire va dans l'image finale.** Chaque Dockerfile a deux étapes : un « atelier » qui fabrique, jeté ensuite, puis l'image finale qui ne reçoit que le résultat.
- **Ni uv ni shell** dans l'image finale du backend : uv installe les dépendances (versions et empreintes de `uv.lock`) à l'étape de fabrication, dans un environnement sans pip. Le pip de Debian reste dans l'image durcie (sans shell, impossible de l'en retirer), mais l'API ne s'en sert pas. L'image du frontend, elle, ne fait que copier le site construit avant.
- **Rien n'est téléchargé ni mis à jour dans les images** (ni `apt-get upgrade`) : les failles de l'image de base (système, npm…) se corrigent **en changeant la version de l'image de base**.
- **Next.js n'envoie pas de statistiques d'usage** (`NEXT_TELEMETRY_DISABLED=1`), et ne s'annonce pas dans les réponses (pas d'en-tête `X-Powered-By`).
- **Reconstruire les images régulièrement**, au moins une fois par mois et à chaque alerte de sécurité.
- **Prêtes pour OpenShift**. OpenShift lance les conteneurs avec un utilisateur pris au hasard (du groupe 0) : les images tournent donc sans droits administrateur.
  - Le backend n'écrit que dans `/data` (le fichier SQLite), un dossier donné au groupe 0 à la fabrication, où l'on monte un volume (sinon les données sont perdues avec le conteneur).
  - Le frontend n'écrit que dans le cache de Next.js (`.next/cache`).
- **Changer de version majeure se décide à la main**, après un essai : Debian 14 (forky) vers 2027, une nouvelle version de Python ou de Node.js.

**Publication** : pour OpenShift, les images sont publiées par la CI dans un registre (`ghcr.io/florent-coulon-deville/…` sur GitHub), à la sortie de chaque version (étiquette Git `vX.Y.Z`). Voir [docs/ci.md § 5](ci.md#5-publier-les-images--sortir-une-version).

## 7. Tester avec Docker sur son poste

Pré-requis : Docker Desktop démarré (ou Podman : voir [Avec Podman au lieu de Docker](#avec-podman-au-lieu-de-docker)). Toutes les commandes se lancent **depuis la racine du projet**.

### Les modules et le fichier de réglages

Deux modules, chacun avec son dossier, son `Dockerfile` et son modèle de réglages :

| Module | Rôle | Modèle de réglages |
| --- | --- | --- |
| `backend` | l'API ; ses données dans un fichier SQLite, dans le volume `suivi-delivery-data-local` (monté sur `/data`) | `backend/docker.example.env` |
| `frontend` | l'interface | `frontend/docker.example.env` |

**Un seul fichier de réglages**, `deployment/docker.env`, non suivi par Git. S'il n'existe pas, le script le crée en mettant bout à bout `deployment/docker.example.env` (réglages du script : `DHI_USERNAME`, `DHI_TOKEN`) puis les modèles des deux modules. Chaque conteneur reçoit tout le fichier (`--env-file`, sans `-e`) et ignore ce qui ne le concerne pas. `DHI_USERNAME` et `DHI_TOKEN` ne sont **jamais** transmis aux conteneurs : le script leur donne une copie provisoire sans ces lignes.

Un `docker.env` d'une version précédente (avec PostgreSQL et Keycloak, sans `APP_DB_FILE`) est refusé avec un message : le mettre de côté (`mv deployment/docker.env deployment/docker.env.ancien`), puis relancer, le script en recrée un.

### Le plus simple : le script `docker-deploy.zsh` (ou `docker-deploy.ps1`)

```bash
./deployment/docker-deploy.zsh                    # tout : backend, puis frontend ; données CONSERVÉES
./deployment/docker-deploy.zsh backend            # l'API seule
./deployment/docker-deploy.zsh frontend           # l'interface seule
./deployment/docker-deploy.zsh --reset            # tout, en EFFAÇANT les données (repartir de zéro)
./deployment/docker-deploy.zsh backend --reset    # l'API seule, en effaçant les données
```

```powershell
.\deployment\docker-deploy.ps1                    # Windows, PowerShell 7 (pwsh), mêmes options
```

Le script, dans l'ordre :

1. **vérifie** Docker, les Dockerfile, `docker.env` (créé s'il manque) et que les ports du poste sont libres. Rien n'est encore modifié ;
2. **fabrique les images** (après s'être connecté à `dhi.io` si `DHI_USERNAME` et `DHI_TOKEN` sont remplis). Une image qui ne se fabrique pas laisse les conteneurs en place ;
3. **remplace les conteneurs** : supprime les anciens, crée le réseau `suivi-delivery-local` et le volume des données s'ils manquent (`--reset` efface d'abord le volume) ;
4. **lance** l'API, puis l'interface, et attend qu'elles répondent (`/readyz`, `/health`) ;
5. **affiche** les adresses.

| Quoi | Adresse |
| --- | --- |
| Interface | <http://localhost:8080> |
| API (Swagger, développement seulement) | <http://localhost:8000/api/docs> |

Pour avoir quelque chose à regarder : `uv run python scripts/load_demo.py` depuis `backend/` (données de démonstration, chargées par l'API du poste).

### Avec Podman au lieu de Docker

**Podman** est un autre programme qui fabrique et lance des conteneurs, publié par Red Hat. Il n'a pas besoin de droits administrateur. Ses commandes sont les mêmes que celles de Docker : les scripts savent donc utiliser l'un ou l'autre.

```bash
./deployment/podman-deploy.zsh                    # comme docker-deploy.zsh, mêmes modules et options
./deployment/podman-deploy.zsh backend --reset    # l'API seule, en effaçant les données
```

```powershell
.\deployment\podman-deploy.ps1                    # Windows, PowerShell 7
```

`podman-deploy` n'est qu'un raccourci : il lance `docker-deploy` avec l'option `--podman`. Tout le reste est commun : le déroulé, les vérifications et `deployment/docker.env`.

- **Pré-requis** : Podman installé et, sur Mac ou Windows, sa machine démarrée (`podman machine start`). Le script le vérifie.
- **Mêmes noms, mêmes ports** que Docker. Mais Podman a **ses propres images, son réseau et son volume**, donc ses propres données : les deux ne se voient pas.
- Ne pas faire tourner Docker et Podman en même temps : si l'un tient déjà un port, le script s'arrête avant de rien modifier.

### Les ports utilisés sur le poste

| Conteneur | Port du poste | Port dans le conteneur (réglage) | Adresse |
| --- | --- | --- | --- |
| Frontend | **8080** | 8080 (`PORT`) | <http://localhost:8080> |
| Backend (développement seulement) | **8000** | 8000 (`APP_PORT`) | <http://localhost:8000/api/docs> |

Lecture de l'option `-p` : **`-p <port du poste>:<port dans le conteneur>`**. Pour changer un port du poste, on ne modifie que le premier nombre (en haut du script). Le frontend joint le backend par le réseau Docker (`API_URL=http://suivi-delivery-backend-local:8000`), jamais par un port du poste.

### Les commandes à retaper (sans le script)

```bash
docker build -t suivi-delivery-backend-local backend
docker build -t suivi-delivery-frontend-local frontend
docker network create suivi-delivery-local
docker volume create suivi-delivery-data-local
docker run -d --name suivi-delivery-backend-local --network suivi-delivery-local -p 8000:8000 \
  --env-file deployment/docker.env -v suivi-delivery-data-local:/data suivi-delivery-backend-local
docker run -d --name suivi-delivery-frontend-local --network suivi-delivery-local -p 8080:8080 \
  --env-file deployment/docker.env suivi-delivery-frontend-local
```

(Avec ces commandes, les lignes `DHI_*` de `docker.env` sont transmises aux conteneurs ; le script, lui, les retire.)

### Tout supprimer

On supprime les conteneurs, puis le réseau. Le volume ne se supprime que si l'on veut **effacer les données**.

```bash
docker rm -f suivi-delivery-frontend-local suivi-delivery-backend-local
docker network rm suivi-delivery-local
docker volume rm suivi-delivery-data-local
```

### En cas de problème

| Symptôme | Où regarder |
| --- | --- |
| Un conteneur s'arrête tout de suite (absent de `docker ps`) | `docker logs <nom>`. Un réglage invalide est signalé par « Réglage invalide : … » |
| Le site s'affiche mais « Les données sont momentanément indisponibles » | Normal si le backend n'est pas lancé : `./deployment/docker-deploy.zsh backend`. Sinon : `API_URL` contient-il bien `suivi-delivery-backend-local` et le même port que `APP_PORT` ? Le détail est dans `docker logs suivi-delivery-frontend-local` (« API injoignable ») |
| « port is already allocated », ou le script s'arrête sur un port déjà utilisé | Le port du poste est déjà pris (souvent par l'API ou l'interface lancées sans Docker) : arrêter ce programme, ou changer le port en haut du script |
| Le backend s'arrête avec « Base SQLite … impossible à ouvrir » | Le dossier de `APP_DB_FILE` n'est pas modifiable : le volume doit être monté sur `/data` |
| Le backend s'arrête avec « structure … plus récente » | La base a été préparée par une version plus récente de l'API : installer cette version, ou repartir de zéro (`--reset`) |
| Le script s'arrête : « `docker.env` date d'une version précédente » | Mettre `docker.env` de côté et relancer (voir plus haut) |

## 8. Kubernetes / OpenShift : les probes

Kubernetes interroge régulièrement chaque pod pour savoir où il en est. L'API répond sur trois adresses, **hors de `/api`** et **sans aucune donnée** :

| Probe | Adresse | Question | Si elle échoue |
| --- | --- | --- | --- |
| **Startup** | `/startupz` | As-tu fini de démarrer (base ouverte, tables présentes) ? | Kubernetes attend ; au-delà du délai, il redémarre le pod |
| **Readiness** | `/readyz` | Peux-tu recevoir des appels (démarrée, et la base répond) ? | le pod ne reçoit plus d'appels, sans être redémarré |
| **Liveness** | `/livez` | Es-tu encore en vie ? Répondre suffit | Kubernetes redémarre le pod |

Réponse : **200** `{"status": "ok"}`, ou **503** `{"status": "unavailable", "detail": "…"}`.

La liveness ne vérifie volontairement rien d'autre : un souci passager doit seulement retirer le pod du trafic (readiness), pas le faire redémarrer en boucle. Réglage dans `helm/suivi-delivery/templates/backend-deployment.yaml` :

```yaml
startupProbe:
  httpGet: { path: /startupz, port: 8000 }
  periodSeconds: 2
  failureThreshold: 30      # jusqu'à 60 s pour démarrer
readinessProbe:
  httpGet: { path: /readyz, port: 8000 }
  periodSeconds: 10
livenessProbe:
  httpGet: { path: /livez, port: 8000 }
  periodSeconds: 20
  failureThreshold: 3
```

**Le frontend** répond sur `/health` (port 8080), même si l'API est arrêtée : `livenessProbe` et `readinessProbe` utilisent cette seule adresse.

## 9. Installer sur un cluster

Deux façons, qui installent exactement la même chose (le chart Helm du projet, [helm/suivi-delivery/README.md](../helm/suivi-delivery/README.md)) :

| | Pour qui | Ce qu'il faut |
| --- | --- | --- |
| **[9.1 Avec Helm, pas à pas](#91-avec-helm-pas-à-pas)** | une équipe OpenShift, une recette, la production : on voit et on maîtrise chaque étape | `helm`, `git` et un accès au cluster ; le chart est pris dans le dépôt Git, à l'étiquette de la version |
| **[9.2 Avec le script `k8s-deploy.zsh`](#92-avec-le-script-k8s-deployzsh)** | le développeur, sur kind ou CRC : tout en une commande | le dépôt Git cloné |

Ce qui est installé : l'API (**un seul exemplaire**, ses données sur le disque `<installation>-data`), l'interface, leurs Services, la Route (OpenShift) ou un Ingress, et une NetworkPolicy (seule l'interface joint l'API).

### 9.1 Avec Helm, pas à pas

À chaque version, la CI publie les deux images ([ci.md § 5](ci.md#5-publier-les-images--sortir-une-version)) : `ghcr.io/florent-coulon-deville/suivi-delivery-{backend,frontend}:<version>`. Le chart se prend dans le dépôt Git, à l'étiquette de la version (`vX.Y.Z`). Le chart d'une version installe les images **de la même version** : on ne choisit qu'un numéro.

**Outils** : Helm 3.8 ou plus (Helm 4 conseillé), `git`, et `oc` (OpenShift) ou `kubectl`.

```bash
VERSION=X.Y.Z
git clone --branch v$VERSION --depth 1 https://github.com/florent-coulon-deville/suivi-delivery.git suivi-delivery-$VERSION
CHART=./suivi-delivery-$VERSION/helm/suivi-delivery
```

#### Étape 1 : se connecter au cluster

```bash
oc login https://api.crc.testing:6443 -u kubeadmin   # OpenShift : la connexion devient le contexte courant
```

Helm vise **le contexte kubectl courant**. Pour en viser un autre sans en changer, ajouter `--kube-context <contexte>` à chaque commande `helm`.

#### Étape 2 : préparer les réglages de l'instance

Helm part des valeurs par défaut du chart (`values.yaml`), puis applique chaque fichier donné avec `-f`, dans l'ordre : **le dernier l'emporte**.

| Fichier | Contenu | Dans Git ? |
| --- | --- | --- |
| `values-<instance>.yaml` (ex. `values-crc.yaml`) | ce qui est **propre à l'instance** : nom affiché, couleur du bandeau, taille du disque, Route… | le modèle oui (`values-crc.example.yaml`, dans le chart), la copie non |
| `values-secret.yaml` | seulement si les images sont dans un **registre privé** : son accès (inutile pour ghcr.io) | **jamais** |

```bash
cp $CHART/values-crc.example.yaml values-crc.yaml         # réglages de l'instance, à adapter
helm show values $CHART                                   # tous les réglages possibles
```

#### Étape 3 : voir avant d'installer (facultatif)

```bash
helm template suivi-delivery $CHART -n suivi-delivery -f values-crc.yaml | less
```

Affiche tout ce qui serait créé dans le cluster, **sans rien installer**.

#### Étape 4 : installer

```bash
helm upgrade --install suivi-delivery $CHART \
  -n suivi-delivery --create-namespace -f values-crc.yaml --wait --timeout 5m
```

| Morceau | Rôle |
| --- | --- |
| `upgrade --install` | installe si l'application n'est pas là, met à jour sinon : **la même commande sert toujours** |
| `suivi-delivery` | le nom de l'installation (« release ») : il préfixe les objets créés |
| `-n … --create-namespace` | l'espace de noms, créé s'il n'existe pas (sur OpenShift, le droit de le créer peut manquer : demander le projet à l'équipe) |
| `--wait --timeout 5m` | attend que l'API et l'interface soient démarrées |

#### Étape 5 : vérifier

```bash
helm test suivi-delivery -n suivi-delivery            # un pod de test appelle l'interface et l'API, depuis le cluster
oc get pods -n suivi-delivery                         # API et interface : Running
oc get route suivi-delivery -n suivi-delivery -o jsonpath='{.spec.host}'; echo   # adresse de l'interface (HTTPS)
```

#### Étape 6 : passer à une nouvelle version

Récupérer le chart de la nouvelle version, puis la **même commande qu'à l'étape 4**. Les données sont gardées (disque conservé). L'ancienne API s'arrête avant que la nouvelle démarre (`Recreate`) ; au démarrage, la nouvelle complète la structure de la base si besoin ([sqlite.md](sqlite.md)). Historique : `helm history suivi-delivery -n suivi-delivery`.

#### Étape 7 : revenir en arrière

```bash
helm rollback suivi-delivery <révision> -n suivi-delivery --wait   # révision : la colonne REVISION de helm history
```

**Attention** : Helm remet les images et les réglages d'avant, **pas la structure de la base**. Si la nouvelle version avait ajouté un fichier de structure (`backend/app/sql/`), l'ancienne API refuse de démarrer sur cette base (« structure plus récente ») : garder une copie du fichier SQLite avant chaque mise à jour en production ([sqlite.md § Sauvegarder](sqlite.md#sauvegarder)).

#### Étape 8 : désinstaller

```bash
helm uninstall suivi-delivery -n suivi-delivery
```

Le **disque des données** est **gardé** : une réinstallation retrouve les données. Pour tout effacer vraiment : `oc delete pvc suivi-delivery-data -n suivi-delivery`.

#### Depuis une autre branche (code pas encore publié)

Prendre pour `CHART` le dossier `helm/suivi-delivery` de son dépôt de travail. Le chart cherche alors les images **de la version écrite dans `Chart.yaml`** : elles doivent être publiées (sinon, sur kind, voir 9.2, qui les fabrique sur le poste).

### 9.2 Avec le script `k8s-deploy.zsh`

Le script `k8s-deploy.zsh`, dans le dossier `deployment/`, installe (ou met à jour) l'application sur **n'importe quel cluster Kubernetes** : OpenShift, kind sur le poste, ou tout autre cluster. Il n'utilise que **kubectl** et **helm**, plus **kind** et **Docker** (ou **Podman**, avec `--podman`) quand le cluster est un kind. Le cluster visé est un **contexte kubectl** : celui en cours, ou celui donné avec `--context` (`oc login` crée le sien sur OpenShift, kind crée `kind-<nom>`).

```bash
./deployment/k8s-deploy.zsh                                    # le contexte kubectl en cours
./deployment/k8s-deploy.zsh --context kind-suivi-delivery     # kind sur le poste (cluster créé s'il manque)
./deployment/k8s-deploy.zsh --context kind-suivi-delivery --reset    # kind, en repartant de zéro
./deployment/k8s-deploy.zsh --context kind-suivi-delivery --podman   # kind sur Podman au lieu de Docker
./deployment/k8s-deploy.zsh --context crc-admin --values helm/suivi-delivery/values-crc.yaml   # avec les réglages de l'instance
```

| Option | Rôle | Défaut |
| --- | --- | --- |
| `--context <nom>` | le cluster visé | le contexte kubectl en cours |
| `--namespace <nom>` | l'espace de noms (namespace) | `suivi-delivery` |
| `--values <fichier>` | un fichier de valeurs Helm en plus (réglages de l'instance). Peut être répétée | aucun |
| `--registry <adresse>` | où le cluster télécharge les images (hors kind) | `ghcr.io/florent-coulon-deville` |
| `--yes` | ne pas demander confirmation (hors kind) | demande |
| `--reset` | supprime d'abord le cluster (kind seulement) | non |
| `--podman` | Podman au lieu de Docker (kind sur Podman, images fabriquées par Podman) | Docker |

Le script, dans l'ordre :

1. **Il vérifie** les outils, lit la version de l'application (`appVersion` de `helm/suivi-delivery/Chart.yaml`), et que le cluster répond. Toutes les commandes visent ce contexte et lui seul.
2. **Sur un vrai cluster**, il affiche l'adresse du cluster, l'espace de noms et la version, puis **demande confirmation**.
3. **Les images** :
   - **kind** : il fabrique les deux images sur le poste (`suivi-delivery-{backend,frontend}:<version>`) et les charge directement dans kind (avec `--podman` : par un fichier, `podman save` puis `kind load image-archive`). Aucun registre n'est nécessaire ;
   - **autre cluster** : le cluster télécharge `<registre>/suivi-delivery-*:<version>`, qui doivent donc être **publiées** par la CI. Le script signale celles qu'il ne trouve pas.
4. **Il installe** (ou met à jour) le chart : `helm upgrade --install`, avec `values-secret.yaml` s'il existe et les fichiers `--values`. Sur kind, le nom d'instance est « kind ».
5. **Il lance `helm test`**, qui vérifie depuis l'intérieur du cluster que l'application répond.

Le récapitulatif final donne l'adresse de l'interface (la Route sur OpenShift, sinon la commande `kubectl port-forward` à lancer, puis <http://localhost:8080>), l'état des pods, et comment tout retirer.

**Sous Windows : `k8s-deploy.ps1`**, la même chose en PowerShell 7 (`pwsh`), avec les mêmes options. Les deux scripts doivent rester identiques (mêmes options, mêmes étapes).
