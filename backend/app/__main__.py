"""Lancement de l'API avec les réglages de l'environnement (voir app/settings.py).

Depuis backend/ :
    uv run python -m app            lancement normal (serveur, conteneur)
    uv run python -m app --reload   développement : redémarre à chaque modification du code

Le serveur (uvicorn) écoute sur APP_HOST:APP_PORT, avec le niveau de journaux APP_LOG_LEVEL.

Un seul processus par conteneur (workers=1). Avec la base PostgreSQL, on peut lancer
plusieurs conteneurs (exemplaires) de l'API : ils partagent les mêmes données, et une seule
écriture passe à la fois (app/storage_postgres.py). Sans base (données en mémoire),
un seul exemplaire : deux exemplaires ne se verraient pas l'un l'autre.
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
        # Derrière le relais du frontend (nginx) : garder l'adresse et le protocole d'origine.
        proxy_headers=True,
        forwarded_allow_ips="*",
    )


if __name__ == "__main__":
    main()
