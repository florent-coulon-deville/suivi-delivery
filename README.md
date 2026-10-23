# Suivi de la delivery

[![Quality gate status](https://sonarcloud.io/api/project_badges/measure?project=artenola-suivi-delivery&metric=alert_status&token=6fcacb24d8182a8196087e6ddbbe38ce36c459da)](https://sonarcloud.io/summary/new_code?id=artenola-suivi-delivery)
[![Reliability Rating](https://sonarcloud.io/api/project_badges/measure?project=artenola-suivi-delivery&metric=reliability_rating&token=6fcacb24d8182a8196087e6ddbbe38ce36c459da)](https://sonarcloud.io/summary/new_code?id=artenola-suivi-delivery)
[![Coverage](https://sonarcloud.io/api/project_badges/measure?project=artenola-suivi-delivery&metric=coverage&token=6fcacb24d8182a8196087e6ddbbe38ce36c459da)](https://sonarcloud.io/summary/new_code?id=artenola-suivi-delivery)
[![Duplicated Lines (%)](https://sonarcloud.io/api/project_badges/measure?project=artenola-suivi-delivery&metric=duplicated_lines_density&token=6fcacb24d8182a8196087e6ddbbe38ce36c459da)](https://sonarcloud.io/summary/new_code?id=artenola-suivi-delivery)
[![Lines of Code](https://sonarcloud.io/api/project_badges/measure?project=artenola-suivi-delivery&metric=ncloc&token=6fcacb24d8182a8196087e6ddbbe38ce36c459da)](https://sonarcloud.io/summary/new_code?id=artenola-suivi-delivery)

[![Snapshot](https://github.com/florent-coulon-deville/suivi-delivery/actions/workflows/snapshot.yml/badge.svg?branch=main)](https://github.com/florent-coulon-deville/suivi-delivery/actions/workflows/snapshot.yml)
[![Release](https://github.com/florent-coulon-deville/suivi-delivery/actions/workflows/release.yml/badge.svg?branch=main)](https://github.com/florent-coulon-deville/suivi-delivery/actions/workflows/release.yml)

Application de suivi des mises en production (MEP). Elle répond à la question : **qu'est-ce qui est installé, où, en quelle version, avec quels paramètres ?**

Elle sert à deux choses :

- **déclarer ce qui est installé** (fait) ;
- **prévoir les installations futures** (à venir).

Nom technique du projet : `suivi-delivery` (dépôt GitHub `florent-coulon-deville/suivi-delivery`).

## Les mots à connaître

| Mot | Sens |
| --- | --- |
| **MEP** | mise en production : l'installation d'une nouvelle version |
| **API** ou **backend** | le programme qui garde les données et vérifie les règles (Python) |
| **interface** ou **frontend** | les pages web que l'on utilise dans le navigateur (Next.js) |
| **image** / **conteneur** | une image Docker est un programme prêt à lancer, avec tout ce dont il a besoin ; un conteneur est une image en train de tourner |
| **Keycloak** | le logiciel qui gère les comptes, les mots de passe et la connexion |
| **jeton** | une preuve de connexion, donnée par Keycloak, que l'on joint à chaque appel de l'API |
| **Liquibase** | l'outil qui crée et fait évoluer les tables de la base de données |
| **cluster** | un ensemble de serveurs qui fait tourner des applications (OpenShift, Kubernetes) |
| **namespace** | un espace réservé à une application dans un cluster |
| **Helm** / **chart** | Helm installe une application sur un cluster ; le chart est sa recette d'installation |

## Démarrage rapide

Il y a deux façons de faire tourner l'application sur son poste.

**Avec Docker** : c'est le plus simple. Il suffit d'avoir Docker Desktop. Depuis la racine du projet :

```bash
./deployment/docker-deploy.zsh
```

| Quoi | Adresse |
| --- | --- |
| Interface | <http://localhost:8080> |
| API (Swagger, développement seulement) | <http://localhost:8000/api/docs> |

Le script fabrique les images, lance les conteneurs et vérifie qu'ils répondent.

- **Les données sont gardées** d'un lancement à l'autre.
- `--reset` repart de zéro : `./deployment/docker-deploy.zsh --reset`.
- On peut relancer une seule partie : `./deployment/docker-deploy.zsh backend` (ou `frontend`).
- Sous Windows (PowerShell 7) : `.\deployment\docker-deploy.ps1`, mêmes options.
- Avec **Podman** au lieu de Docker : `./deployment/podman-deploy.zsh` (ou `.ps1`), mêmes options.

Détails et dépannage : [docs/deploiement.md](docs/deploiement.md#7-tester-avec-docker-sur-son-poste).

**Sans Docker, pour développer** (le code est rechargé à chaque modification) : voir [Développement](#développement) plus bas.

## Structure

```Plaintext
suivi-delivery/
├── deployment/             lancer l'application sur le poste ou sur un cluster
│   ├── docker-deploy.zsh   fabrique les images Docker et (re)lance les conteneurs sur le poste
│   ├── docker-deploy.ps1   la même chose pour Windows (PowerShell 7, pwsh)
│   ├── podman-deploy.zsh   la même chose avec Podman au lieu de Docker (.ps1 pour Windows)
│   ├── k8s-deploy.zsh      installe l'application sur un cluster (OpenShift, kind…) avec Helm
│   ├── k8s-deploy.ps1      la même chose pour Windows (PowerShell 7, pwsh)
│   └── docker.env          réglages des conteneurs sur le poste (créé par docker-deploy, hors de Git)
├── postgres/               la base de données PostgreSQL (image et préparation au premier démarrage)
├── keycloak/               les comptes et la connexion (Keycloak) — voir docs/keycloak.md
│   ├── Dockerfile          image Keycloak + notre thème + la configuration du domaine
│   ├── import/             la configuration de Keycloak pour l'outil (rôles, compte admin…)
│   └── themes/             le thème : pages de connexion à l'allure de l'outil
├── liquibase/              les tables de la base, créées par Liquibase — voir docs/postgresql.md
│   ├── Dockerfile          image Liquibase avec nos fichiers SQL
│   └── changelog/          les fichiers SQL, dans l'ordre (liste : main.yaml)
├── backend/                API (Python, FastAPI)
│   ├── .python-version     version de Python utilisée (3.14)
│   ├── pyproject.toml      dépendances et réglages des outils (pytest, ruff, ty)
│   ├── uv.lock             versions exactes des dépendances (fabriqué par uv, ne pas modifier à la main)
│   ├── dist/               dépendances téléchargées avant de fabriquer l'image (hors de Git)
│   ├── .env.example        modèle des réglages pour le développement sans Docker
│   ├── Dockerfile          fabrication de l'image Docker du backend
│   ├── docker.example.env  modèle des réglages du conteneur (recopié dans deployment/docker.env)
│   ├── app/
│   │   ├── __main__.py     lancement (python -m app) avec les réglages
│   │   ├── settings.py     réglages lus dans les variables d'environnement (port, base de données…)
│   │   ├── main.py         crée l'application et branche les routes
│   │   ├── schemas.py      forme des données échangées (JSON) et règles de saisie
│   │   ├── storage.py      opérations sur les données (lister, ajouter…), version en mémoire
│   │   ├── storage_postgres.py  les mêmes opérations dans la base PostgreSQL
│   │   ├── transactions.py une transaction par requête, une écriture à la fois
│   │   ├── consistency.py  règles d'ensemble : on ne peut rien saisir d'incohérent
│   │   ├── http.py         règles HTTP communes (méthodes, codes retour)
│   │   ├── security.py     vérification des jetons de connexion
│   │   ├── audit_log.py    journal des actions (qui a saisi quoi)
│   │   └── routes/         une ressource par fichier (clusters, modules, installations…)
│   ├── scripts/
│   │   ├── load_demo.py données de démonstration, à charger dans une API démarrée
│   └── tests/              un fichier de tests par ressource (+ conftest.py : outils communs)
├── frontend/               interface web (Next.js + React + TypeScript) — voir docs/frontend.md
│   ├── .env.example        modèle des réglages pour le développement sans Docker
│   ├── Dockerfile          fabrication de l'image Docker du frontend (serveur Next.js)
│   ├── docker.example.env  modèle des réglages du conteneur (recopié dans deployment/docker.env)
│   ├── app/                les pages (« Ce qui tourne », « Saisie ») et leurs actions côté serveur
│   ├── components/         les blocs d'affichage
│   └── lib/                accès à l'API (côté serveur), calcul de l'état, types
├── cicd/                   outils de la CI (voir docs/ci.md)
│   └── check_versions.py   vérifie que backend, frontend et chart ont le même numéro
├── release-please-config.json  versions automatiques : fichiers où release-please change le numéro (docs/ci.md § 5)
├── CHANGELOG.md            journal des versions, tenu par release-please
├── helm/suivi-delivery/    le chart Helm : la recette d'installation sur un cluster
├── bruno/                  appels d'API prêts à l'emploi pour l'outil Bruno
├── .vscode/                réglages et extensions VS Code du projet
└── docs/
    ├── comprendre-le-code/ guide pas à pas du code du backend, fichier par fichier
    ├── architecture.md     découpage du programme, trajet d'une requête, choix
    ├── frontend.md         interface web : outils, lancement, écrans, code
    ├── deploiement.md      réglages, images Docker, lancement sur le poste et sur un cluster
    ├── postgresql.md       base PostgreSQL et Liquibase : tables, évolutions, commandes
    ├── keycloak.md         Keycloak : comptes, connexion, accès par script
    ├── modele-de-donnees.md  tables, liens et règles métier
    ├── api.md              URLs, champs, codes retour, exemples
    ├── glossaire.md        mot métier → nom dans le code (le code est en anglais)
    ├── git.md              branches, pull requests, ménage des branches fusionnées
    └── ci.md               vérifications automatiques (GitHub Actions)
```

## Avancement

- [x] Saisie de la structure : environnements, clusters, zones réseau, applications, namespaces, modules et leurs dépendances
- [x] Saisie des livraisons : versions de module, paramètres, emplacements, installations
- [x] Refus des versions incompatibles entre modules qui dépendent l'un de l'autre
- [x] Données dans PostgreSQL, tables créées par Liquibase
- [x] Interface web : écran « Ce qui tourne », espace de saisie, journal des actions
- [x] Export et import de toute la configuration dans un fichier Excel
- [x] Connexion par **Keycloak** : comptes, rôles consultation / saisie / administration
- [x] Réglages par variables d'environnement
- [x] Images Docker et lancement sur le poste
- [ ] Déploiement sur OpenShift
- [ ] Installations prévues et actions à faire
- [ ] Statut des installations, lu depuis l'outil de déploiement
- [ ] Rapports

## Développement

### L'API (backend)

Pré-requis : [uv](https://docs.astral.sh/uv/), qui installe Python 3.14 et les dépendances tout seul.

Depuis `backend/` :

```bash
uv sync                                # installer
uv run pytest                          # lancer les tests
uv run python -m app --reload          # démarrer l'API, données en mémoire (sans --reload : lancement normal)
```

Pour garder les données, démarrer l'API sur la base PostgreSQL du poste (Docker, voir [docs/postgresql.md](docs/postgresql.md)) :

```bash
./deployment/docker-deploy.zsh postgres && ./deployment/docker-deploy.zsh liquibase                    # depuis la racine
APP_DB_HOST=localhost APP_DB_PASSWORD=$(sed -n 's/^POSTGRES_PASSWORD=//p' ../deployment/docker.env) uv run python -m app --reload   # depuis backend/
```

Swagger (documentation interactive, pour tester chaque appel) : <http://localhost:8000/api/docs>, après s'être connecté avec le bouton **Authorize**.

### La connexion

Il faut être connecté pour appeler l'API (comptes et rôles : [docs/api.md](docs/api.md#0-connexion-et-droits)).

Les comptes et les mots de passe sont gérés par **Keycloak** ([docs/keycloak.md](docs/keycloak.md)). Sa page de connexion ressemble à l'outil et a la même adresse : l'utilisateur ne voit pas Keycloak.

- **Au premier démarrage**, Keycloak crée le compte **`admin`**. Son mot de passe est `APP_ADMIN_PASSWORD`, tiré au hasard dans `deployment/docker.env` et affiché par `docker-deploy.zsh`.
- Avec ce compte, l'écran **Comptes** crée les autres comptes :
  - onglet **Utilisateurs** : des personnes, avec un mot de passe provisoire à changer à la première connexion ;
  - onglet **Programmes** : des scripts ou outils, avec une clé.
- Chacun change son mot de passe dans **Mon compte** (clic sur son nom, en haut à droite).
- **Pour appeler l'API** sans l'interface : Bruno, Swagger, un script ou un compte programme. Voir [docs/api.md](docs/api.md#obtenir-un-jeton).

### Les données

Les données sont enregistrées dans une base **PostgreSQL** (variables `APP_DB_*`).

- Nos tables sont dans le schéma `suivi_delivery`. Keycloak range les siennes dans le schéma `keycloak` de la même base. (Un schéma est un dossier de tables à l'intérieur d'une base.)
- Les tables sont créées et mises à jour par **Liquibase**, lancé avant l'API.

Tout est expliqué dans [docs/postgresql.md](docs/postgresql.md).

- **Sans base** (`APP_DB_HOST` absente), l'API garde ses données en mémoire : elles sont perdues à l'arrêt.
- **Sur le poste**, `./deployment/docker-deploy.zsh` lance la base dans Docker. Les données sont gardées dans le volume Docker `suivi-delivery-postgres-local`.
- **Repartir de zéro** : `./deployment/docker-deploy.zsh --reset`.
- **Sauvegarder** : `docker exec suivi-delivery-postgres-local pg_dump -U suivi_delivery -d suivi_delivery > sauvegarde.sql`.

Les tests travaillent en mémoire, ou sur une base de tests à part : ils ne touchent jamais aux données.

### L'interface web (frontend)

Pré-requis : [Node.js](https://nodejs.org) 26 et npm (sur Mac avec MacPorts : `sudo port install nodejs26 npm11`).

L'API doit tourner en même temps : c'est le serveur de l'interface qui l'appelle.

```bash
# depuis backend/ : charger des données de démonstration (facultatif ;
# le script affiche une adresse à ouvrir dans le navigateur pour se connecter)
uv run python scripts/load_demo.py

# depuis frontend/
npm install          # la première fois, ou après une mise à jour des dépendances
npm run dev          # interface sur http://localhost:5173
npm run typecheck    # vérifie les types (TypeScript) : doit passer avant chaque commit
```

L'annonce « New major version of npm available » peut être ignorée. Détails dans [docs/frontend.md](docs/frontend.md).

### Les réglages

Ce qui change d'une installation à l'autre (adresses, ports, mots de passe) se règle **au lancement**, par des variables d'environnement. On ne touche pas au code. Sans variable, les valeurs par défaut conviennent au développement.

| Application | Variables |
| --- | --- |
| Backend | `APP_HOST`, `APP_PORT`, `APP_LOG_LEVEL`, `APP_DOCS` ; base : `APP_DB_HOST`, `APP_DB_PORT`, `APP_DB_NAME`, `APP_DB_SCHEMA`, `APP_DB_USER`, `APP_DB_PASSWORD` ; connexion : `APP_KEYCLOAK_URL`, `APP_KEYCLOAK_REALM`, `APP_KEYCLOAK_CLIENT_SECRET`, `APP_FRONTEND_URL`, `APP_API_URL` |
| Frontend | `API_URL` (adresse et port du backend), `PORT`, `INSTANCE_NAME`, `INSTANCE_COLOR`, `APP_FRONTEND_URL`, `KEYCLOAK_URL`, `KEYCLOAK_REALM` (connexion) |
| Keycloak | `KC_DB_*`, `KC_HOSTNAME`, `KC_BOOTSTRAP_ADMIN_*`, `APP_ADMIN_PASSWORD`, `APP_KEYCLOAK_CLIENT_SECRET` ([docs/keycloak.md](docs/keycloak.md#7-réglages)) |
| Script de démo | `API_URL`, `API_CLIENT_ID` / `API_CLIENT_SECRET` ou `API_OFFLINE_TOKEN`, `KEYCLOAK_URL` |

Où les mettre :

- sans Docker : fichiers `.env`, à créer à partir de `backend/.env.example` et `frontend/.env.example` ;
- avec Docker : un seul fichier, `deployment/docker.env`, hors de Git. `docker-deploy.zsh` le crée s'il manque, à partir des modèles `<module>/docker.example.env`.

Rôle de chaque variable, valeurs par défaut et exemples : [docs/deploiement.md](docs/deploiement.md).

### Qualité du code

Les outils viennent tous d'[Astral](https://astral.sh) :

| Outil | Rôle | Commande (depuis `backend/`) |
| --- | --- | --- |
| **uv** | installe Python et les dépendances, lance les commandes | `uv sync` |
| **ruff** | signale les erreurs courantes et les écarts de style | `uv run ruff check .` (`--fix` pour corriger automatiquement) |
| **ruff format** | met en forme le code (indentation, retours à la ligne, guillemets) | `uv run ruff format .` |
| **ty** | vérifie la cohérence des types (un texte n'est pas passé là où un nombre est attendu…) | `uv run ty check` |

Leurs réglages sont dans `backend/pyproject.toml`. Les trois doivent répondre « All checks passed » avant chaque envoi sur GitHub.

#### Dans VS Code

Le fichier `.vscode/extensions.json` liste les extensions du projet. À l'ouverture, VS Code propose d'installer les **recommandées** :

- **Ruff** et **ty** (éditeur Astral) ;
- **Python** et **Python Debugger** (Microsoft) ;
- **Docker DX** ;
- **Kubernetes** (Microsoft), pour le chart Helm ;
- **SonarQube for IDE** (SonarSource), voir plus bas.

Il signale aussi comme **déconseillées** celles qui font double emploi avec ruff et ty : Pylance, Mypy, Pylint, Flake8, Black et isort.

Pylance et Pylint sont **éteintes automatiquement sur ce projet**, par des réglages de `.vscode/settings.json` (`"python.languageServer": "None"` et `"pylint.enabled": false`). Elles restent actives pour vos autres projets.

Pour les autres extensions déconseillées, VS Code n'offre pas de réglage de ce type. Si l'une d'elles est installée un jour, il faudra la désactiver à la main : *Extensions*, clic droit, puis **Désactiver (espace de travail)**.

**Chart Helm** : les fichiers de `helm/suivi-delivery/templates/` contiennent des `{{ … }}` et ne sont donc pas du YAML pur. `.vscode/settings.json` les déclare comme des modèles Helm, un type fourni par l'extension Kubernetes : sans elle, VS Code y signale de fausses erreurs YAML. `Chart.yaml` et `values.yaml` restent vérifiés comme du YAML.

**SonarCloud en local** : SonarCloud est un service qui analyse la qualité du code. L'extension *SonarQube for IDE* affiche ses remarques directement dans l'éditeur (onglet *Problèmes*), sans attendre une PR. Elle est reliée au projet par `.vscode/settings.json` et applique donc les mêmes règles.

Il faut la connecter une fois sur chaque poste : panneau **SonarQube**, *Connected Mode*, ajouter une connexion SonarCloud (organisation `artenola`) avec un jeton personnel. Ce jeton reste sur le poste, jamais dans Git.

L'environnement Python utilisé est `backend/.venv`, réglé dans `.vscode/settings.json`. En cas de message « Unable to import 'app…' », vérifiez avec *Python : Sélectionner l'interpréteur* que c'est bien lui qui est choisi.

## Conventions de l'API

| Méthode | Usage | Succès | Erreurs |
| --- | --- | --- | --- |
| `GET /api/resources` | lister | 200 | 400 |
| `GET /api/resources/{id}` | lire | 200 | 404 |
| `HEAD` | comme `GET`, sans le corps | 200 | 404 |
| `OPTIONS` | méthodes possibles (en-tête `Allow`) | 204 | 404 |
| `POST /api/resources` | créer | 201 + en-tête `Location` | 400, 409, 415, 422 |
| `PUT /api/resources/{id}` | remplacer entièrement | 200 | 400, 404, 409, 415, 422 |
| `PATCH /api/resources/{id}` | modifier les champs envoyés | 200 | 400, 404, 409, 415, 422 |
| `DELETE /api/resources/{id}` | supprimer | 204 | 404, 409 |
| autre méthode | | | 405 + en-tête `Allow` |

Signification des erreurs :

- **400** : la demande est illisible (JSON mal formé, paramètre d'URL invalide).
- **404** : l'URL ne désigne aucun élément.
- **405** : méthode impossible sur cette URL ; l'en-tête `Allow` donne les méthodes possibles.
- **409** : la valeur est déjà utilisée, l'élément est encore utilisé ailleurs, ou la demande rendrait les données incohérentes.
- **415** : le corps n'est pas du JSON.
- **422** : le contenu est invalide (champ manquant, mauvais format, champ inconnu, référence vers un élément inexistant).

Le détail, avec les codes de 1xx à 5xx, est dans [docs/api.md](docs/api.md).

## Documentation

- [docs/comprendre-le-code/](docs/comprendre-le-code/README.md) : guide pas à pas du code du backend (découpage, chaque fichier, recette pour ajouter une ressource, aide-mémoire Python).
- [docs/architecture.md](docs/architecture.md) : découpage du programme, trajet d'une requête, choix et limites.
- [docs/frontend.md](docs/frontend.md) : interface web (outils, lancement, écran « Ce qui tourne », code).
- [docs/deploiement.md](docs/deploiement.md) : réglages, images Docker, **lancer sur son poste** (§ 7) et sur un cluster.
- [docs/modele-de-donnees.md](docs/modele-de-donnees.md) : tables, liens et règles métier.
- [docs/api.md](docs/api.md) : URLs, champs, règles de saisie, exemple pas à pas, organisation du code.
- [docs/glossaire.md](docs/glossaire.md) : le nom anglais, dans le code, de chaque mot métier (le code est en anglais, les commentaires et la doc en français).
- [docs/git.md](docs/git.md) : façon de travailler avec Git (branches, pull requests) et ménage des branches déjà fusionnées.
- [docs/ci.md](docs/ci.md) : les vérifications automatiques à chaque PR (GitHub).
