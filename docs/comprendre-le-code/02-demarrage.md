# 2. Le démarrage — `main.py`

## Qui lance quoi

```bash
uv run python -m app --reload
```

- **`python -m app`** exécute le fichier `app/__main__.py`. Il lit les réglages (`app/settings.py`), puis lance **uvicorn**, le serveur web.
- **uvicorn** écoute le port (8000 par défaut, ou `APP_PORT`) et transmet chaque requête à l'application, qu'il trouve dans la variable `app` du fichier `app/main.py`.
- **`--reload`** relance automatiquement le serveur quand un fichier change (pratique en développement). Sans `--reload`, c'est le lancement normal, celui d'un serveur ou d'un conteneur.

## Les réglages — `settings.py`

Tout ce qui change d'une installation à l'autre est lu dans des **variables d'environnement**, au démarrage :

| Variable | Rôle | Défaut |
| --- | --- | --- |
| `APP_HOST` | adresse d'écoute | `127.0.0.1` |
| `APP_PORT` | port d'écoute | `8000` |
| `APP_LOG_LEVEL` | détail des journaux | `info` |
| `APP_DOCS` | Swagger visible (`oui` / `non`) | `oui` |
| `APP_DB_HOST`, `APP_DB_PORT`, `APP_DB_NAME`, `APP_DB_SCHEMA`, `APP_DB_USER`, `APP_DB_PASSWORD` | la base PostgreSQL (et le schéma de nos tables) | sans `APP_DB_HOST` : données en mémoire |
| `APP_KEYCLOAK_URL`, `APP_KEYCLOAK_REALM` | Keycloak (adresse interne), son domaine | sans `APP_KEYCLOAK_URL` : aucun jeton accepté |
| `APP_KEYCLOAK_CLIENT_SECRET` | clé du client de l'API dans Keycloak (écran Comptes) | aucune : écran Comptes indisponible |
| `APP_FRONTEND_URL` | adresse publique de l'interface, sous laquelle Keycloak est servi (émetteur des jetons) | `http://localhost:8080` |

`read_settings()` renvoie un objet `Settings` qui contient ces valeurs ; celles de la base sont regroupées dans `settings.base` (un `DatabaseSettings`, ou `None` sans `APP_DB_HOST`), celles de la sécurité dans `settings.security` (un `SecuritySettings`). Les secrets ne sont jamais affichés : ni quand on affiche les réglages (`repr=False`), ni dans les messages d'erreur. Une valeur impossible lève `InvalidSetting` : le démarrage s'arrête avec un message clair. Détails et exemples : [docs/deploiement.md](../deploiement.md).

## La variable `app`

Tout en bas de `main.py` :

```python
settings = read_settings()
app = create_application(settings.base, docs=settings.docs, security=settings.security)
```

L'application est créée avec la base, le choix d'afficher ou non Swagger et les réglages de sécurité, tous venus des réglages.

## `create_application()`, pas à pas

```python
def create_application(base: DatabaseSettings | None = None, docs: bool = True, ...) -> FastAPI:
    # 1. L'application vide, avec la documentation Swagger sous /api/docs (sauf si docs=False)
    app = FastAPI(title="Suivi de la delivery", version=VERSION, openapi_tags=TAGS,
                  docs_url="/api/docs", openapi_url="/api/openapi.json", redoc_url=None)

    # 2. Les données : des tables vides en mémoire, rangées dans app.state (remplacées au démarrage
    #    par la base, s'il y en a une)
    app.state.storage = MemoryStorage()

    # 3. Les routes de chaque fichier de routes/, toutes préfixées par /api
    routers = [module.router for module in (environments, clusters, applications, ...)]
    for router in routers:
        app.include_router(router, prefix="/api")

    # 4. Les règles HTTP communes (voir page 8)
    routes = [(re.compile("^/api" + route.path_regex.pattern.lstrip("^")), route.methods or set())
              for router in routers for route in router.routes if isinstance(route, APIRoute)]
    app.add_middleware(RequestTransaction)          # une transaction par requête (page 3)
    app.add_middleware(HttpMethods, routes=routes)
    app.add_exception_handler(RequestValidationError, invalid_request)
    app.add_exception_handler(psycopg.errors.IntegrityError, database_rejection)  # 409, page 3
    return app
```

| Étape | Ce qui se passe |
| --- | --- |
| 1 | **FastAPI** crée l'application. `TAGS` (en haut du fichier) donne les titres et descriptions des rubriques de Swagger. |
| 2 | **`app.state`** est un espace où l'on range ce qui doit vivre aussi longtemps que l'application. On y met le stockage, que les routes récupéreront (page 5). |
| 3 | Chaque fichier de `routes/` expose une variable `router`. `include_router` ajoute toutes ses routes, préfixées par `/api` : `/clusters` devient `/api/clusters`. Exception : `health.py`, branché sans préfixe. Ses adresses (`/startupz`, `/readyz`, `/livez`) sont des *probes* : Kubernetes les appelle régulièrement pour savoir si l'API est démarrée, prête, et toujours vivante. |
| 4 | On branche la transaction par requête ([le stockage](03-stockage.md)). On donne à `http.py` la liste des chemins et des méthodes de chaque route (pour OPTIONS et l'en-tête `Allow`), et on branche le choix des codes 400 / 404 / 422, et le 409 d'une saisie refusée par la base. |

## Le démarrage et l'arrêt : `lifespan`

Au début de `create_application`, une petite fonction dit quoi faire au démarrage et à l'arrêt du serveur :

```python
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
        if base is not None:
            storage = PostgresStorage(base)
            storage.open()                        # démarrage : se connecte, vérifie les tables
            app.state.storage = storage
        app.state.started = True                    # /startupz et /readyz répondent « prêt »
        yield                                        # … l'API tourne …
        app.state.storage.close()                  # arrêt : ferme les connexions
```

Elle est donnée à FastAPI (`FastAPI(lifespan=lifespan, …)`). Tout ce qui est avant `yield` s'exécute au démarrage, tout ce qui est après, à l'arrêt.

Pourquoi ne pas se connecter à la base tout de suite ? Parce que les tests importent `main.py`, et ils se connecteraient à chaque fois. Ici, la connexion n'est ouverte que lorsque le serveur démarre vraiment.

Si la base ne répond pas, ou si les tables n'existent pas (Liquibase pas encore lancé), `open()` arrête le démarrage avec un message clair.

`create_application` prépare aussi la sécurité, sans contacter Keycloak tout de suite :

- le **vérificateur** des jetons (`Verificateur.pour(securite)`), qui lira les clés de Keycloak au premier jeton reçu ;
- l'**annuaire** des comptes (`KeycloakDirectory`), si la clé du client est donnée.

L'API ne garde aucun mot de passe : le compte `admin` est créé par Keycloak. Voir [la sécurité](11-securite.md).

## Pourquoi une fonction ?

On aurait pu écrire tout cela directement dans le fichier. La fonction sert **aux tests** : chacun obtient une application **neuve, avec des données vides** (en mémoire, ou dans la base des tests, vidée avant chaque test : voir [les tests](09-tests.md)). Aucun test ne voit les données d'un autre.

## Ce qu'il faut retenir

- `main.py` **ne contient aucune règle** : il branche les morceaux.
- Ajouter une ressource demande d'ajouter son module dans la liste de l'étape 3, et c'est tout.

Page suivante : [le stockage](03-stockage.md).
