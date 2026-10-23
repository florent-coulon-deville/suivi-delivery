# Réglages et déploiement

## 1. Le principe

**Une seule version de chaque application, qui marche partout.** Ce qui change d'une installation à l'autre (adresses, ports, base de données, nom de l'instance) ne se trouve pas dans le code : on le donne **au lancement**, par des *variables d'environnement*.

- **Sans variable**, les valeurs par défaut sont celles du développement sur un poste : rien à régler en local.
- **Une fois mises en conteneur** (Docker, puis OpenShift), ce sont les mêmes variables qui seront renseignées.

## 2. Les réglages

### Backend (l'API)

| Variable | Rôle | Défaut |
| --- | --- | --- |
| `APP_HOST` | Adresse d'écoute : `127.0.0.1` = ce poste seulement ; `0.0.0.0` = joignable depuis l'extérieur (obligatoire dans un conteneur) | `127.0.0.1` |
| `APP_PORT` | Port d'écoute | `8000` |
| `APP_LOG_LEVEL` | Détail des journaux : `critical`, `error`, `warning`, `info`, `debug`, `trace` | `info` |
| `APP_DOCS` | Documentation Swagger (`/api/docs`) visible : `oui` ou `non` | `oui` |
| `APP_DB_HOST` | Adresse du serveur PostgreSQL. **Sans elle, les données sont en mémoire et perdues à l'arrêt** (essais, tests) | aucune |
| `APP_DB_PORT` | Port de PostgreSQL | `5432` |
| `APP_DB_NAME` | Nom de la base | `suivi_delivery` |
| `APP_DB_SCHEMA` | Schéma de nos tables dans la base (lettres minuscules, chiffres, `_`) ; « public » reste vide | `suivi_delivery` |
| `APP_DB_USER` | Utilisateur de la base | `suivi_delivery` |
| `APP_DB_PASSWORD` | Mot de passe de la base (obligatoire avec `APP_DB_HOST`) | aucun |
| `APP_KEYCLOAK_URL` | Adresse **interne** de Keycloak, avec `/auth` (ex. `http://suivi-delivery-keycloak:8080/auth`) : clés de signature des jetons, gestion des comptes | aucune : **aucun jeton accepté** |
| `APP_KEYCLOAK_REALM` | Domaine Keycloak de l'outil | `suivi-delivery` |
| `APP_KEYCLOAK_CLIENT_SECRET` | Clé du client `suivi-delivery-api` dans Keycloak (16 caractères au moins) : l'écran Comptes. **La même que celle importée dans Keycloak** | aucune : écran Comptes indisponible (503) |
| `APP_FRONTEND_URL` | Adresse publique de l'interface : Keycloak y est servi sous `/auth`, c'est l'émetteur attendu dans les jetons (`<url>/auth/realms/suivi-delivery`) | `http://localhost:8080` |
| `APP_API_URL` | Adresse publique de l'API (développement) : retour de Swagger après la connexion | aucune |

**Les secrets en production.** `APP_DB_PASSWORD` et `APP_KEYCLOAK_CLIENT_SECRET` viennent d'un **Secret** OpenShift / Kubernetes (`secretKeyRef` dans le chart Helm). L'API ne garde plus aucun mot de passe : les comptes sont dans Keycloak (réglages de Keycloak : [keycloak.md § 7](keycloak.md#7-réglages)).

Une valeur impossible (port `abc`, niveau inconnu, mot de passe trop court…) **arrête le démarrage** avec un message clair : mieux vaut ne pas démarrer que démarrer avec un réglage faux.

**Plusieurs exemplaires de l'API** peuvent tourner ensemble : ils partagent la base, et une seule saisie passe à la fois (voir [postgresql.md § 6](postgresql.md#6-comment-lapi-utilise-la-base)). La **structure** de la base (tables, colonnes) n'est pas créée par l'API, mais par **Liquibase**, lancé avant elle : voir [postgresql.md](postgresql.md).

Code : `backend/app/settings.py` (lecture et contrôle) et `backend/app/__main__.py` (lancement).

### Frontend (l'interface)

| Variable | Rôle | Défaut |
| --- | --- | --- |
| `API_URL` | Adresse **et port** de l'API, appelée par le serveur Next.js (jamais par le navigateur). Sans `/` final | `http://127.0.0.1:8000` |
| `PORT` | Port d'écoute du site. En développement, il se donne au lancement (`PORT=3000 npm run dev`), pas dans `.env` | `5173` en développement, `8080` déployé |
| `INSTANCE_NAME` | Nom affiché dans un bandeau en haut de page et dans le titre de l'onglet (ex. `recette`) | vide : pas de bandeau |
| `INSTANCE_COLOR` | Couleur du bandeau (ex. `#2f9e44`, `green`) | rouge si le nom est `prod` ou `production`, orange sinon |
| `APP_FRONTEND_URL` | Adresse publique du site, telle que la tape le navigateur (sans `/` final) : l'interface y reçoit les retours de connexion (`/login/callback`), et y sert les pages de Keycloak (`/auth`). La même valeur que pour l'API | `http://localhost:<PORT>` |
| `KEYCLOAK_URL` | Adresse **interne** de Keycloak, avec `/auth` : échange des codes contre les jetons, relais des pages de connexion | `http://127.0.0.1:8081/auth` |
| `KEYCLOAK_REALM` | Domaine Keycloak de l'outil | `suivi-delivery` |

Tous ces réglages sont lus **au lancement** du serveur Next.js, et non à la construction du site : la même image sert pour toutes les instances.

**La session** est gardée dans deux cookies protégés (voir [frontend.md § 2 bis](frontend.md#2-bis-connexion-session-et-rôles)). Quand la requête arrive en HTTPS, ces cookies sont marqués `Secure` : le navigateur ne les envoie alors qu'en HTTPS. Le serveur Next.js le sait grâce à l'en-tête `X-Forwarded-Proto`, posé par la Route OpenShift. **En production, la Route doit donc être en HTTPS.**

Code : `frontend/lib/settings.ts`.

### Script de données de démonstration

| Variable | Rôle | Défaut |
| --- | --- | --- |
| `API_URL` | Adresse de l'API à remplir (la même que celle du frontend). Un paramètre sur la ligne de commande est prioritaire | `http://127.0.0.1:8000` |
| `API_CLIENT_ID`, `API_CLIENT_SECRET` | Identifiant et clé d'un programme ADMIN (écran Comptes → Programmes) | sans eux : `API_OFFLINE_TOKEN` |
| `API_OFFLINE_TOKEN` | Jeton hors ligne d'une personne ADMIN (`uv run python -m scripts.login`) | sans lui : connexion dans le navigateur (adresse et code affichés) |
| `KEYCLOAK_URL` | Keycloak vu du navigateur (sous l'interface) | `http://localhost:8080/auth` |

## 3. Comment les services se trouvent

```Plaintext
navigateur ──► frontend : serveur Next.js (PORT) ──── API_URL ────► backend (APP_HOST:APP_PORT) ──► PostgreSQL (APP_DB_HOST:APP_DB_PORT)
                    │  /auth/… (pages de connexion)                     │ clés, comptes                 ▲
                    └──────────── KEYCLOAK_URL ────► Keycloak ◄─────────┘ APP_KEYCLOAK_URL              │
                                                         └──────────── KC_DB_URL (schéma keycloak) ─────┘
```

- **Keycloak n'est jamais joint directement par le navigateur** : ses pages de connexion passent par l'interface, sous `/auth` (même adresse que l'outil). L'API et l'interface lui parlent par son adresse interne. Voir [keycloak.md](keycloak.md).

- Le **navigateur ne connaît que l'adresse du frontend**. Il ne parle jamais à l'API : il reçoit des pages déjà prêtes, préparées par le serveur Next.js.
- Le **serveur Next.js connaît le backend** par `API_URL`, qui contient son adresse et son port. C'est lui qui lit et écrit dans l'API.
- **Le backend n'a donc pas besoin d'être ouvert vers l'extérieur** : seul le frontend l'est. Sur OpenShift, une NetworkPolicy (une règle réseau du cluster) n'autorise que le frontend à le joindre.
- Le frontend cherche l'adresse du backend **à chaque appel**. Les deux applications sont donc **indépendantes** :
  - le frontend démarre même si le backend n'est pas lancé. L'interface s'affiche avec le message « Les données sont momentanément indisponibles » jusqu'à ce que le backend soit là ;
  - un backend relancé, même s'il change d'adresse interne, est retrouvé tout seul : pas besoin de relancer le frontend.
- Le **backend** écoute sur `APP_PORT`, et sur `APP_HOST` = `0.0.0.0` dans un conteneur.

Exemple de valeurs une fois sur OpenShift (à confirmer à l'étape de déploiement) :

| Application | Variable | Valeur |
| --- | --- | --- |
| Backend | `APP_HOST` | `0.0.0.0` |
| Backend | `APP_PORT` | `8000` |
| Backend | `APP_DB_HOST`, `APP_DB_PORT`, `APP_DB_NAME`, `APP_DB_USER` | la base PostgreSQL (intégrée au chart, ou fournie) |
| Backend | `APP_DOCS` | `non` en production de l'outil |
| Backend | `APP_DB_PASSWORD`, `APP_KEYCLOAK_CLIENT_SECRET` | depuis un Secret |
| Backend | `APP_KEYCLOAK_URL` | `http://suivi-delivery-keycloak:8080/auth` |
| Frontend | `KEYCLOAK_URL` | `http://suivi-delivery-keycloak:8080/auth` |
| Frontend | `PORT` | `8080` |
| Frontend | `API_URL` | `http://suivi-delivery-backend:8000` : nom du service backend, puis son port |
| Frontend | `INSTANCE_NAME` | `recette` ou `prod` |

Le nom court du service suffit : le serveur de noms (DNS) du cluster le complète. Le nom complet (`http://<service>.<namespace>.svc.cluster.local:<port>`) marche aussi.

## 4. Régler en local

**Backend** (depuis `backend/`), au choix :

- directement sur la ligne de commande :

  ```bash
  APP_PORT=9000 uv run python -m app --reload
  ```

- avec la base PostgreSQL du poste (lancée par `./deployment/docker-deploy.zsh postgres` puis `liquibase`, voir § 7) :

  ```bash
  APP_DB_HOST=localhost APP_DB_PASSWORD=$(sed -n 's/^POSTGRES_PASSWORD=//p' ../deployment/docker.env) uv run python -m app --reload
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

Les fichiers `.env` restent sur votre poste : ils ne sont pas envoyés sur GitHub.

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
| Base de données (image `suivi-delivery-postgres`) | `dhi.io/postgres:18.6-alpine3.24`, avec notre point d'entrée (`start.sh`) qui prépare ses schémas au premier démarrage | Docker Hardened Images |
| Structure de la base (image `suivi-delivery-liquibase`) | `dhi.io/liquibase:4.33.0-debian13` (connecteur PostgreSQL 42.7.12 inclus) | Docker Hardened Images |
| Comptes et connexion (image `suivi-delivery-keycloak`) | `dhi.io/keycloak:26.7.4-debian13` + thème de l'outil + domaine importé | Docker Hardened Images |

Pour comprendre une étiquette : `dhi.io/python:3.14.8-debian13-dev` = Python **3.14.8** (version exacte, figée), système **Debian 13**, variante **dev** (avec shell, pour l'étape de fabrication ; sans `-dev` : l'image d'exécution). `dhi.io/node:26.12.1-alpine3.24` = Node **26.12.1**, système **Alpine 3.24** (plus petit que Debian).

Pour limiter les failles de sécurité :

- **Seul le nécessaire va dans l'image finale.** Chaque Dockerfile a deux étapes : un « atelier » qui fabrique, jeté ensuite, puis l'image finale qui ne reçoit que le résultat.
- **Ni uv ni shell** dans l'image finale du backend : uv installe les dépendances (versions et empreintes de `uv.lock`) à l'étape de fabrication, dans un environnement sans pip. Le pip de Debian reste dans l'image durcie (sans shell, impossible de l'en retirer), mais l'API ne s'en sert pas. L'image du frontend, elle, ne fait que copier le site construit avant.
- **Rien n'est téléchargé ni mis à jour dans les images** (ni `apt-get upgrade`) : les failles de l'image de base (système, npm…) se corrigent **en changeant la version de l'image de base**.
- **Next.js n'envoie pas de statistiques d'usage** (`NEXT_TELEMETRY_DISABLED=1`), et ne s'annonce pas dans les réponses (pas d'en-tête `X-Powered-By`).
- **Reconstruire les images régulièrement**, au moins une fois par mois et à chaque alerte de sécurité. Les étiquettes choisies suivent les correctifs : une reconstruction les récupère.
- **Prêtes pour OpenShift**. OpenShift lance les conteneurs avec un utilisateur pris au hasard (du groupe 0) : les images tournent donc sans droits administrateur.
  - Le backend n'écrit rien dans son conteneur : les données sont dans la base.
  - Le frontend n'écrit que dans le cache de Next.js (`.next/cache`).
  - Keycloak est préparé à la fabrication (`kc.sh build`), et n'écrit qu'en `/tmp` et `/opt/keycloak/data/tmp`.
  - PostgreSQL : l'image durcie ne sait pas tourner avec un utilisateur au hasard ; notre point d'entrée (`postgres/start.sh`) le déclare au système à chaque démarrage (dans `/tmp/passwd`, vers lequel renvoie `/etc/passwd` ; l'image livre ce fichier déjà rempli, sinon Podman le créerait lui-même, en root, au lancement). Ailleurs (kind), le chart le lance avec son utilisateur `postgres` (70).
- **Changer de version majeure se décide à la main**, après un essai : Debian 14 (forky) vers 2027, une nouvelle version de Python ou de Node.js.

**Publication** : pour OpenShift, les images sont publiées par la CI dans un registre (`ghcr.io/florent-coulon-deville/…` sur GitHub), à la sortie de chaque version (étiquette Git `vX.Y.Z`). Voir [docs/ci.md § 5](ci.md#5-publier-les-images--sortir-une-version).

## 7. Tester avec Docker sur son poste

Pré-requis : Docker Desktop démarré (ou Podman : voir [Avec Podman au lieu de Docker](#avec-podman-au-lieu-de-docker)). Toutes les commandes se lancent **depuis la racine du projet**.

### Les modules et le fichier de réglages

Cinq modules tournent dans Docker, chacun dans son conteneur :

| Module | Dossier | Image |
| --- | --- | --- |
| `postgres` | `postgres/` | `suivi-delivery-postgres-local` : l'image durcie `dhi.io/postgres:18.6-alpine3.24`, sous le nom du projet, qui prépare au premier démarrage le schéma de nos tables, et l'utilisateur et le schéma de Keycloak (`postgres/Dockerfile`) |
| `liquibase` | `liquibase/` | `suivi-delivery-liquibase-local`, fabriquée par `liquibase/Dockerfile` ; elle applique la structure, puis s'arrête |
| `keycloak` | `keycloak/` | `suivi-delivery-keycloak-local` : les comptes et la connexion (voir [keycloak.md](keycloak.md)) |
| `backend` | `backend/` | `suivi-delivery-backend-local` |
| `frontend` | `frontend/` | `suivi-delivery-frontend-local` |

**Un seul fichier de réglages : `deployment/docker.env`.** Il n'est pas suivi par Git : chacun a le sien.

- Chaque module a son **modèle**, `<module>/docker.example.env`, qui décrit ses réglages ; le script a le sien, `deployment/docker.example.env` (connexion à dhi.io).
- `docker.env` est fait de ces six modèles mis bout à bout.
- Le script le crée tout seul s'il n'existe pas, avec des mots de passe et des clés tirés au hasard.

Pour le créer à la main (il faut ensuite remplir les secrets vides) :

```bash
cat deployment/docker.example.env postgres/docker.example.env liquibase/docker.example.env keycloak/docker.example.env backend/docker.example.env frontend/docker.example.env > deployment/docker.env
```

**Si `docker.env` n'a pas tous les réglages attendus**, le script le dit et s'arrête. Mettre le fichier de côté (`mv deployment/docker.env deployment/docker.env.old`), puis relancer avec `--reset` : le script en recrée un, et la base repart de zéro.

| Partie | Réglages |
| --- | --- |
| Le script | `DHI_USERNAME`, `DHI_TOKEN` : connexion à dhi.io, d'où viennent les images de base (compte Docker ; sur le poste, un jeton en lecture seule suffit). Remplis : `docker-deploy` et `k8s-deploy` se connectent (`docker login`, ou `podman login` avec `--podman`, jeton passé par l'entrée standard) avant de fabriquer. Vides : ils comptent sur un `docker login dhi.io` déjà fait. **Jamais transmis aux conteneurs.** Facultatifs : un `docker.env` plus ancien, sans ces lignes, reste valable (les ajouter à la main) |
| PostgreSQL | `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD` : la base de référence |
| Liquibase | `LIQUIBASE_COMMAND_URL` (adresse JDBC de la base, avec le schéma de nos tables : `jdbc:postgresql://suivi-delivery-postgres-local:5432/suivi_delivery?currentSchema=suivi_delivery`), `LIQUIBASE_COMMAND_USERNAME`, `LIQUIBASE_COMMAND_PASSWORD` |
| Keycloak | sa base (`KC_DB_URL`, `KC_DB_USERNAME=keycloak`, `KC_DB_PASSWORD`), son adresse publique (`KC_HOSTNAME=http://localhost:8080/auth`, sous l'interface), sa console (`KC_HOSTNAME_ADMIN`, `KC_BOOTSTRAP_ADMIN_*`), et ce qu'il importe au premier démarrage : `APP_ADMIN_PASSWORD` (compte `admin` de l'outil), `APP_KEYCLOAK_CLIENT_SECRET` (lue aussi par l'API) |
| Backend | `APP_HOST=0.0.0.0`, `APP_PORT=8000`, la base (`APP_DB_HOST=suivi-delivery-postgres-local`, `APP_DB_PORT`, `APP_DB_NAME`, `APP_DB_SCHEMA`, `APP_DB_USER`, `APP_DB_PASSWORD`), `APP_LOG_LEVEL`, `APP_DOCS`, la connexion (`APP_KEYCLOAK_URL=http://suivi-delivery-keycloak-local:8080/auth`, `APP_FRONTEND_URL=http://localhost:8080`, lue aussi par le frontend et Keycloak, `APP_API_URL=http://localhost:8000`) |
| Frontend | `PORT=8080`, `API_URL=http://suivi-delivery-backend-local:8000`, `KEYCLOAK_URL=http://suivi-delivery-keycloak-local:8080/auth`, `INSTANCE_NAME=local`, `INSTANCE_COLOR` (facultatif) |

Chaque conteneur reçoit tout le fichier, sans aucun `-e`, **sauf `DHI_USERNAME` et `DHI_TOKEN`** : le script lui donne une copie de `docker.env` sans ces deux lignes (fichier provisoire, lisible par vous seul, effacé à la fin du script), pour qu'aucun jeton n'entre dans un conteneur. Il y trouve ses réglages, et ignore les autres. Pour les commandes à retaper à la main (ci-dessous), même précaution : `grep -vE '^DHI_(USERNAME|TOKEN)=' deployment/docker.env > /tmp/conteneurs.env`, puis `--env-file /tmp/conteneurs.env`.

La base apparaît donc plusieurs fois, sous les noms qu'attend chaque programme (`POSTGRES_*`, `LIQUIBASE_COMMAND_*`, `KC_DB_*`, `APP_DB_*`). **Le script vérifie que tout se correspond** et s'arrête avec un message sinon :

- toutes ces variables désignent la même base (même adresse, même nom ; pour Liquibase et l'API, même utilisateur et même mot de passe) ;
- Keycloak est bien servi sous l'adresse de l'interface (`KC_HOSTNAME`, `APP_KEYCLOAK_URL`, `KEYCLOAK_URL`).

Pour changer le mot de passe de la base, il faut donc le changer aux trois endroits. Et si un modèle gagne un nouveau réglage, votre `docker.env` n'est pas mis à jour : il faut l'y ajouter à la main.

Ce n'est **pas** le même fichier que les `.env.example` de `backend/` et `frontend/`, qui servent au développement sans Docker. Deux différences comptent :

- **`APP_HOST`** : dans un conteneur, il faut `0.0.0.0`. Avec `127.0.0.1`, l'API serait injoignable depuis le frontend.
- **La base** : dans Docker, l'API la joint par le **nom du conteneur** PostgreSQL (`APP_DB_HOST=suivi-delivery-postgres-local`). Sans Docker, c'est `localhost`.

Les mots de passe (`POSTGRES_PASSWORD` et ses deux copies, `KC_DB_PASSWORD`, `KC_BOOTSTRAP_ADMIN_PASSWORD`, `APP_ADMIN_PASSWORD`) et la clé `APP_KEYCLOAK_CLIENT_SECRET` sont tirés au hasard par le script quand il crée `docker.env`. Les modèles n'en contiennent aucun : aucun mot de passe n'est écrit dans Git. Ils ne servent que sur ce poste, et la base n'est ouverte que sur `127.0.0.1`.

Règles d'écriture du fichier :

- une ligne `VARIABLE=value` par réglage, **sans guillemets** ;
- `#` en début de ligne pour un commentaire ;
- **ne pas laisser de ligne vide** comme `APP_DOCS=` : elle remplacerait la valeur prévue par du vide. Il faut supprimer la ligne, ou la mettre en commentaire.

`API_URL` contient le **nom du conteneur backend** et **son port** : si l'on change `APP_PORT`, il faut changer `API_URL` aussi.

### Le plus simple : le script `docker-deploy.zsh` (ou `docker-deploy.ps1`)

Le script, dans `deployment/`, enchaîne tout ce qui suit : fabrication des images, remplacement des conteneurs, réseau et volume, lancement de la base et application de sa structure (Liquibase), lancement de Keycloak, de l'API et de l'interface, vérification.

```bash
./deployment/docker-deploy.zsh                    # tout : postgres, liquibase, keycloak, backend, frontend ; données CONSERVÉES
./deployment/docker-deploy.zsh postgres           # la base seule (par exemple pour l'API lancée avec « uv run »)
./deployment/docker-deploy.zsh liquibase          # la structure de la base seule (après un nouveau changement)
./deployment/docker-deploy.zsh keycloak           # Keycloak seul (comptes et connexion)
./deployment/docker-deploy.zsh backend            # l'API seule
./deployment/docker-deploy.zsh frontend           # l'interface seule
./deployment/docker-deploy.zsh --reset            # tout, en EFFAÇANT les données (repartir de zéro)
./deployment/docker-deploy.zsh postgres --reset   # la base seule, en effaçant les données
```

**Sous Windows : `docker-deploy.ps1`**, la même chose en PowerShell, avec les mêmes options et le même déroulé. Il faut **PowerShell 7 (`pwsh`)** : l'ancien « Windows PowerShell » 5.1 est refusé dès la première ligne (`#Requires -Version 7.0`).

```powershell
.\deployment\docker-deploy.ps1                    # tout
.\deployment\docker-deploy.ps1 postgres --reset   # etc., comme ci-dessus
```

Si Windows refuse de lancer le script (« l'exécution de scripts est désactivée sur ce système ») : `pwsh -ExecutionPolicy Bypass -File .\deployment\docker-deploy.ps1`. Les noms et les ports, réglables en haut de chaque script, doivent rester les mêmes dans les deux fichiers.

Ne relancer qu'un module est plus rapide : seule son image est refabriquée, et les autres conteneurs continuent de tourner.

- `liquibase`, `keycloak` et `backend` ont besoin de la base. Si son conteneur est arrêté, le script le redémarre. S'il n'existe pas, il demande de lancer d'abord `postgres`.
- `--reset` efface les données de la base. Il ne s'utilise donc qu'avec `postgres`, ou sans module.

Le frontend et le backend sont indépendants (voir § 3) :

- **`frontend` sans backend lancé** : le frontend démarre, et le script le signale. L'interface affiche « Les données sont momentanément indisponibles » jusqu'au lancement du backend, sans avoir à relancer le frontend ensuite.
- **`backend` seul** : le frontend en place continue de fonctionner et retrouve tout seul le nouveau backend.

Ce qu'il fait, dans l'ordre :

1. **Il vérifie avant d'agir**, pour le ou les modules demandés :
   - Docker est démarré, et les fichiers sont présents ;
   - `docker.env` existe et est complet (sinon il le crée à partir des modèles) ;
   - les réglages de la base et les adresses de Keycloak se correspondent ;
   - les ports du poste sont libres. Un port pris par un autre programme (souvent l'API ou l'interface lancée sans Docker, ou un PostgreSQL installé sur le poste) l'arrête **avant toute modification**.
2. **Il fabrique les images** (PostgreSQL, Liquibase, Keycloak, backend, frontend). Si une fabrication échoue, il s'arrête : les conteneurs en place ne sont pas touchés.
3. **Il supprime les anciens conteneurs**, seulement s'ils existent. Les données de la base restent dans son volume.
4. **Il crée le réseau et le volume de la base**, seulement s'ils n'existent pas. Le volume, donc les données, est conservé, sauf avec `--reset`.
5. **Il lance la base, puis la prépare** :
   - **PostgreSQL** : il attend qu'il réponde. Au premier lancement, la base crée ses deux schémas et l'utilisateur de Keycloak. Le script vérifie que le schéma `suivi_delivery` existe (sinon : `--reset`).
   - **Liquibase** applique les changements de structure qui manquent (au premier lancement : toutes les tables).
   - **Keycloak** prépare ses tables et, au premier lancement, importe la configuration de l'outil (une à deux minutes).
6. **Il lance le backend puis le frontend.**
7. **Il attend qu'ils répondent** (30 s au plus ; Keycloak : 3 minutes) : le backend (`/readyz`), le frontend (`/health`), sa page de connexion, et Keycloak servi par le frontend (`/auth/…`). En cas d'échec, il affiche les derniers journaux du conteneur en cause.
8. **Il affiche le compte `admin`** : identifiant et mot de passe (`APP_ADMIN_PASSWORD` de `docker.env`) quand Keycloak vient de le créer, et l'adresse de la console de Keycloak.

Il affiche ✔ à chaque étape réussie, et ✘ avec un message à la première erreur. Les noms et les ports sont réglables en haut du fichier.

Les commandes ci-dessous détaillent ce que fait le script, étape par étape.

### Avec Podman au lieu de Docker

**Podman** est un autre programme qui fabrique et lance des conteneurs, publié par Red Hat. Il n'a pas besoin de droits administrateur. Ses commandes sont les mêmes que celles de Docker : les scripts savent donc utiliser l'un ou l'autre.

```bash
./deployment/podman-deploy.zsh                    # comme docker-deploy.zsh, mêmes modules et options
./deployment/podman-deploy.zsh backend            # l'API seule
./deployment/podman-deploy.zsh postgres --reset   # la base seule, en effaçant les données
```

```powershell
.\deployment\podman-deploy.ps1                    # Windows, PowerShell 7
```

`podman-deploy` n'est qu'un raccourci : il lance `docker-deploy` avec l'option `--podman` (`./deployment/docker-deploy.zsh --podman backend` revient au même). Tout le reste est commun : le déroulé, les vérifications et `deployment/docker.env`.

- **Pré-requis** : Podman installé et, sur Mac ou Windows, sa machine démarrée (`podman machine start`). Le script le vérifie.
- **Mêmes noms, mêmes ports** que Docker. Mais Podman a **ses propres images, son réseau et son volume**, donc sa propre base : les deux ne se voient pas.
- Ne pas faire tourner Docker et Podman en même temps. Si l'un tient déjà un port, le script s'arrête avant de rien modifier : arrêter d'abord les conteneurs de l'autre (`docker rm -f …` ou `podman rm -f …`, voir [Tout supprimer](#tout-supprimer)).
- Les commandes à retaper (plus bas) s'écrivent pareil avec `podman` à la place de `docker`.

### Les ports utilisés sur le poste

**Chaque conteneur ouvert sur le poste a son propre port** : un port ne peut servir qu'à un seul programme à la fois. Sinon, le second conteneur refuse de démarrer (« port is already allocated »).

| Conteneur | Port du poste (à ouvrir avec `-p`) | Port dans le conteneur (réglage) | Adresse |
| --- | --- | --- | --- |
| Frontend | **8080** | 8080 (`PORT`, dans `docker.env`) | <http://localhost:8080> |
| Backend (développement seulement) | **8000** | 8000 (`APP_PORT`, dans `docker.env`) | <http://localhost:8000/api/docs> |
| Keycloak (développement seulement, ce poste seulement) | **8081**, sur `127.0.0.1` | 8080 | <http://localhost:8081/auth/admin> : sa console. Les pages de connexion, elles, passent par le frontend (`http://localhost:8080/auth/…`) |
| PostgreSQL (développement seulement, ce poste seulement) | **5432**, sur `127.0.0.1` | 5432 | `localhost:5432` (psql, DBeaver, API lancée avec `uv run`) |

Lecture de l'option `-p` : **`-p <port du poste>:<port dans le conteneur>`**.

- Le **premier nombre** est celui qu'on tape dans le navigateur. Il doit être **différent** pour le frontend et le backend, et libre sur le poste.
- Le **second nombre** doit être égal au port réglé dans le `docker.env` du conteneur.

Pour changer un port du poste, on ne modifie que le premier nombre (ex. `-p 9090:8080`) : les réglages ne bougent pas. Le frontend joint le backend par le réseau Docker (`API_URL=http://suivi-delivery-backend-local:8000`), jamais par un port du poste. Il n'est donc pas concerné par ce choix.

### Étape 1 : fabriquer les images

À refaire à chaque modification du code ou des Dockerfiles. L'option `-t` donne un nom à l'image, et le dernier mot est le dossier qui contient le Dockerfile.

Le backend installe ses dépendances hors ligne, depuis `backend/dist/` : les préparer d'abord, avec uv, pour le processeur de Docker (`arm64` sur un Mac Apple, `amd64` sur un PC) :

```bash
(cd backend && uv run --no-project --no-build --with pip==26.2.1 python scripts/prepare_dist.py uv arm64)
```

Le frontend copie le site déjà construit : le construire d'abord, avec le Node.js du poste (voir [frontend.md](frontend.md)) :

```bash
(cd frontend && npm ci --ignore-scripts && npm run build)
```

```bash
docker build -t suivi-delivery-postgres-local postgres
docker build -t suivi-delivery-liquibase-local liquibase
docker build -t suivi-delivery-keycloak-local keycloak
docker build -t suivi-delivery-backend-local backend
docker build -t suivi-delivery-frontend-local frontend
```

### Étape 2 : créer le réseau et le volume (une seule fois)

Les conteneurs d'un même **réseau** se trouvent par leur nom : c'est ainsi que le frontend joint `suivi-delivery-backend-local:8000`, et le backend `suivi-delivery-postgres-local:5432`. Le **volume** est un disque géré par Docker, où PostgreSQL range ses données.

```bash
docker network create suivi-delivery-local
docker volume create suivi-delivery-postgres-local
```

### Étape 3 : lancer la base, sa structure, Keycloak, le backend, puis le frontend

La base (nom, utilisateur et mot de passe : `POSTGRES_*` de `docker.env`) :

```bash
docker run -d --name suivi-delivery-postgres-local --network suivi-delivery-local -p 127.0.0.1:5432:5432 --env-file deployment/docker.env -v suivi-delivery-postgres-local:/var/lib/postgresql suivi-delivery-postgres-local
```

Sa structure, une fois qu'elle répond (Liquibase applique ce qui manque, puis s'arrête) :

```bash
docker run --rm --network suivi-delivery-local --env-file deployment/docker.env suivi-delivery-liquibase-local
```

Keycloak (le premier démarrage prend une à deux minutes : `docker logs -f suivi-delivery-keycloak-local` jusqu'à « Import finished successfully ») :

```bash
docker run -d --name suivi-delivery-keycloak-local --network suivi-delivery-local -p 127.0.0.1:8081:8080 --env-file deployment/docker.env suivi-delivery-keycloak-local
```

Le backend et le frontend, avec les images créées localement :

```bash
docker run -d --name suivi-delivery-backend-local --network suivi-delivery-local -p 8000:8000 --env-file deployment/docker.env suivi-delivery-backend-local
docker run -d --name suivi-delivery-frontend-local --network suivi-delivery-local -p 8080:8080 --env-file deployment/docker.env suivi-delivery-frontend-local
```

Ou avec les images publiées sur GitHub (ghcr.io), par exemple en version 0.4.2 :

```zsh
docker run --rm --network suivi-delivery-local --env-file deployment/docker.env ghcr.io/florent-coulon-deville/suivi-delivery-liquibase:0.4.2
docker run -d --name suivi-delivery-backend-local --network suivi-delivery-local -p 8000:8000 --env-file deployment/docker.env ghcr.io/florent-coulon-deville/suivi-delivery-backend:0.4.2
docker run -d --name suivi-delivery-frontend-local --network suivi-delivery-local -p 8080:8080 --env-file deployment/docker.env ghcr.io/florent-coulon-deville/suivi-delivery-frontend:0.4.2
```

| Option | Signification |
| --- | --- |
| `-d` | Tourne en arrière-plan |
| `--name` | Nom du conteneur, qui sert aussi d'adresse sur le réseau |
| `--network suivi-delivery-local` | Branché sur le réseau commun |
| `--env-file` | Les réglages, lus dans le fichier |
| `-e VARIABLE=value` | Un réglage donné directement |
| `-v suivi-delivery-postgres-local:/var/lib/postgresql` | Le volume des données, monté là où PostgreSQL les écrit |
| `--rm` | Supprime le conteneur dès qu'il s'arrête (Liquibase : il fait son travail, puis s'arrête) |
| `-p 127.0.0.1:5432:5432` | Ouvre la base **sur ce poste seulement** (pas depuis le réseau) |
| `-p 8080:8080` | Ouvre le port 8080 du poste vers le frontend : c'est l'adresse de l'interface |
| `-p 8000:8000` | **En développement seulement** : ouvre aussi le port 8000 du poste vers le backend, pour le tester directement (Swagger, script de démo, appels `curl`) |

**Le backend exposé, uniquement pour le développement.** Sur OpenShift, seul le frontend sera ouvert vers l'extérieur ; le backend restera derrière lui. En local, ouvrir le backend sert à charger les données de démo, à utiliser Swagger, et à distinguer un problème d'API d'un problème d'interface.

- Ce n'est pas un réglage de l'image : c'est seulement l'option `-p` de la commande. Pour ne pas exposer le backend, il suffit de la retirer.
- Si l'API tourne déjà sur votre poste sans Docker (`uv run python -m app`), le port 8000 est pris : utiliser par exemple `-p 8001:8000`, puis <http://localhost:8001>.

### Étape 4 : vérifier

| Vérification | Adresse ou commande | Résultat attendu |
| --- | --- | --- |
| Le site | <http://localhost:8080> | L'interface, avec le bandeau « Instance : local » |
| La connexion | <http://localhost:8080> | La page de connexion (Keycloak, à l'allure de l'outil, à l'adresse `http://localhost:8080/auth/…`) ; avec `admin` et son mot de passe (voir ci-dessous), les chiffres clés, sans « Les données sont momentanément indisponibles » |
| Swagger (développement) | <http://localhost:8000/api/docs> | La documentation de l'API, servie directement par le backend |
| La sonde de vie du frontend | <http://localhost:8080/sante> | `ok` |
| Les probes du backend (développement) | <http://localhost:8000/readyz> | `{"status":"ok"}` (voir § 8) |
| Les quatre conteneurs tournent | `docker ps` | `suivi-delivery-postgres-local`, `suivi-delivery-keycloak-local`, `suivi-delivery-backend-local` et `suivi-delivery-frontend-local`, état `Up` |
| La structure de la base | `docker exec suivi-delivery-postgres-local psql -U suivi_delivery -d suivi_delivery -c '\dt'` | les 15 tables (schéma `suivi_delivery`), et les deux de Liquibase |

**Le mot de passe du compte `admin`** est `APP_ADMIN_PASSWORD` de `docker.env`, tiré au hasard. Keycloak le reprend à son premier démarrage, et **le script l'affiche dans son récapitulatif** à ce moment-là.

- Le changer ensuite dans « Mon compte ». (Modifier `APP_ADMIN_PASSWORD` après coup n'a pas d'effet : il ne sert qu'au premier démarrage.)
- Mot de passe perdu : un autre administrateur en donne un provisoire dans l'écran Comptes. Sinon, sur ce poste : la console de Keycloak (<http://localhost:8081/auth/admin>, `KC_BOOTSTRAP_ADMIN_*`), ou repartir de zéro (`--reset`).

Pour avoir des données à regarder, le script de démo remplit l'API (depuis `backend/`). Il vise le backend exposé (<http://127.0.0.1:8000>). Sans réglage, il affiche une adresse et un code : les ouvrir dans le navigateur et se connecter en `admin`. On peut aussi lui donner un compte programme ADMIN (`API_CLIENT_ID`, `API_CLIENT_SECRET`, voir § 2).

```bash
uv run python scripts/load_demo.py
```

### Au quotidien

| Pour… | Commande |
| --- | --- |
| Voir ce qui tourne | `docker ps` |
| Lire les journaux | `docker logs -f suivi-delivery-backend-local` (ou `suivi-delivery-frontend-local`, `suivi-delivery-keycloak-local`, `suivi-delivery-postgres-local`) ; `Ctrl+C` pour sortir |
| Arrêter | `docker stop suivi-delivery-frontend-local suivi-delivery-backend-local suivi-delivery-keycloak-local suivi-delivery-postgres-local` |
| Relancer | `docker start suivi-delivery-postgres-local suivi-delivery-keycloak-local suivi-delivery-backend-local suivi-delivery-frontend-local` |
| Changer un réglage, ou mettre à jour après une modification du code | Voir « Les commandes à retaper », juste après. Les données, sur le volume, sont conservées |
| Changer la structure de la base | Voir [postgresql.md § 4](postgresql.md#4-faire-évoluer-la-structure), puis `./deployment/docker-deploy.zsh liquibase` |

### Les commandes à retaper

Toutes ces commandes se lancent depuis la racine du projet. Ports du poste : **8080 pour le frontend, 8000 pour le backend, 8081 pour la console de Keycloak, 5432 pour la base**, jamais le même (voir « Les ports utilisés sur le poste »). `docker rm -f` supprime un conteneur, même s'il tourne. Les **images** et les **données** (sur le volume) ne sont pas touchées.

**Après une modification du code ou d'un Dockerfile** : refabriquer les images (backend : `dist/` d'abord ; frontend : `npm run build` d'abord ; voir l'étape 1), mettre la structure de la base à jour, puis recréer les deux conteneurs. La base, elle, continue de tourner.

```bash
docker build -t suivi-delivery-liquibase-local liquibase
docker build -t suivi-delivery-backend-local backend
docker build -t suivi-delivery-frontend-local frontend
docker run --rm --network suivi-delivery-local --env-file deployment/docker.env suivi-delivery-liquibase-local
docker rm -f suivi-delivery-frontend-local suivi-delivery-backend-local
docker run -d --name suivi-delivery-backend-local --network suivi-delivery-local -p 8000:8000 --env-file deployment/docker.env suivi-delivery-backend-local
docker run -d --name suivi-delivery-frontend-local --network suivi-delivery-local -p 8080:8080 --env-file deployment/docker.env suivi-delivery-frontend-local
```

**Pour recréer le backend seul** : après une modification de `docker.env` (le fichier n'est lu qu'à la création du conteneur), ou pour prendre une nouvelle image du backend (après `docker build -t suivi-delivery-backend-local backend`).

```bash
docker rm -f suivi-delivery-backend-local
docker run -d --name suivi-delivery-backend-local --network suivi-delivery-local -p 8000:8000 --env-file deployment/docker.env suivi-delivery-backend-local
```

**Pour recréer le frontend seul** : après une modification de `docker.env`, ou pour prendre une nouvelle image du frontend (après `docker build -t suivi-delivery-frontend-local frontend`).

```bash
docker rm -f suivi-delivery-frontend-local
docker run -d --name suivi-delivery-frontend-local --network suivi-delivery-local -p 8080:8080 --env-file deployment/docker.env suivi-delivery-frontend-local
```

**Pour recréer Keycloak seul** : après une modification du thème ou de `docker.env` (le domaine, lui, n'est importé qu'une fois : le changer demande `--reset`).

```bash
docker build -t suivi-delivery-keycloak-local keycloak
docker rm -f suivi-delivery-keycloak-local
docker run -d --name suivi-delivery-keycloak-local --network suivi-delivery-local -p 127.0.0.1:8081:8080 --env-file deployment/docker.env suivi-delivery-keycloak-local
```

**Après un redémarrage du poste ou de Docker Desktop** : les conteneurs existent toujours, il suffit de les relancer, la base d'abord.

```bash
docker start suivi-delivery-postgres-local suivi-delivery-keycloak-local suivi-delivery-backend-local suivi-delivery-frontend-local
```

**Pour vérifier** que tout tourne, puis lire les journaux en cas de souci :

```bash
docker ps
docker logs suivi-delivery-backend-local
docker logs suivi-delivery-frontend-local
```

### Tout supprimer

On supprime les conteneurs, puis le réseau. Le volume ne se supprime que si l'on veut **effacer les données**.

```bash
docker rm -f suivi-delivery-frontend-local suivi-delivery-backend-local suivi-delivery-keycloak-local suivi-delivery-postgres-local
docker network rm suivi-delivery-local
docker volume rm suivi-delivery-postgres-local
```

### En cas de problème

| Symptôme | Où regarder |
| --- | --- |
| Un conteneur s'arrête tout de suite (absent de `docker ps`) | `docker logs <name>`. Un réglage invalide est signalé par « Réglage invalide : … » |
| Le site s'affiche mais « Les données sont momentanément indisponibles » | Normal si le backend n'est pas lancé : `./deployment/docker-deploy.zsh backend`. Sinon : `API_URL` contient-il bien `suivi-delivery-backend-local` et le même port que `APP_PORT` ? Le détail de l'erreur est dans `docker logs suivi-delivery-frontend-local` (« API injoignable »). |
| « port is already allocated » | Le port du poste est déjà pris (8080 pour le frontend, 8000 pour le backend, souvent par l'API lancée sans Docker) : changer le premier nombre, par exemple `-p 9090:8080` puis <http://localhost:9090>, ou `-p 8001:8000` |
| « name is already in use » | Le conteneur existe déjà, même s'il est arrêté : `docker rm -f <name>`, puis relancer (voir « Les commandes à retaper ») |
| Le backend s'arrête avec « n'a pas les tables … : appliquer d'abord la structure avec Liquibase » | La structure n'a pas été appliquée : `./deployment/docker-deploy.zsh liquibase` (ou Liquibase à la main, étape 3) |
| Le backend s'arrête avec « Base PostgreSQL injoignable » | La base ne tourne pas (`docker start suivi-delivery-postgres-local`), ou les réglages `POSTGRES_*` de `docker.env` ont changé depuis la création de la base (ils ne servent qu'au premier démarrage : `--reset` pour repartir de zéro) |
| Le script s'arrête : « La base n'a pas de schéma suivi_delivery », ou `docker.env` incomplet | La base ou les réglages ne sont pas ceux attendus : mettre `docker.env` de côté et relancer avec `--reset` (voir « Les modules et le fichier de réglages ») |
| La page de connexion ne s'affiche pas (404 sur `/auth/…`) | Keycloak ne tourne pas, ou démarre encore : `docker logs suivi-delivery-keycloak-local`. Sinon, `KEYCLOAK_URL` doit désigner `suivi-delivery-keycloak-local` |
| Connexion refusée par l'API (« Jeton d'accès invalide ») juste après la page de connexion | `APP_FRONTEND_URL` doit être l'adresse tapée dans le navigateur, et `KC_HOSTNAME` la même suivie de `/auth` |
| Liquibase refuse avec « checksum » ou « Validation Failed » | Un changement déjà appliqué a été modifié : remettre le fichier comme il était, et faire un **nouveau** changement (voir [postgresql.md § 4](postgresql.md#4-faire-évoluer-la-structure)) |

### Plus tard : Docker Compose

Comme il y a plusieurs commandes à enchaîner dans l'ordre, l'outil habituel est **Docker Compose**, inclus dans Docker Desktop. On décrit les conteneurs une fois pour toutes dans un fichier `compose.yaml` : images, `env_file`, réseau, volume, port. Ensuite :

- `docker compose up -d --build` fabrique, crée et lance tout ;
- `docker compose down` arrête tout.

Les fichiers `docker.env` restent les mêmes. Pas encore mis en place.

## 8. Kubernetes / OpenShift : les probes

Kubernetes interroge régulièrement chaque pod pour savoir où il en est. L'API répond sur trois adresses, **hors de `/api`**, **sans jeton** et **sans aucune donnée** :

| Probe | Adresse | Question | Si elle échoue |
| --- | --- | --- | --- |
| **Startup** | `/startupz` | As-tu fini de démarrer (connectée à la base, tables présentes) ? | Kubernetes attend ; au-delà du délai, il redémarre le pod |
| **Readiness** | `/readyz` | Peux-tu recevoir des appels (démarrée, et la base répond) ? | le pod ne reçoit plus d'appels, sans être redémarré |
| **Liveness** | `/livez` | Es-tu encore en vie ? Répondre suffit | Kubernetes redémarre le pod |

Réponse : **200** `{"status": "ok"}`, ou **503** `{"status": "unavailable", "detail": "…"}`.

La liveness ne vérifie volontairement rien d'autre : un souci passager de la base doit seulement retirer le pod du trafic (readiness), pas le faire redémarrer en boucle.

À mettre dans le chart Helm, sur le conteneur du backend (port `APP_PORT`, 8000 par défaut) :

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

Les deux autres probes ne commencent qu'une fois la startup réussie. Un démarrage lent (base longue à répondre) ne fait donc pas redémarrer le pod par erreur.

Les autres pods :

- **avant l'API**, des conteneurs de préparation (*initContainers*, lancés avant le conteneur principal) attendent la base, puis lancent Liquibase (voir `templates/backend-deployment.yaml`) ;
- **la base** intégrée au chart a ses propres probes (`pg_isready`) ;
- **Keycloak** a les siennes, sur son port de gestion 9000 (`/auth/health/started`, `/ready`, `/live`), jamais exposé ;
- **le frontend** répond sur `/health` (port 8080), même si l'API est arrêtée : `livenessProbe` et `readinessProbe` utilisent cette seule adresse.

## 9. Installer sur un cluster

Deux façons, qui installent exactement la même chose (le chart Helm du projet) :

| | Pour qui | Ce qu'il faut |
| --- | --- | --- |
| **[9.1 Avec Helm, pas à pas](#91-avec-helm-pas-à-pas)** | une équipe OpenShift, une recette, la production : on voit et on maîtrise chaque étape | `helm`, `git` et un accès au cluster ; le chart est pris dans le dépôt Git, à l'étiquette de la version |
| **[9.2 Avec le script `k8s-deploy.zsh`](#92-avec-le-script-k8s-deployzsh)** | le développeur, sur kind ou CRC : tout en une commande | le dépôt Git cloné |

### 9.1 Avec Helm, pas à pas

À chaque version, la CI publie les cinq images et le chart ([ci.md § 5](ci.md#5-publier-les-images--sortir-une-version)). Le chart se prend sur Docker Hub, ou dans le dépôt Git, à l'étiquette de la version (`vX.Y.Z`) : c'est le même.

| Quoi | Où |
| --- | --- |
| le chart | `oci://registry-1.docker.io/florentcoulon/suivi-delivery`, version `<version>` (`helm pull … --version <version> --untar` pour le récupérer), ou le dossier `helm/suivi-delivery` du dépôt Git, à l'étiquette `v<version>` |
| les images | `ghcr.io/florent-coulon-deville/suivi-delivery-{backend,frontend,liquibase,keycloak,postgres}:<version>` |

Le chart d'une version installe les images **de la même version**, et va les chercher seul dans ce registre (`images.registry`). On ne choisit donc qu'un numéro : celui de l'étiquette.

**Outils** : Helm 3.8 ou plus (Helm 4 conseillé), `git`, et `oc` (OpenShift) ou `kubectl`.

Les exemples visent l'instance CRC (OpenShift Local) dans l'espace de noms `suivi-delivery`. On récupère le dépôt à l'étiquette de la version, et on met le dossier du chart dans une variable pour ne pas le répéter :

```bash
VERSION=0.4.3
git clone --branch v$VERSION --depth 1 https://github.com/florent-coulon-deville/suivi-delivery.git suivi-delivery-$VERSION
CHART=./suivi-delivery-$VERSION/helm/suivi-delivery
```

#### Étape 1 : se connecter au cluster

```bash
oc login https://api.crc.testing:6443 -u kubeadmin   # OpenShift : la connexion devient le contexte courant
```

Helm vise **le contexte kubectl courant** (`kubectl config current-context`). Pour en viser un autre sans en changer, ajouter `--kube-context <context>` à chaque commande `helm`. Si les images sont privées, c'est le cluster qui se connecte au registre (`registry` de `values-secret.yaml`, voir [ci.md § 6](ci.md#qui-peut-télécharger-les-images)).

#### Étape 2 : préparer les fichiers de réglages

Helm part des valeurs par défaut du chart (`values.yaml`), puis applique chaque fichier donné avec `-f`, dans l'ordre : **le dernier l'emporte**.

```Plaintext
values.yaml (dans le chart)  →  -f values-secret.yaml  →  -f values-<instance>.yaml
```

| Fichier | Contenu | Dans Git ? |
| --- | --- | --- |
| `values-secret.yaml` | les **secrets** : accès à un registre privé (vide pour ghcr.io, images publiques), mot de passe initial de l'admin, clé du client de l'API dans Keycloak, mots de passe de la base (nos tables, Keycloak), administrateur de la console Keycloak | **jamais** |
| `values-<instance>.yaml` (ex. `values-crc.yaml`) | ce qui est **propre à l'instance** et n'est pas secret : nom affiché, couleur du bandeau, base fournie, Route… | le modèle oui (`values-crc.example.yaml`, dans le chart), la copie non |

Les modèles sont dans le dossier du chart :

```bash
cp $CHART/values-secret.example.yaml values-secret.yaml   # puis le remplir
cp $CHART/values-crc.example.yaml values-crc.yaml         # réglages de l'instance, à adapter
```

Garder ces deux copies **hors du dossier récupéré** (ici, à côté) : on les réutilise à chaque version. Dans le dossier `helm/suivi-delivery/` d'un dépôt de travail, les copies `values-secret.yaml` et `values-crc.yaml` sont ignorées par Git.

Pour voir tous les réglages possibles et leurs valeurs par défaut :

```bash
helm show values $CHART
```

#### Étape 3 : voir avant d'installer (facultatif)

```bash
helm template suivi-delivery $CHART -n suivi-delivery \
  -f values-secret.yaml -f values-crc.yaml | less
```

Affiche tout ce qui serait créé dans le cluster (Deployments, Services, Route…), **sans rien installer**. Utile pour vérifier une image, un réglage ou le nom d'une Route.

#### Étape 4 : installer

```bash
helm upgrade --install suivi-delivery $CHART \
  -n suivi-delivery --create-namespace \
  -f values-secret.yaml -f values-crc.yaml \
  --wait --timeout 10m
```

| Morceau | Rôle |
| --- | --- |
| `upgrade --install` | installe si l'application n'est pas là, met à jour sinon : **la même commande sert toujours** |
| `suivi-delivery` | le nom de l'installation (« release ») : il préfixe les objets créés |
| `-n … --create-namespace` | l'espace de noms, créé s'il n'existe pas (sur OpenShift, le droit de le créer peut manquer : demander le projet à l'équipe) |
| `--wait --timeout 10m` | attend que tout soit démarré (base, structure Liquibase, Keycloak, API, interface) ; échoue au-delà de 10 minutes (Keycloak est long à son premier démarrage) |

À la fin, Helm affiche l'adresse de l'interface et comment lire le mot de passe initial de l'admin.

#### Étape 5 : vérifier

```bash
helm test suivi-delivery -n suivi-delivery            # un pod de test appelle l'interface et l'API, depuis le cluster
```

```bash
oc get pods -n suivi-delivery                         # base, Keycloak, API et interface : Running ; test : Completed
```

```bash
oc get route suivi-delivery -n suivi-delivery -o jsonpath='{.spec.host}'; echo   # adresse de l'interface (HTTPS)
```

Se connecter avec le compte `admin` : son mot de passe initial est celui de `values-secret.yaml`, ou, s'il n'y était pas, celui généré à la première installation (le changer ensuite dans « Mon compte ») :

```bash
oc get secret suivi-delivery-application -n suivi-delivery -o jsonpath='{.data.APP_ADMIN_PASSWORD}' | base64 -d; echo
```

#### Étape 6 : passer à une nouvelle version

Récupérer le chart de la nouvelle version, puis la **même commande qu'à l'étape 4** :

```bash
VERSION=0.4.4
git clone --branch v$VERSION --depth 1 https://github.com/florent-coulon-deville/suivi-delivery.git suivi-delivery-$VERSION
CHART=./suivi-delivery-$VERSION/helm/suivi-delivery
helm upgrade --install suivi-delivery $CHART \
  -n suivi-delivery -f values-secret.yaml -f values-crc.yaml --wait --timeout 10m
```

Les données sont gardées (disque de la base conservé). Avant le démarrage de la nouvelle API, Liquibase applique les changements de structure qui manquent ([postgresql.md](postgresql.md)). Les secrets générés à la première installation sont conservés.

Pour voir les installations successives :

```bash
helm history suivi-delivery -n suivi-delivery
```

#### Étape 7 : revenir en arrière

```bash
helm rollback suivi-delivery <révision> -n suivi-delivery --wait   # révision : la colonne REVISION de helm history
```

**Attention** : Helm remet les images et les réglages d'avant, **pas la structure de la base**. Si la nouvelle version avait ajouté des changements Liquibase, ils restent appliqués, et l'ancienne API doit savoir tourner avec.

Avant un retour en arrière en production, vérifier la liste des changements de la version (`liquibase/changelog/`). Au besoin, les défaire d'abord avec Liquibase (`rollback`, voir [postgresql.md § 5](postgresql.md#5-les-commandes-liquibase-utiles)).

#### Étape 8 : désinstaller

```bash
helm uninstall suivi-delivery -n suivi-delivery
```

Le **disque de la base** et le **Secret de l'application** (mots de passe générés) sont **gardés** : une réinstallation retrouve les données. Pour tout effacer vraiment, données comprises :

```bash
oc delete pvc data-suivi-delivery-postgresql-0 -n suivi-delivery
oc delete secret suivi-delivery-application -n suivi-delivery
```

#### Depuis une autre branche (code pas encore publié)

Prendre pour `CHART` le dossier `helm/suivi-delivery` de son dépôt de travail. Le chart cherche alors les images **de la version écrite dans `Chart.yaml`** : elles doivent être publiées (sinon, sur kind, voir 9.2, qui les fabrique sur le poste).

### 9.2 Avec le script `k8s-deploy.zsh`

Le script `k8s-deploy.zsh`, dans le dossier `deployment/`, installe (ou met à jour) l'application sur **n'importe quel cluster Kubernetes** : OpenShift, kind sur le poste, ou tout autre cluster. Il n'utilise que **kubectl** et **helm**, plus **kind** et **Docker** (ou **Podman**, avec `--podman`) quand le cluster est un kind.

**OpenShift** : le script n'appelle pas `oc`, mais il en profite.

- `oc login` crée le contexte kubectl que le script utilise. Il faut donc `kubectl` installé à côté de `oc`.
- Le chart s'adapte tout seul à OpenShift : Route en HTTPS, utilisateur des conteneurs choisi par OpenShift, politique de sécurité « restricted ».
- Le script crée l'espace de noms s'il manque. Sur un OpenShift partagé, un compte ordinaire n'a souvent pas ce droit : demander le projet à l'équipe, ou le créer d'abord avec `oc new-project suivi-delivery`.

Le cluster visé est un **contexte kubectl**, c'est-à-dire une connexion enregistrée (`kubectl config get-contexts` les liste) :

- par défaut, le contexte en cours ;
- ou celui donné avec `--context`.

Sur OpenShift, `oc login` crée ce contexte et le rend courant. kind crée le sien (`kind-<name from cluster>`).

```bash
./deployment/k8s-deploy.zsh                                    # le contexte kubectl en cours
```

```bash
./deployment/k8s-deploy.zsh --context kind-suivi-delivery     # kind sur le poste (cluster créé s'il manque)
```

```bash
./deployment/k8s-deploy.zsh --context kind-suivi-delivery --reset   # kind, en repartant de zéro
```

```bash
./deployment/k8s-deploy.zsh --context kind-suivi-delivery --podman   # kind sur Podman au lieu de Docker
```

```bash
./deployment/k8s-deploy.zsh --context crc-admin --values helm/suivi-delivery/values-crc.yaml   # un cluster, avec les réglages de l'instance
```

| Option | Rôle | Défaut |
| --- | --- | --- |
| `--context <name>` | le cluster visé | le contexte kubectl en cours |
| `--namespace <name>` | l'espace de noms (namespace) | `suivi-delivery` |
| `--values <file>` | un fichier de valeurs Helm en plus : les réglages de cette instance (nom affiché, Route, base fournie…), par exemple `helm/suivi-delivery/values-crc.yaml`. Peut être répétée | aucun |
| `--registry <url>` | où le cluster télécharge les images (hors kind) : donné au chart (`images.registry`) | `ghcr.io/florent-coulon-deville` |
| `--yes` | ne pas demander confirmation (hors kind) | demande |
| `--reset` | supprime d'abord le cluster (kind seulement) | non |
| `--podman` | Podman au lieu de Docker : kind tourne sur Podman, et Podman fabrique les images ; hors kind, il vérifie seulement que les images sont publiées | Docker |

Le script, dans l'ordre :

1. **Il vérifie** les outils, lit la version de l'application (`appVersion` de `helm/suivi-delivery/Chart.yaml`), et vérifie que le contexte existe et que le cluster répond. Toutes les commandes visent ce contexte et lui seul (`kubectl --context`, `helm --kube-context`), même si un autre est en cours.
2. **Sur un vrai cluster**, il affiche l'adresse du cluster, l'espace de noms et la version, puis **demande confirmation** : on n'installe jamais sur le mauvais cluster par erreur.
3. **Les images** :
   - **kind** : il fabrique les cinq images du projet sur le poste (`suivi-delivery-{backend,frontend,liquibase,keycloak,postgres}:<version>`) et les charge directement dans kind. Aucun registre n'est nécessaire (`images.registry` vide : le chart prend les noms courts). On essaie ainsi le code tel qu'il est sur le poste.
   - **kind avec `--podman`** : kind fait tourner son cluster dans Podman (`KIND_EXPERIMENTAL_PROVIDER=podman`).
     - Chaque image passe par un fichier (`podman save`, puis `kind load image-archive`), car kind ne sait charger directement que depuis Docker.
     - Elle est nommée `docker.io/library/suivi-delivery-…`, le nom complet sous lequel le cluster la cherche (sinon, Podman l'appellerait `localhost/…`).
     - Un cluster kind créé avec Docker n'est pas vu avec Podman, et inversement.
     - Sur Mac et Windows, kind demande une machine Podman avec droits administrateur (`podman machine set --rootful`, machine arrêtée) : le script prévient sinon.
   - **autre cluster** : le cluster télécharge `<registry>/suivi-delivery-*:<version>`. Ces images doivent donc être **publiées** par la CI, à la sortie de la version ([ci.md § 5](ci.md#5-publier-les-images--sortir-une-version)). Le script signale celles qu'il ne trouve pas. Pour un registre privé : se connecter d'abord (`docker login`, ou `podman login` avec `--podman`), et donner au cluster un accès en lecture (`registry` dans `values-secret.yaml`).
4. **Il installe** (ou met à jour) le chart : `helm upgrade --install`, avec `values-secret.yaml` s'il existe et les fichiers `--values`. Sur kind, le nom d'instance est « kind ».
5. **Il lance `helm test`**, qui vérifie depuis l'intérieur du cluster que l'application répond.

**Les secrets** : si `helm/suivi-delivery/values-secret.yaml` existe, il est utilisé. Sinon, les mots de passe (admin, base, Keycloak) et la clé du client de l'API sont générés à la première installation, puis gardés d'une mise à jour à l'autre. Un `values-secret.yaml` qui contient des réglages inconnus du chart (`keySignature`, `tokenRegistration`) est refusé : retirer ces lignes (modèle : `values-secret.example.yaml`).

Le récapitulatif final donne les commandes utiles, toutes avec `--context` :

- **l'adresse de l'interface** : la Route sur OpenShift, sinon la commande `kubectl port-forward` à lancer, puis <http://localhost:8080> ;
- **le mot de passe initial de l'admin** ;
- **l'état des pods** ;
- **pour tout retirer** : `kind delete cluster` sur kind, `helm uninstall` ailleurs.

**Pour installer du code pas encore publié** sur un vrai cluster, il faut d'abord pousser ses images dans un registre que ce cluster peut lire : le script ne publie rien. La publication reste réservée à la CI, une fois par version.

**Sous Windows : `k8s-deploy.ps1`**, la même chose en PowerShell 7 (`pwsh`), avec les mêmes options :

```powershell
.\deployment\k8s-deploy.ps1 --context kind-suivi-delivery
```

Seule différence : Windows n'a pas la commande `base64`, la commande affichée pour lire le mot de passe admin le décode donc avec PowerShell. Si Windows refuse de lancer le script : `pwsh -ExecutionPolicy Bypass -File .\deployment\k8s-deploy.ps1`. Les deux scripts doivent rester identiques (mêmes options, mêmes étapes).
