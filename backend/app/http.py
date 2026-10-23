"""Règles HTTP communes à toute l'API.

1. Méthodes (HttpMethods, un « middleware » : il voit passer chaque requête avant les routes)
   - HEAD    : accepté partout où GET l'est ; même réponse que GET (code, en-têtes), sans corps.
   - OPTIONS : 204 avec l'en-tête Allow, qui liste les méthodes possibles sur l'URL.
   - 405     : l'en-tête Allow liste toutes les méthodes possibles sur l'URL (pas seulement une).
   - 415     : le corps envoyé avec POST, PUT ou PATCH doit être du JSON (Content-Type: application/json) ;
               une requête sans corps n'est pas concernée ;
               sauf les chemins qui reçoivent un fichier (import de la configuration : un fichier Excel).

2. Erreurs de requête (invalid_request), au lieu d'un 422 pour tout :
   - 404 : un identifiant de l'URL n'est pas un nombre (/api/modules/abc ne désigne rien) ;
   - 400 : le corps n'est pas du JSON lisible, ou un paramètre de l'URL est invalide (?type=UNKNOWN) ;
   - 422 : le JSON est lisible mais son contenu est invalide (champ manquant, mauvais format…).
"""

import json
import re

from fastapi import Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

# Ordre d'affichage des méthodes dans l'en-tête Allow.
ORDER = ["GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"]
WITH_BODY = {"POST", "PUT", "PATCH"}


class HttpMethods:
    """Middleware : HEAD, OPTIONS, en-tête Allow et contrôle du type de contenu (415).

    routes : liste de (expression du chemin, méthodes acceptées), une par route de l'API.
    fichiers : chemins dont le corps n'est pas du JSON → (type de contenu attendu, sa description).
    """

    def __init__(self, app, routes: list[tuple[re.Pattern, set[str]]], files: dict[str, tuple[str, str]] | None = None):
        self.app = app
        self.routes = routes
        self.files = files or {}

    def methods(self, path: str) -> set[str] | None:
        """Méthodes acceptées sur ce chemin, ou None si le chemin ne correspond à aucune route."""
        found = set()
        for expression, methods in self.routes:
            if expression.match(path):
                found |= methods
        if not found:
            return None
        if "GET" in found:
            found.add("HEAD")
        return found | {"OPTIONS"}

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        methods = self.methods(scope["path"])
        if methods is None:  # chemin inconnu : 404 renvoyé par FastAPI
            return await self.app(scope, receive, send)
        allow = ", ".join(m for m in ORDER if m in methods).encode()
        method = scope["method"]

        if method == "OPTIONS":
            return await respond(send, 204, allow)

        if method in WITH_BODY and method in methods and _has_body(scope):
            rejection = self.content_type_rejection(scope)
            if rejection is not None:
                return await respond(send, 415, allow, {"detail": rejection})

        head = method == "HEAD"
        if head:
            scope = {**scope, "method": "GET"}  # on fait un GET, puis on retire le corps
        await self.app(scope, receive, _fix_response(send, allow, head))

    def content_type_rejection(self, scope) -> str | None:
        """Message du 415 si le corps n'est pas du type attendu (JSON, ou fichier), sinon None."""
        expected, kind = self.files.get(scope["path"], ("application/json", "du JSON"))
        content_type = dict(scope["headers"]).get(b"content-type", b"").split(b";")[0].strip().lower()
        if content_type == expected.encode():
            return None
        return f"Le corps doit être {kind} (Content-Type: {expected})"


def _fix_response(send, allow: bytes, head: bool):
    """Envoi de la réponse des routes, corrigé : Allow complet sur un 405, pas de corps pour HEAD."""

    async def wrapped_send(message):
        if message["type"] == "http.response.start" and message["status"] == 405:
            headers = [(k, v) for k, v in message["headers"] if k.lower() != b"allow"]
            message = {**message, "headers": headers + [(b"allow", allow)]}
        elif message["type"] == "http.response.body" and head:
            message = {**message, "body": b""}
        await send(message)

    return wrapped_send


def _has_body(scope) -> bool:
    """La requête envoie-t-elle un corps (longueur non nulle, ou envoi par morceaux) ?"""
    headers = dict(scope["headers"])
    return headers.get(b"content-length", b"0") != b"0" or b"transfer-encoding" in headers


async def respond(send, code: int, allow: bytes, body: dict | None = None) -> None:
    """Envoie directement une réponse (sans passer par les routes)."""
    content = b"" if body is None else json.dumps(body, ensure_ascii=False).encode()
    headers = [(b"allow", allow)]
    if body is not None:
        headers += [(b"content-type", b"application/json"), (b"content-length", str(len(content)).encode())]
    await send({"type": "http.response.start", "status": code, "headers": headers})
    await send({"type": "http.response.body", "body": content})


def invalid_request(request: Request, error: Exception) -> JSONResponse:
    """Choisit le bon code selon la partie de la requête qui est fausse (voir en tête du fichier).

    Fonction simple (pas « async ») : elle n'attend rien, FastAPI sait appeler les deux.
    """
    assert isinstance(error, RequestValidationError)  # branché uniquement pour ces erreurs (main.py)
    errors = error.errors()
    if any(e["loc"][0] == "path" for e in errors):
        return JSONResponse({"detail": f"{request.url.path} introuvable"}, status.HTTP_404_NOT_FOUND)
    if any(e["type"] == "json_invalid" for e in errors):
        return JSONResponse({"detail": "Corps JSON mal formé"}, status.HTTP_400_BAD_REQUEST)
    if any(e["loc"][0] == "query" for e in errors):
        return JSONResponse({"detail": _readable(errors)}, status.HTTP_400_BAD_REQUEST)
    return JSONResponse({"detail": _readable(errors)}, status.HTTP_422_UNPROCESSABLE_CONTENT)


def _readable(errors) -> list[dict]:
    """Liste des erreurs, réduite à : où (loc), quoi (msg), type."""
    return [{"loc": list(e["loc"]), "msg": e["msg"], "type": e["type"]} for e in errors]
