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
│   ├── storage_postgres.py  les mêmes opérations, dans la base PostgreSQL
│   ├── transactions.py   une transaction par requête (base PostgreSQL)
│   ├── consistency.py      les règles d'ensemble (compatibilités, prod, clusters…)
│   ├── versions.py       comparaison de numéros de version (1.4 < 1.10 < 2.0)
│   ├── security.py, access.py  vérification des jetons de Keycloak, contrôle des droits (401, 403)
│   ├── directory.py       les comptes, gérés dans Keycloak pour l'écran Comptes
│   ├── audit_log.py        le journal des actions
│   ├── configuration.py  toute la configuration dans un fichier Excel (export)
│   ├── import_configuration.py  import de ce fichier (fusion, aperçu, tout ou rien)
│   └── routes/           une ressource par fichier
│       ├── __init__.py   vérifications communes : 404, 409, 422, en-tête Location
│       └── applications.py, namespaces.py, modules.py…
└── tests/                un fichier de tests par ressource, plus les règles HTTP et d'ensemble
```

À côté de `backend/` et `frontend/`, on trouve :

- `postgres/` : l'image de la base de données, qui prépare ses deux schémas au premier démarrage ;
- `liquibase/` : la création des tables, lancée avant l'API (voir [postgresql.md](postgresql.md)) ;
- `keycloak/` : les comptes et la connexion (voir [keycloak.md](keycloak.md)).

Chaque fichier a **un seul rôle**. Pour savoir où intervenir :

| Je veux… | Je vais dans… |
| --- | --- |
| ajouter un champ à un objet | `schemas.py`, puis la route concernée |
| changer une règle de saisie (format, minuscules…) | `schemas.py` |
| changer une règle propre à un objet (unicité, suppression interdite…) | `routes/<object>.py` |
| changer une règle qui croise plusieurs objets | `consistency.py` |
| changer un code retour HTTP général | `http.py` |
| changer la structure de la base (table, colonne) | un **nouveau** fichier dans le module `liquibase/changelog/`, à la racine du projet (voir [postgresql.md](postgresql.md)) |
| ajouter un réglage (variable d'environnement) | `settings.py`, puis `docs/deploiement.md` |
| ajouter une ressource | copier une route existante, ajouter ses schémas, sa table (`storage.py` et Liquibase), la brancher dans `main.py`, écrire ses tests |

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

Au tout début, la requête a pris le verrou « une écriture à la fois » de la base (`transactions.py`). Aucune autre saisie ne passe pendant ce temps.

## 4. Les choix et leurs raisons

| Choix | Pourquoi |
| --- | --- |
| **Un seul projet Python, un fichier par rôle** | C'est simple à lire : on suit le code de haut en bas, sans sauter de couche en couche. |
| **FastAPI + Pydantic** | Ils vérifient automatiquement les données reçues et génèrent la documentation interactive Swagger, ce qui évite d'écrire ces contrôles à la main. |
| **PostgreSQL, une vraie table par objet** (`storage_postgres.py`) | Les données sont rangées en colonnes et se lisent en SQL. La base contrôle elle-même liens, unicité et valeurs : c'est un filet de sécurité. Plusieurs exemplaires de l'API peuvent tourner ensemble. |
| **Liquibase pour la structure** | Chaque évolution de la structure est un fichier SQL, gardé dans Git. Liquibase l'applique une seule fois, dans l'ordre, avant l'API. On sait toujours où en est chaque base (table `databasechangelog`). Voir [postgresql.md](postgresql.md). |
| **Keycloak pour les comptes et la connexion** | Un logiciel reconnu (Red Hat), qui suit les normes OAuth 2.1 et OpenID Connect, plutôt qu'un code maison. Il gère mots de passe, blocage après des échecs, renouvellement des jetons, connexion des scripts. Ses pages ressemblent à l'outil et passent par l'interface (`/auth`) : on ne voit pas Keycloak. L'API se contente de vérifier les jetons. Keycloak et l'API partagent la même base, chacun dans son schéma. Voir [keycloak.md](keycloak.md). |
| **Pas d'ORM** (SQLAlchemy…) | Quelques requêtes SQL simples, écrites avec `psycopg`, suffisent. Un ORM ajouterait une couche à apprendre, sans besoin réel. |
| **Une transaction par requête, une écriture à la fois** (`transactions.py`) | Une saisie qui écrit plusieurs éléments est enregistrée entièrement, ou pas du tout. Et le contrôle de cohérence voit toujours des données à jour, même avec plusieurs exemplaires de l'API. |
| **Données en mémoire sans base** (`MemoryStorage`) | Les tests et les essais rapides n'ont besoin de rien installer. Les mêmes tests tournent aussi sur PostgreSQL. |
| **Liens par identifiant** (`application_id: 3`) | C'est comme une base de données : on ne recopie jamais une information. Le reste se déduit, comme le nom du namespace ou ce qui tourne sur un emplacement (la dernière installation). |
| **Un fichier par ressource, toujours bâti sur le même modèle** | Une fois qu'on en a compris un, on les comprend tous. |
| **PATCH et PUT passent par la même fonction `save`** | Les mêmes contrôles s'appliquent dans les deux cas, sans copier-coller. |
| **Règles d'ensemble dans `consistency.py`, avec un essai** | C'est la règle d'or : on ne peut rien saisir d'incohérent. Les règles qui croisent plusieurs objets sont au même endroit, et l'essai (annulé en cas de refus) garantit qu'un refus ne laisse aucune trace. |
| **Tout en minuscules, formats contrôlés** | Ça évite les doublons du type `INT` / `int`, et produit des noms valides pour OpenShift. |
| **Codes HTTP stricts** (`http.py`) | Un client (l'interface web, un script) sait exactement quoi faire de chaque réponse. |
| **Tests par appels HTTP réels**, sur une application neuve à chaque test | On teste ce que verra l'utilisateur, et aucun test ne dépend d'un autre. Ils tournent en mémoire, et sur une vraie base PostgreSQL (CI). |
| **Outils Astral : uv, ruff, ty** | Un seul éditeur, des outils rapides, et des réglages regroupés dans `pyproject.toml`. |

## 5. Limites actuelles (connues et assumées)

- **Une écriture à la fois** : les saisies passent l'une après l'autre. C'est sans effet pour une équipe. Ce ne serait à revoir qu'avec des centaines de saisies par seconde.
- **Connexion et droits** : les comptes sont dans Keycloak, avec trois rôles (consultation, saisie, administration). Le rôle est lu dans le jeton : un rôle retiré prend effet en 5 minutes au plus. Voir [api.md § 0](api.md#0-connexion-et-droits) et [keycloak.md](keycloak.md).
- **Le contrôle de cohérence relit toutes les installations** à chaque saisie sensible. C'est instantané pour quelques milliers d'éléments. Au-delà, il faudra ne vérifier que l'environnement touché.
- **La configuration de Keycloak est importée une seule fois** (`keycloak/import/`), au premier démarrage. Pour la changer ensuite (rôle, client, durée), on passe par sa console d'administration, ou on repart d'une base neuve.

- **Sauvegarde de la base** : à prévoir avec l'équipe qui la fournit, avant la mise en service (voir [postgresql.md § 8](postgresql.md#8-sauvegarde)).
