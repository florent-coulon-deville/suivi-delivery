# 5. Les routes : le modèle commun — `routes/__init__.py` et `routes/clusters.py`

Une **route** associe une adresse et une méthode HTTP (par exemple `GET /api/clusters/7`) à une fonction Python. Chaque fichier de `routes/` regroupe toutes les routes d'**une** ressource.

On prend les **clusters** comme exemple, car c'est la ressource la plus simple. Toutes les autres suivent exactement le même modèle.

## Les outils communs — `routes/__init__.py`

### Récupérer le stockage dans une route

```python
def _storage(request: Request) -> Storage:
    return request.app.state.storage

StorageDep = Annotated[Storage, Depends(_storage)]
```

C'est une **dépendance** FastAPI. Quand une route a un paramètre `storage: StorageDep`, FastAPI appelle `_storage()` et passe le résultat à la route. Les routes n'ont donc pas à savoir où le stockage est rangé : c'est dans `app.state`, comme vu en page 2.

### Les vérifications qui arrêtent tout

| Fonction | Vérifie | Sinon |
| --- | --- | --- |
| `read_or_404(table, id, "Cluster")` | l'élément demandé **dans l'adresse** existe ; le renvoie | **404** « Cluster 7 introuvable » |
| `check_reference(table, id, "Application")` | un identifiant envoyé **dans le corps** existe | **422** |
| `check_unique(table, message, excluding_id, **criteria)` | aucune **autre** ligne n'a ces valeurs | **409** |
| `check_unused(table, message, **criteria)` | plus rien ne fait référence à l'élément, avant de le supprimer | **409** |
| `add_location(request, response, id)` | — ajoute l'en-tête `Location: /api/clusters/3` après une création | — |

Toutes fonctionnent de la même façon :

```python
def check_unique(table: Table, message: str, excluding_id: int | None = None, **criteria) -> None:
    existing_installation = table.find(**criteria)
    if existing_installation is not None and existing_installation["id"] != excluding_id:
        raise HTTPException(status.HTTP_409_CONFLICT, message)
```

**`raise`** *lève* une erreur. La fonction s'arrête net, et la route qui l'a appelée aussi. FastAPI attrape l'erreur et répond avec le code et le message, par exemple `409 {"detail": "Le code cb01 est déjà utilisé"}`.

C'est ce qui rend les routes courtes : chaque vérification s'écrit en une ligne, sans `if` ni `return` dans la route.

`excluding_id` sert en modification : un cluster qui garde son propre code n'est pas un doublon de lui-même.

## Une ressource complète — `routes/clusters.py`

### Le routeur

```python
router = APIRouter(prefix="/clusters", tags=["Clusters"])
OBJECT = "Cluster"   # pour les messages : « Cluster 7 introuvable »
```

### Lister et lire (GET)

```python
@router.get("", response_model=list[Cluster], summary="Lister les clusters")
def list_all(storage: StorageDep):
    return sorted(storage.clusters.list_all(), key=lambda c: c["code"])


@router.get("/{cluster_id}", response_model=Cluster, responses=R404, summary="Lire un cluster")
def read(cluster_id: int, storage: StorageDep):
    return read_or_404(storage.clusters, cluster_id, OBJECT)
```

- **`@router.get(...)`** est un *décorateur* : il enregistre la fonction juste en dessous comme réponse à `GET /api/clusters/…`.
- **Les paramètres sont remplis par FastAPI** :
  - `cluster_id: int` vient de `{cluster_id}` dans l'adresse, et est converti en nombre ;
  - `storage` vient de la dépendance.
- **`response_model=Cluster`** : la réponse est mise en forme selon ce schéma, et documentée dans Swagger.
- **`responses=R404`** : ajoute la réponse 404 dans Swagger. C'est de la documentation uniquement.
- **Ce que la fonction renvoie devient le JSON de la réponse**, avec le code 200 par défaut.

### Créer (POST)

```python
@router.post("", response_model=Cluster, status_code=status.HTTP_201_CREATED, responses=R409,
             summary="Créer un cluster")
def create(data: ClusterCreation, request: Request, response: Response, storage: StorageDep):
    check_unique(storage.clusters, f"Le code {donnees.code} est déjà utilisé", code=data.code)
    cluster = storage.clusters.add(data.model_dump())
    add_location(request, response, cluster["id"])
    return cluster
```

1. `data: ClusterCreation` : FastAPI a déjà vérifié le JSON avec le schéma (page 4).
2. On vérifie l'unicité du code (sinon 409).
3. On transforme le schéma en dictionnaire avec `model_dump()`, et on l'ajoute à la table.
4. On ajoute l'en-tête `Location`.
5. `status_code=201` : la réponse part avec le code « créé ».

### Modifier (PATCH et PUT) : une seule fonction pour les deux

```python
def save(storage: Storage, cluster_id: int, changes: dict):
    """Enregistre une modification : les champs envoyés (PATCH) ou tous les champs (PUT)."""
    read_or_404(storage.clusters, cluster_id, OBJECT)
    if "code" in changes:
        check_unique(storage.clusters, f"Le code {changements['code']} est déjà utilisé",
                        excluding_id=cluster_id, code=changes["code"])
    return apply_if_consistent(storage, lambda s: s.clusters.update(cluster_id, changes))


@router.patch("/{cluster_id}", ...)
def update(cluster_id: int, data: ClusterUpdate, storage: StorageDep):
    return save(storage, cluster_id, data.model_dump(exclude_unset=True))


@router.put("/{cluster_id}", ...)
def replace(cluster_id: int, data: ClusterCreation, storage: StorageDep):
    return save(storage, cluster_id, data.model_dump())
```

- **Toute la différence entre PATCH et PUT tient dans `exclude_unset=True`** : on ne garde que les champs réellement envoyés. Sans cette option (PUT), tous les champs sont gardés, y compris les valeurs par défaut.
- **PATCH reçoit un `…Update`** (tout facultatif), **PUT un `…Creation`** (les champs obligatoires sont exigés).
- **La logique est écrite une seule fois** (`save`), donc les contrôles sont forcément les mêmes.
- **`apply_if_consistent(storage, lambda s: …)`** fait le changement sur une copie, vérifie les règles d'ensemble, puis l'applique pour de vrai (sinon 409). Voir page 7. Ici, ça empêche par exemple de passer en hors prod un cluster qui porte des namespaces de prod.

### Supprimer (DELETE)

```python
@router.delete("/{cluster_id}", status_code=status.HTTP_204_NO_CONTENT, ...)
def delete(cluster_id: int, storage: StorageDep) -> None:
    read_or_404(storage.clusters, cluster_id, OBJECT)
    check_unused(storage.namespaces, "Cluster utilisé par au moins un namespace", cluster_id=cluster_id)
    storage.clusters.delete(cluster_id)
```

La fonction ne renvoie rien (`-> None`), et la réponse est un 204 sans corps.

## Le patron à retenir

Chaque fichier de route contient, dans cet ordre :

1. **une docstring** qui résume les adresses et leurs codes retour ;
2. **`router`** et **`OBJECT`** ;
3. **une fonction `check(...)`**, si l'objet a des règles à vérifier aussi bien à la création qu'à la modification (pas pour les clusters, dont la seule règle est l'unicité du code) ;
4. **les routes** `list_all`, `read`, `create`, puis `save` (la logique commune), `update` (PATCH), `replace` (PUT) et `delete`.

Page suivante : [les routes plus riches](06-routes-riches.md).
