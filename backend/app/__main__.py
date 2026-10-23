"""Lancement de l'API avec les réglages de l'environnement (voir app/settings.py).

Depuis backend/ :
    uv run python -m app            lancement normal (serveur, conteneur)
    uv run python -m app --reload   développement : redémarre à chaque modification du code

Le serveur (uvicorn) écoute sur APP_HOST:APP_PORT, avec le niveau de journaux APP_LOG_LEVEL.

Un seul processus (workers=1), et un seul exemplaire de l'API à la fois : la base SQLite est
un fichier, lu et écrit par ce seul processus, une requête à la fois (app/storage_sqlite.py).
"""

import sys

import uvicorn

from app.settings import InvalidSetting, read_settings


def main() -> None:
    try:
        settings = read_settings()
    except InvalidSetting as error:
        sys.exit(f"Réglage invalide : {error}")

    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        log_level=settings.log_level,
        reload="--reload" in sys.argv[1:],
        workers=1,
        # Derrière un relais (Route OpenShift) : garder l'adresse et le protocole d'origine.
        proxy_headers=True,
        forwarded_allow_ips="*",
    )


if __name__ == "__main__":
    main()
