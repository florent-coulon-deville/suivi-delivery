"""Routes de santé, pour Kubernetes / OpenShift (probes).

Kubernetes appelle régulièrement ces adresses pour savoir où en est l'API. Elles sont
hors de /api (le frontend ne les relaie donc pas vers l'extérieur), ne demandent aucun
jeton et ne montrent aucune donnée.

  GET /startupz   200 | 503  « As-tu fini de démarrer ? »  (connectée à la base)
  GET /readyz     200 | 503  « Peux-tu recevoir des appels ? »  (démarrée, et la base répond)
  GET /livez      200        « Es-tu encore en vie ? »  (répondre suffit)

La liveness ne vérifie volontairement rien d'autre : un souci passager de la base ne doit
pas faire redémarrer le pod en boucle, seulement le retirer du trafic (readiness).
Réglage des probes dans le chart Helm : voir docs/deploiement.md.
"""

import logging

from fastapi import APIRouter, Request, status
from fastapi.responses import JSONResponse

from app.routes import Responses
from app.storage import StorageUnavailable

router = APIRouter(tags=["Santé"])
logger = logging.getLogger(__name__)

UNAVAILABLE: Responses = {503: {"description": "Pas prête (le détail dit pourquoi)"}}


def _ok() -> JSONResponse:
    return JSONResponse({"status": "ok"})


def _unavailable(detail: str) -> JSONResponse:
    return JSONResponse({"status": "unavailable", "detail": detail}, status.HTTP_503_SERVICE_UNAVAILABLE)


@router.get("/startupz", responses=UNAVAILABLE, summary="Probe de démarrage")
def startup(request: Request):
    if not request.app.state.started:
        return _unavailable("Démarrage en cours")
    return _ok()


@router.get("/readyz", responses=UNAVAILABLE, summary="Probe de disponibilité")
def readiness(request: Request):
    if not request.app.state.started:
        return _unavailable("Démarrage en cours")
    try:
        request.app.state.storage.check()
    except StorageUnavailable as error:
        logger.warning("Base de données inaccessible : %s", error)
        return _unavailable("Base de données inaccessible")
    return _ok()


@router.get("/livez", summary="Probe de vie")
def liveness():
    return _ok()
