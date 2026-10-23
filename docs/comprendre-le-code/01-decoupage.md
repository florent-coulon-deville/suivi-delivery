# 1. Le découpage en modules

## La carte

```Plaintext
backend/
├── pyproject.toml          dépendances + réglages de pytest, ruff, ty
├── app/                    le code de l'API
│   ├── __main__.py            lancement (python -m app)
│   ├── settings.py            les réglages, lus dans les variables d'environnement
│   ├── main.py             ① assemble l'application
│   ├── http.py             ② règles HTTP communes (avant les routes)
│   ├── schemas.py          ③ forme des données échangées (vérification à l'entrée)
│   ├── routes/             ④ une ressource par fichier
│   │   ├── __init__.py        outils communs à toutes les routes
│   │   ├── clusters.py, modules.py, installations.py…
│   │   └── health.py           adresses de santé pour Kubernetes (/startupz, /readyz, /livez)
│   ├── consistency.py        ⑤ règles d'ensemble (plusieurs objets à la fois)
│   ├── versions.py            comparaison de numéros de version
│   ├── security.py            vérification des jetons de Keycloak (identité, rôle)
│   ├── access.py               qui a le droit de faire quoi (401, 403)
│   ├── directory.py            les comptes, gérés dans Keycloak (écran Comptes)
│   ├── configuration.py       export de toute la configuration en fichier Excel
│   ├── import_configuration.py  import de ce fichier Excel
│   ├── audit_log.py             journal des actions (qui a saisi quoi)
│   ├── storage.py         ⑥ les données : les opérations communes, et la version en mémoire
│   ├── storage_postgres.py   les mêmes opérations, dans la base PostgreSQL
│   └── transactions.py        une transaction par requête (base PostgreSQL)
├── scripts/load_demo.py données de démonstration
├── scripts/login.py     connexion d'une personne pour ses scripts (jeton hors ligne de Keycloak)
└── tests/                  vérification automatique de tout ce qui précède
```

À côté de `backend/`, on trouve :

- `postgres/` : l'image de la base de données ;
- `liquibase/` : la création des tables, lancée avant l'API (voir [postgresql.md](../postgresql.md)) ;
- `keycloak/` : les comptes et la connexion (voir [keycloak.md](../keycloak.md)).

## Qui utilise qui

Une flèche `A → B` veut dire « A utilise B » (A contient `from app.B import …`).

```mermaid
flowchart TD
    main["main.py<br/>assemble"] --> http["http.py<br/>règles HTTP"]
    main --> routes["routes/*.py<br/>une ressource par fichier"]
    main --> stockage["storage.py<br/>les données"]
    main --> transactions["transactions.py<br/>une transaction par requête"]
    transactions --> postgres["storage_postgres.py<br/>dans PostgreSQL"]
    postgres --> stockage
    routes --> commun["routes/__init__.py<br/>404, 409, 422, Location"]
    routes --> schemas["schemas.py<br/>forme des données"]
    routes --> coherence["consistency.py<br/>règles d'ensemble"]
    commun --> stockage
    coherence --> versions["versions.py<br/>1.4 < 1.10"]
    coherence --> stockage
    versions --> schemas
```

Ce qu'il faut remarquer :

- **`storage.py` ne dépend de rien** : il ne connaît ni HTTP, ni FastAPI, ni les règles métier. Il range et rend des données, c'est tout.
- **`schemas.py` ne dépend de rien non plus** (à part Pydantic) : il décrit la forme des données.
- **Les routes sont au centre** : elles utilisent les schémas pour lire la demande, les outils communs et la cohérence pour vérifier, et le stockage pour enregistrer.
- **`main.py` est le seul à tout connaître** : son rôle est de brancher les morceaux entre eux.

## Pourquoi ce découpage

**Un fichier = un rôle.** Quand on cherche quelque chose, on sait où regarder :

| Je veux… | Je vais dans… |
| --- | --- |
| ajouter un champ à un objet | `schemas.py`, puis la route concernée |
| changer une règle de saisie (format, minuscules…) | `schemas.py` |
| changer une règle propre à un objet (unicité, suppression interdite…) | `routes/<object>.py` |
| changer une règle qui croise plusieurs objets | `consistency.py` |
| changer un code retour HTTP général | `http.py` |
| changer la façon de lire ou d'écrire dans la base | `storage_postgres.py` |

**Toutes les routes sont bâties sur le même modèle.** Une fois `clusters.py` compris (page 5), on lit `modules.py` ou `slots.py` sans effort : seules les vérifications changent.

**Les règles sont rangées selon leur portée :**

| Portée de la règle | Exemple | Où elle vit | Code retour |
| --- | --- | --- | --- |
| un **champ** | le trigramme fait 3 caractères | `schemas.py` | 422 |
| un **objet** | le code d'un cluster est unique | `routes/<object>.py` | 409 ou 422 |
| **plusieurs objets** | pas de snapshot en prod | `consistency.py` | 409 |
| **toute requête** | un POST doit contenir du JSON | `http.py` | 400, 404, 405, 415 |

## Le trajet d'une requête

Exemple : `POST /api/installations` avec un corps JSON.

```mermaid
sequenceDiagram
    participant N as Navigateur / client
    participant H as http.py
    participant S as schemas.py
    participant R as routes/installations.py
    participant C as consistency.py
    participant T as storage.py
    N->>H: POST /api/installations {…}
    H->>H: méthode permise ? corps JSON ? (sinon 405 / 415)
    H->>S: (via FastAPI) le JSON a-t-il la bonne forme ?
    S-->>N: sinon 400 / 422
    S->>R: données vérifiées
    R->>R: références, module réservé, paramètres (sinon 422)
    R->>C: essai sur une copie
    C-->>N: incohérent → 409
    C->>T: cohérent → enregistrement
    R-->>N: 201 + Location
```

Chaque étape **arrête tout** en cas de problème : la suivante ne s'exécute jamais avec des données fausses.

Page suivante : [le démarrage](02-demarrage.md).
