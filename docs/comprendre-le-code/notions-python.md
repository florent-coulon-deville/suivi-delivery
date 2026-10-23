# Aide-mémoire : les notions Python utilisées dans le code

| Écriture | Ce que ça veut dire | Exemple dans le code |
| --- | --- | --- |
| `{"code": "cb01", "id": 2}` | un **dictionnaire** : des valeurs rangées par nom | chaque ligne d'une table |
| `line["code"]` | lire la valeur rangée sous le nom `code` | partout |
| `line.get("code")` | pareil, mais renvoie `None` au lieu d'une erreur si le nom n'existe pas | `storage.py` |
| `[x["id"] for x in list]` | une **liste construite en une ligne** : l'`id` de chaque élément | `consistency.py` |
| `{**a, **b}` | un nouveau dictionnaire qui fusionne `a` puis `b` (`b` l'emporte) | `{**current, **changes}` |
| `def f(**criteria)` | la fonction accepte autant de paramètres nommés qu'on veut, rangés dans le dictionnaire `criteria` | `Table.list_all(**criteria)` |
| `f(**criteria)` | l'inverse : passe un dictionnaire comme paramètres nommés | `table.find(**criteria)` |
| `f"Cluster {id_} introuvable"` | une **f-string** : un texte dans lequel les `{…}` sont remplacés par leur valeur | messages d'erreur |
| `x: int`, `-> dict` | des **annotations de type** : « x est un nombre », « la fonction renvoie un dictionnaire ». Python ne les vérifie pas en cours d'exécution, mais `ty` et FastAPI s'en servent. | partout |
| `int \| None` | « un nombre, ou rien » | champs facultatifs |
| `@router.get("/…")` | un **décorateur** : il enregistre la fonction juste en dessous auprès de FastAPI | toutes les routes |
| `lambda s: s.clusters.update(…)` | une **mini-fonction** écrite sur une ligne, qu'on passe à une autre fonction | `apply_if_consistent` |
| `raise HTTPException(409, "…")` | **lever une erreur** : la fonction s'arrête, et FastAPI répond avec ce code et ce message | `routes/__init__.py` |
| `class Table:` | une **classe** : un modèle d'objet qui regroupe des données (`self._rows`) et des actions (`add`, `read`…) | `storage.py` |
| `self` | dans une méthode, l'objet lui-même | `self._rows` |
| `class EquipeCreation(Entry):` | **héritage** : `EquipeCreation` reprend tout ce que définit `Entry`, et y ajoute ses champs | `schemas.py` |
| `"""Text…"""` sous une fonction | une **docstring** : la documentation de la fonction | partout |
| `from app.storage import Storage` | **importer** un élément d'un autre fichier | en tête de chaque fichier |
| `async def` / `await` | du code **asynchrone**, qui peut attendre sans bloquer le serveur | seulement dans `http.py` |

## Les mots de FastAPI et Pydantic

| Mot | Sens |
| --- | --- |
| **route** | une adresse et une méthode (`GET /api/clusters`) associées à une fonction |
| **routeur** (`APIRouter`) | un groupe de routes, un par fichier de `routes/` |
| **dépendance** (`Depends`) | un paramètre de route que FastAPI remplit tout seul, comme `storage: StorageDep` |
| **schéma / modèle** (`BaseModel`) | la description d'un JSON ; Pydantic le vérifie automatiquement |
| **`model_dump()`** | transforme un schéma en dictionnaire |
| **`exclude_unset=True`** | dans `model_dump`, ne garde que les champs réellement envoyés |
| **middleware** | un intermédiaire qui voit passer toutes les requêtes avant les routes |
| **Swagger** | la page `/api/docs`, générée automatiquement à partir des routes et des schémas |
