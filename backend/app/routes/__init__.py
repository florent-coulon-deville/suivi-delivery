"""Routes de l'API (une ressource par fichier) et vérifications communes.

StorageDep : à mettre en paramètre d'une route pour recevoir le stockage de
l'application. FastAPI le fournit automatiquement (c'est une « dépendance »).

Les vérifications ci-dessous lèvent une HTTPException : FastAPI arrête alors la
route et renvoie le code d'erreur avec le message, sous la forme {"detail": "..."}.
"""

from typing import Annotated, Any

from fastapi import Depends, HTTPException, Request, Response, status

from app.schemas import Error
from app.storage import Storage, Table


def _storage(request: Request) -> Storage:
    return request.app.state.storage


StorageDep = Annotated[Storage, Depends(_storage)]

# Erreurs affichées dans Swagger.
type Responses = dict[int | str, dict[str, Any]]
R404: Responses = {404: {"model": Error, "description": "Introuvable"}}
R409: Responses = {409: {"model": Error, "description": "Conflit : valeur déjà utilisée, ou élément encore utilisé"}}
R422: Responses = {422: {"description": "Données invalides, ou référence vers un élément inexistant"}}

# Description commune des routes PUT.
REPLACEMENT = (
    "Remplace **entièrement** l'élément : tous les champs obligatoires sont à fournir (422 sinon), "
    "et un champ facultatif absent reprend sa valeur par défaut. Rejouer la même requête donne le même "
    "résultat (idempotent). L'identifiant étant attribué par l'outil, PUT ne crée pas : 404 si l'élément "
    "n'existe pas (utiliser POST)."
)


def read_or_404(table: Table, id_: int, object: str) -> dict:
    """La ligne demandée dans l'URL, sinon 404. Ex. : « Application 9 introuvable »."""
    row = table.read(id_)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"{object} {id_} introuvable")
    return row


def check_reference(table: Table, id_: int, object: str) -> None:
    """Un identifiant envoyé dans le corps (ex. application_id) doit exister, sinon 422."""
    if table.read(id_) is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"{object} {id_} introuvable")


def check_unique(table: Table, message: str, excluding_id: int | None = None, **criteria) -> None:
    """Aucune autre ligne (que excluding_id) ne doit avoir ces valeurs, sinon 409."""
    existing_installation = table.find(**criteria)
    if existing_installation is not None and existing_installation["id"] != excluding_id:
        raise HTTPException(status.HTTP_409_CONFLICT, message)


def check_unused(table: Table, message: str, **criteria) -> None:
    """Avant une suppression : aucune ligne de cette table ne doit y faire référence, sinon 409."""
    if table.find(**criteria) is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, message)


def add_location(request: Request, response: Response, id_: int | str) -> None:
    """En-tête Location d'une création : l'adresse du nouvel élément."""
    response.headers["Location"] = f"{request.url.path}/{id_}"
