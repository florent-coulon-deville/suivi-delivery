# Image de l'API. Tout se fait ici : `docker build` suffit (pas d'étape à faire avant).
#
# Images de base : celles des éditeurs, sur Docker Hub (aucune connexion requise) : Python, image
# officielle « slim » (Debian 13, trixie), et uv, image d'Astral. Voir docs/deploiement.md.
#
# Deux étapes :
#   1. « build »  : récupère les dépendances Python, aux versions exactes de uv.lock (empreintes
#                   vérifiées), avec uv (l'outil d'Astral), dans un environnement à part (.venv) ;
#   2. l'image finale : Python, cet environnement et le code. Pas d'uv : il ne sert qu'à la
#                   fabrication.
#
# Fabrication, depuis backend/ :
#   docker build -t suivi-delivery-backend-local .

# ---------- Étape 1 : les dépendances ----------
FROM docker.io/library/python:3.14.8-slim-trixie AS build

# uv (version figée, la même que la CI), recopié de l'image d'Astral, le temps de cette étape.
COPY --from=docker.io/astral/uv:0.13.4 /uv /usr/local/bin/uv

WORKDIR /app
# D'abord les seules listes de dépendances : cette étape reste en cache tant qu'elles ne changent pas.
COPY pyproject.toml uv.lock ./

#   uv export      la liste exacte des dépendances de uv.lock (sans celles du développement), avec
#                  leurs empreintes ;
#   uv pip install les installe dans .venv (sans pip), en vérifiant chaque empreinte :
#                  --no-deps     exactement cette liste ;
#                  --no-build    uniquement des paquets déjà construits : aucun script exécuté.
RUN set -eu; \
    uv export --frozen --no-dev --no-emit-project --format requirements-txt -o /tmp/requirements.txt; \
    python -m venv --without-pip /app/.venv; \
    uv pip install --python /app/.venv/bin/python --no-cache --no-deps --no-build \
      --require-hashes --requirement /tmp/requirements.txt; \
    rm -f /tmp/requirements.txt uv.lock

# Puis le code, et pyproject.toml (l'API y lit son numéro de version).
COPY app ./app

# OpenShift lance le conteneur avec un utilisateur au hasard, du groupe 0 : on donne les
# droits à ce groupe (gardés par la copie vers l'image finale).
RUN chgrp -R 0 /app && chmod -R g=u /app

# ---------- Étape 2 : exécution ----------
# Même image que l'étape 1 (/usr/local/bin/python3.14) : l'environnement .venv y fonctionne tel
# quel. L'image officielle contient pip pour son Python ; .venv, lui, n'en a pas.
FROM docker.io/library/python:3.14.8-slim-trixie

WORKDIR /app
COPY --from=build /app /app

# /data : le dossier de la base SQLite (APP_DB_FILE), où l'API écrit ; un volume y est monté pour
# garder les données (docker-deploy.zsh, chart Helm). Créé ici, dans l'image finale : une copie
# depuis l'étape 1 ne garderait pas ses droits. À l'utilisateur 1001 (hors OpenShift) et au
# groupe 0 (utilisateur au hasard d'OpenShift).
RUN mkdir /data && chown 1001:0 /data && chmod 770 /data

# Réglages par défaut dans un conteneur (modifiables au lancement, voir docs/deploiement.md).
# Les données sont dans le fichier SQLite APP_DB_FILE, sous /data : y monter un volume, sinon
# elles sont perdues avec le conteneur.
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    APP_HOST=0.0.0.0 \
    APP_PORT=8000 \
    APP_DB_FILE=/data/suivi-delivery.sqlite

USER 1001
EXPOSE 8000
CMD ["python", "-m", "app"]
