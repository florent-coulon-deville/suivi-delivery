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

**Version légère** : deux programmes seulement (l'API et l'interface), les données dans un seul fichier **SQLite**, et **pas de connexion** : tout le monde peut tout lire et tout saisir. À réserver à un réseau de confiance.

## Les mots à connaître

| Mot | Sens |
| --- | --- |
| **MEP** | mise en production : l'installation d'une nouvelle version |
| **API** ou **backend** | le programme qui garde les données et vérifie les règles (Python) |
| **interface** ou **frontend** | les pages web que l'on utilise dans le navigateur (Next.js) |
| **image** / **conteneur** | une image Docker est un programme prêt à lancer, avec tout ce dont il a besoin ; un conteneur est une image en train de tourner |
| **SQLite** | une base de données rangée dans un seul fichier, lue et écrite directement par l'API (pas de serveur de base à installer) |
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
├── backend/                API (Python, FastAPI)
│   ├── .python-version     version de Python utilisée (3.14)
│   ├── pyproject.toml      dépendances et réglages des outils (pytest, ruff, ty)
│   ├── uv.lock             versions exactes des dépendances (fabriqué par uv, ne pas modifier à la main)
│   ├── .env.example        modèle des réglages pour le développement sans Docker
│   ├── Dockerfile          fabrication de l'image Docker du backend
│   ├── docker.example.env  modèle des réglages du conteneur (recopié dans deployment/docker.env)
│   ├── app/
│   │   ├── __main__.py     lancement (python -m app) avec les réglages
│   │   ├── settings.py     réglages lus dans les variables d'environnement (port, base de données…)
│   │   ├── main.py         crée l'application et branche les routes
│   │   ├── schemas.py      forme des données échangées (JSON) et règles de saisie
│   │   ├── storage.py      opérations sur les données (lister, ajouter…), version en mémoire
│   │   ├── storage_sqlite.py    les mêmes opérations dans la base SQLite
│   │   ├── sql/            la structure de la base (tables), appliquée par l'API au démarrage
│   │   ├── transactions.py une transaction par requête, une requête à la fois
│   │   ├── consistency.py  règles d'ensemble : on ne peut rien saisir d'incohérent
│   │   ├── http.py         règles HTTP communes (méthodes, codes retour)
│   │   ├── audit_log.py    journal des actions (quoi a été saisi, et quand)
│   │   └── routes/         une ressource par fichier (clusters, modules, installations…)
│   ├── scripts/
│   │   ├── load_demo.py données de démonstration, à charger dans une API démarrée
│   └── tests/              un fichier de tests par ressource (+ conftest.py : outils communs)
├── frontend/               interface web (Next.js + React + TypeScript) — voir docs/frontend.md
│   ├── .env.example        modèle des réglages pour le développement sans Docker
│   ├── Dockerfile          fabrication de l'image Docker du frontend (serveur Next.js)
│   ├── docker.example.env  modèle des réglages du conteneur (recopié dans deployment/docker.env)
│   ├── app/                les pages (« Ce qui tourne », « Saisie », « Import », « Journal ») et leurs actions côté serveur
│   ├── components/         les blocs d'affichage
│   └── lib/                accès à l'API (côté serveur), calcul de l'état, types
├── cicd/                   outils de la CI (voir docs/ci.md)
│   └── check_versions.py   vérifie que backend, frontend et chart ont le même numéro
├── release-please-config.json  versions automatiques : fichiers où release-please change le numéro (docs/ci.md § 5)
├── CHANGELOG.md            journal des versions, tenu par release-please
├── helm/suivi-delivery/    le chart Helm : la recette d'installation sur un cluster
├── .vscode/                réglages et extensions VS Code du projet
└── docs/
    ├── comprendre-le-code/ guide pas à pas du code du backend, fichier par fichier
    ├── architecture.md     découpage du programme, trajet d'une requête, choix
    ├── frontend.md         interface web : outils, lancement, écrans, code
    ├── deploiement.md      réglages, images Docker, lancement sur le poste et sur un cluster
    ├── sqlite.md           la base SQLite : fichier, tables, évolutions, sauvegarde
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
- [x] Données dans un fichier SQLite, tables créées par l'API elle-même
- [x] Interface web : écran « Ce qui tourne », espace de saisie, journal des actions
- [x] Export et import de toute la configuration dans un fichier Excel
- [ ] Connexion et comptes (version légère : pas de connexion pour l'instant)
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

Pour garder les données, donner à l'API un fichier SQLite (créé s'il n'existe pas, avec ses tables) :

```bash
APP_DB_FILE=donnees/suivi-delivery.sqlite uv run python -m app --reload   # depuis backend/
```

Swagger (documentation interactive, pour tester chaque appel) : <http://localhost:8000/api/docs>.

### Pas de connexion

Cette version n'a **ni comptes, ni mots de passe, ni rôles** : toute personne qui ouvre l'interface (ou appelle l'API) peut tout lire et tout saisir. La règle d'or reste : **rien d'incohérent ne peut être saisi**. Le journal note chaque saisie (quoi, quand), sans auteur.

L'API n'est jamais exposée hors du cluster (seule l'interface l'appelle) ; l'interface, elle, est à réserver à un réseau de confiance.

### Les données

Les données sont enregistrées dans **un seul fichier SQLite** (variable `APP_DB_FILE`). L'API crée le fichier et ses tables au premier démarrage, et les met à jour quand une nouvelle version en a besoin. Tout est expliqué dans [docs/sqlite.md](docs/sqlite.md).

- **Sans fichier** (`APP_DB_FILE` absente), l'API garde ses données en mémoire : elles sont perdues à l'arrêt.
- **Sur le poste**, avec `./deployment/docker-deploy.zsh`, le fichier est gardé dans le volume Docker `suivi-delivery-data-local`.
- **Repartir de zéro** : `./deployment/docker-deploy.zsh --reset`.
- **Sauvegarder** : l'export Excel (bouton « Exporter »), ou une copie du fichier (voir [docs/sqlite.md](docs/sqlite.md#sauvegarder)).
- **Un seul exemplaire de l'API** à la fois sur un même fichier.

Les tests travaillent en mémoire, ou sur un fichier de tests à part : ils ne touchent jamais aux données.

### L'interface web (frontend)

Pré-requis : [Node.js](https://nodejs.org) 26 et npm (sur Mac avec MacPorts : `sudo port install nodejs26 npm11`).

L'API doit tourner en même temps : c'est le serveur de l'interface qui l'appelle.

```bash
# depuis backend/ : charger des données de démonstration (facultatif)
uv run python scripts/load_demo.py

# depuis frontend/
npm install          # la première fois, ou après une mise à jour des dépendances
npm run dev          # interface sur http://localhost:5173
npm run typecheck    # vérifie les types (TypeScript) : doit passer avant chaque commit
```

L'annonce « New major version of npm available » peut être ignorée. Détails dans [docs/frontend.md](docs/frontend.md).

### Les réglages

Ce qui change d'une installation à l'autre (adresses, ports, fichier des données) se règle **au lancement**, par des variables d'environnement. On ne touche pas au code. Sans variable, les valeurs par défaut conviennent au développement.

| Application | Variables |
| --- | --- |
| Backend | `APP_HOST`, `APP_PORT`, `APP_LOG_LEVEL`, `APP_DOCS`, `APP_DB_FILE` (fichier SQLite) |
| Frontend | `API_URL` (adresse et port du backend), `PORT`, `INSTANCE_NAME`, `INSTANCE_COLOR` |
| Script de démo | `API_URL` |

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
