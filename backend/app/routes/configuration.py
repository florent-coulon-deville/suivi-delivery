"""Route /api/configuration : toute la configuration dans un fichier Excel.

  GET   /api/configuration              200  le fichier .xlsx (app/configuration.py) ; en-tête
                                             Content-Disposition : nom proposé au téléchargement.
                                             Rôle VIEWER : on n'exporte que ce qu'on peut déjà lire.
  PATCH /api/configuration?dry_run=true   200  aperçu de l'import : rapport (ajouts, modifications,
                                             problèmes), rien n'est enregistré
  PATCH /api/configuration              200  import en mode fusion (app/import_configuration.py) : rapport
                                        409  il reste des problèmes : rien n'est importé (rapport joint)
                                        400  fichier illisible | 413 trop gros | 415 pas un fichier Excel
                                        422  pas le fichier de l'export (onglet ou colonnes inconnus, format)
  Import réservé à l'ADMIN. Corps : le fichier lui-même
  (Content-Type: application/vnd.openxmlformats-officedocument.spreadsheetml.sheet).

PATCH, car l'import fusionne : il ajoute et met à jour, sans rien retirer. Un remplacement complet
(PUT, pour restaurer une sauvegarde) est prévu.
"""

from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Request, Response, status
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse

from app.configuration import TYPE_XLSX, excel_file, file_name
from app.import_configuration import InvalidFormat, UnreadableFile, import_workbook
from app.routes import StorageDep
from app.schemas import Error, ImportReport

router = APIRouter(prefix="/configuration", tags=["Configuration"])

MAX_SIZE = 10 * 1024 * 1024  # 10 Mo : bien plus que la configuration d'une grosse équipe


@router.get(
    "",
    response_class=Response,
    responses={200: {"content": {TYPE_XLSX: {}}, "description": "Le fichier Excel de la configuration"}},
    summary="Exporter toute la configuration (Excel)",
    description="Un onglet par objet, objets désignés par leurs codes (et non leurs identifiants) : "
    "le fichier peut être rechargé sur une autre instance.",
)
def export_file(request: Request, storage: StorageDep) -> Response:
    now = datetime.now(UTC)
    content = excel_file(storage, request.app.version, now)
    headers = {"Content-Disposition": f'attachment; filename="{file_name(now)}"'}
    return Response(content, media_type=TYPE_XLSX, headers=headers)


@router.patch(
    "",
    response_model=ImportReport,
    responses={
        400: {"model": Error, "description": "Fichier illisible"},
        409: {"description": "Il reste des problèmes : rien n'est importé ({detail, rapport})"},
        413: {"model": Error, "description": "Fichier trop gros"},
        422: {"model": Error, "description": "Pas le fichier de l'export"},
    },
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {TYPE_XLSX: {"schema": {"type": "string", "format": "binary"}}},
        }
    },
    summary="Importer une configuration (Excel, fusion)",
    description="Relit le fichier de l'export : ajoute ce qui manque, met à jour ce qui a changé, ne retire "
    "rien. Tout ou rien : s'il reste un problème, rien n'est importé. `dry_run=true` : aperçu, rien "
    "n'est enregistré. Réservé à l'ADMIN.",
)
async def import_file(request: Request, storage: StorageDep, dry_run: bool = False):
    # Route « async » : elle lit le corps brut (le fichier). Le travail sur le stockage, lui, attend
    # la base : il tourne dans un autre fil d'exécution (run_in_threadpool), comme les autres routes.
    content = await request.body()
    if len(content) > MAX_SIZE:
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, "Fichier trop gros (10 Mo au plus)")
    try:
        report = await run_in_threadpool(import_workbook, storage, content, dry_run)
    except UnreadableFile as error:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(error)) from error
    except InvalidFormat as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(error)) from error
    if report.problems and not dry_run:
        detail = f"Import refusé : {len(report.problems)} problème(s), rien n'a été importé"
        return JSONResponse({"detail": detail, "report": report.model_dump(mode="json")}, status.HTTP_409_CONFLICT)
    return report
