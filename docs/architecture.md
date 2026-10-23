# Architecture du programme

## 1. À quoi sert le programme

C'est une **API** : un service qu'on interroge par des adresses web (`/api/modules`, `/api/installations`…) et qui répond en JSON.

L'interface web passe par cette API. C'est le serveur de l'interface (Next.js) qui l'appelle, jamais le navigateur.

Elle sert à deux choses :

- **décrire le socle** : applications, namespaces, modules, dépendances, environnements, clusters ;
- **suivre les déploiements** : quelle version de quel module tourne sur quel emplacement, avec quels paramètres, en vérifiant que tout est compatible.

Le détail des objets est dans [modele-de-donnees.md](modele-de-donnees.md), et celui des adresses dans [api.md](api.md).

L'interface web (dossier `frontend/`) est décrite à part, dans [frontend.md](frontend.md).

Pour lire le code fichier par fichier, voir le guide [comprendre-le-code/](comprendre-le-code/README.md).

## 2. Le découpage

```Plaintext
backend/
├── pyproject.toml        dépendances et réglages des outils (pytest, ruff, ty)
├── .python-version       Python 3.14
├── .env.example          modèle des réglages (variables d'environnement)
├── app/
│   ├── __main__.py       lancement (python -m app) : lit les réglages, démarre le serveur
│   ├── settings.py       réglages lus dans les variables d'environnement (port, base de données…)
│   ├── main.py           assemble l'application : branche les routes et les règles HTTP
│   ├── http.py           règles HTTP communes : HEAD, OPTIONS, Allow, 400 / 404 / 415 / 422
│   ├── schemas.py        forme des données échangées et règles de saisie
│   ├── storage.py       les opérations sur les données (une « table » par type d'objet), et leur version en mémoire
│   ├── storage_sqlite.py les mêmes opérations, dans un fichier SQLite
│   ├── sql/              la structure de la base (tables), appliquée par l'API au démarrage
│   ├── transactions.py   une transaction par requête (base SQLite)
│   ├── consistency.py      les règles d'ensemble (compatibilités, prod, clusters…)
│   ├── versions.py       comparaison de numéros de version (1.4 < 1.10 < 2.0)
│   ├── audit_log.py        le journal des actions
│   ├── configuration.py  toute la configuration dans un fichier Excel (export)
│   ├── import_configuration.py  import de ce fichier (fusion, aperçu, tout ou rien)
│   └── routes/           une ressource par fichier
│       ├── __init__.py   vérifications communes : 404, 409, 422, en-tête Location
│       └── applications.py, namespaces.py, modules.py…
└── tests/                un fichier de tests par ressource, plus les règles HTTP et d'ensemble
```

C'est la **version légère** : il n'y a que deux programmes, `backend/` (l'API, avec ses données dans un fichier SQLite) et `frontend/` (l'interface). Pas de serveur de base de données, pas d'outil de structure à part, pas de connexion.

Chaque fichier a **un seul rôle**. Pour savoir où intervenir :

