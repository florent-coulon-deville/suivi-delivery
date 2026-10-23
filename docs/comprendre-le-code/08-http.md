# 8. Les règles HTTP — `http.py`

Ce fichier traite ce qui concerne **toutes** les requêtes, quelle que soit la ressource. Il contient deux morceaux.

## 1. Le « middleware » `HttpMethods`

Un **middleware** est un intermédiaire : il voit passer **chaque requête avant les routes**, et chaque réponse après. On l'utilise pour quatre règles qu'il serait pénible de répéter dans chaque route :

| Requête | Traitement |
| --- | --- |
| `OPTIONS /api/clusters/1` | répond directement **204** avec `Allow: GET, HEAD, PUT, PATCH, DELETE, OPTIONS`, sans passer par les routes |
| `HEAD /api/clusters` | transforme la requête en `GET`, puis **retire le corps** de la réponse (le code et les en-têtes restent identiques) |
| `POST`, `PUT` ou `PATCH` sans `Content-Type: application/json` | répond directement **415** |
| toute réponse **405** (méthode impossible) | remplace l'en-tête `Allow` par la liste complète des méthodes de l'adresse |

Pour savoir quelles méthodes existent sur une adresse, le middleware reçoit au démarrage (page 2) la liste de toutes les routes, chacune avec son expression de chemin et ses méthodes.

```python
def methods(self, path: str) -> set[str] | None:
    found = set()
    for expression, methods in self.routes:
        if expression.match(path):        # cette route correspond-elle à l'adresse ?
            found |= methods            # on ajoute ses méthodes
    if not found:
        return None                         # adresse inconnue : FastAPI répondra 404
    if "GET" in found:
        found.add("HEAD")
    return found | {"OPTIONS"}
```

La méthode `__call__` est celle qui reçoit chaque requête. Elle est écrite en **`async`** (asynchrone), car c'est la forme qu'attend le serveur à ce niveau. Tu n'as pas besoin d'y toucher pour faire évoluer l'API.

## 2. Le choix du code d'erreur — `invalid_request`

Quand Pydantic rejette une requête, FastAPI répond toujours **422** par défaut. On remplace ce comportement pour donner un code plus juste, selon **la partie de la requête** qui est fausse :

```python
async def invalid_request(request: Request, fail: Exception) -> JSONResponse:
    errors = fail.errors()
    if any(e["loc"][0] == "path" for e in errors):           # l'adresse : /api/clusters/abc
        return JSONResponse({"detail": f"{request.url.path} introuvable"}, 404)
    if any(e["type"] == "json_invalid" for e in errors):     # le corps n'est pas du JSON lisible
        return JSONResponse({"detail": "Corps JSON mal formé"}, 400)
    if any(e["loc"][0] == "query" for e in errors):          # un filtre : ?type=INCONNU
        return JSONResponse({"detail": _readable(errors)}, 400)
    return JSONResponse({"detail": _readable(errors)}, 422)   # le contenu du JSON
```

`e["loc"]` indique **où** se trouve l'erreur : `["path", "cluster_id"]`, `["query", "type"]` ou `["body", "code"]`.

| Partie fausse | Code |
| --- | --- |
| l'identifiant dans l'adresse n'est pas un nombre | **404** : cette adresse ne désigne rien |
| le corps n'est pas du JSON lisible | **400** : la demande est illisible |
| un paramètre de filtre est invalide | **400** |
| le JSON est lisible, mais un champ est faux | **422** : la demande est comprise, mais son contenu ne va pas |

Le branchement de cette fonction se fait dans `main.py` : `app.add_exception_handler(RequestValidationError, invalid_request)`.

Page suivante : [les tests](09-tests.md).