| Je veux… | Je vais dans… |
| --- | --- |
| ajouter un champ à un objet | `schemas.py`, puis la route concernée |
| changer une règle de saisie (format, minuscules…) | `schemas.py` |
| changer une règle propre à un objet (unicité, suppression interdite…) | `routes/<object>.py` |
| changer une règle qui croise plusieurs objets | `consistency.py` |
| changer un code retour HTTP général | `http.py` |
| changer la structure de la base (table, colonne) | un **nouveau** fichier numéroté dans `app/sql/` (voir [sqlite.md](sqlite.md)) |
| ajouter un réglage (variable d'environnement) | `settings.py`, puis `docs/deploiement.md` |
| ajouter une ressource | copier une route existante, ajouter ses schémas, sa table (`storage.py` et un nouveau fichier de `app/sql/`), la brancher dans `main.py`, écrire ses tests |

## 3. Le trajet d'une requête

Exemple : on enregistre une installation (`POST /api/installations`).

1. **`http.py`** vérifie que la méthode est permise sur cette adresse et que le corps est du JSON. Sinon : 405 ou 415.
2. **`schemas.py`** (via Pydantic) vérifie la forme du JSON : champs présents, bons types, aucun champ inconnu. Sinon : 400 ou 422, sans même entrer dans la route.
3. **`routes/installations.py`** vérifie les règles propres à l'objet :
   - les éléments référencés existent ;
   - la version appartient au module réservé de l'emplacement ;
   - les paramètres ont le bon type et sont affectés au namespace.

   Sinon : 422.
4. **`consistency.py`** fait la saisie **à l'essai**, puis vérifie que tout reste cohérent : modules requis présents et compatibles, pas de snapshot en prod, clusters du bon type… Sinon : 409, l'essai est annulé et rien n'est modifié.
5. La route répond **201**, avec l'adresse du nouvel élément dans l'en-tête `Location`.
6. **`transactions.py`** enregistre la transaction de la requête (`commit`) juste avant d'envoyer cette réponse.

Au tout début, la requête a pris le verrou « une requête à la fois » de la base (`transactions.py`, `storage_sqlite.py`). Aucune autre requête ne passe pendant ce temps.

## 4. Les choix et leurs raisons

| Choix | Pourquoi |
| --- | --- |
| **Un seul projet Python, un fichier par rôle** | C'est simple à lire : on suit le code de haut en bas, sans sauter de couche en couche. |
| **FastAPI + Pydantic** | Ils vérifient automatiquement les données reçues et génèrent la documentation interactive Swagger, ce qui évite d'écrire ces contrôles à la main. |
| **SQLite, une vraie table par objet** (`storage_sqlite.py`) | Toutes les données dans un seul fichier, sans serveur de base à installer ni à surveiller. Les données sont rangées en colonnes et se lisent en SQL. La base contrôle elle-même liens, unicité et valeurs : c'est un filet de sécurité. Voir [sqlite.md](sqlite.md). |
| **Structure appliquée par l'API** (`app/sql/`) | Chaque évolution de la structure est un fichier SQL numéroté, gardé dans Git. L'API applique au démarrage ceux que la base n'a pas encore (`PRAGMA user_version`) : rien à lancer avant elle. |
| **Pas de connexion** | Version légère : ni comptes, ni mots de passe, ni rôles. Tout le monde peut tout faire ; l'interface est à réserver à un réseau de confiance. |
| **Pas d'ORM** (SQLAlchemy…) | Quelques requêtes SQL simples, écrites avec le module `sqlite3` livré avec Python, suffisent. Un ORM ajouterait une couche à apprendre, sans besoin réel. |
| **Une transaction par requête, une requête à la fois** (`transactions.py`) | Une saisie qui écrit plusieurs éléments est enregistrée entièrement, ou pas du tout. Et le contrôle de cohérence voit toujours des données à jour. |
| **Données en mémoire sans base** (`MemoryStorage`) | Les tests et les essais rapides n'ont besoin de rien installer. Les mêmes tests tournent aussi sur un fichier SQLite. |
| **Liens par identifiant** (`application_id: 3`) | C'est comme une base de données : on ne recopie jamais une information. Le reste se déduit, comme le nom du namespace ou ce qui tourne sur un emplacement (la dernière installation). |
| **Un fichier par ressource, toujours bâti sur le même modèle** | Une fois qu'on en a compris un, on les comprend tous. |
| **PATCH et PUT passent par la même fonction `save`** | Les mêmes contrôles s'appliquent dans les deux cas, sans copier-coller. |
| **Règles d'ensemble dans `consistency.py`, avec un essai** | C'est la règle d'or : on ne peut rien saisir d'incohérent. Les règles qui croisent plusieurs objets sont au même endroit, et l'essai (annulé en cas de refus) garantit qu'un refus ne laisse aucune trace. |
| **Tout en minuscules, formats contrôlés** | Ça évite les doublons du type `INT` / `int`, et produit des noms valides pour OpenShift. |
| **Codes HTTP stricts** (`http.py`) | Un client (l'interface web, un script) sait exactement quoi faire de chaque réponse. |
| **Tests par appels HTTP réels**, sur une application neuve à chaque test | On teste ce que verra l'utilisateur, et aucun test ne dépend d'un autre. Ils tournent en mémoire, et sur une vraie base SQLite (CI). |
| **Outils Astral : uv, ruff, ty** | Un seul éditeur, des outils rapides, et des réglages regroupés dans `pyproject.toml`. |

## 5. Limites actuelles (connues et assumées)

- **Une requête à la fois, un seul exemplaire de l'API** : la base est un fichier, sur un seul disque. C'est sans effet pour une équipe. Pour plusieurs exemplaires, il faudrait revenir à une base serveur (PostgreSQL).
- **Pas de connexion ni de droits** : toute personne qui atteint l'interface peut tout saisir, et le journal ne dit pas qui a fait quoi. À réserver à un réseau de confiance ; une gestion de comptes est à prévoir dans une étape suivante.
- **Le contrôle de cohérence relit toutes les installations** à chaque saisie sensible. C'est instantané pour quelques milliers d'éléments. Au-delà, il faudra ne vérifier que l'environnement touché.
- **Sauvegarde** : copier le fichier, ou exporter en Excel (voir [sqlite.md](sqlite.md#sauvegarder)) ; à organiser avant la mise en service.
