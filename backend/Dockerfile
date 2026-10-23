# Image de l'API. Tout se fait ici : `docker build` suffit (pas d'étape à faire avant).
#
# Images de base : Docker Hardened Images (dhi.io, connexion requise : `docker login dhi.io`),
# réduites au strict nécessaire, presque sans faille connue. Voir docs/deploiement.md.
#
# Deux étapes :
#   1. « build »  : récupère les dépendances Python, aux versions exactes de uv.lock (empreintes
#                   vérifiées), avec uv (l'outil d'Astral), dans un environnement à part (.venv) ;
#                   image « -dev » : elle a un shell, l'image finale n'en a pas ;
#   2. l'image finale : Python, cet environnement et le code. Ni uv ni shell : rien ne pourra
#                   être installé ou lancé d'autre dans le conteneur.
#
# Fabrication, depuis backend/ :
#   docker build -t suivi-delivery-backend-local .

# ---------- Étape 1 : les dépendances ----------
FROM dhi.io/python:3.14.8-debian13-dev AS build

# uv (version figée, la même que la CI), recopié de son image durcie, le temps de cette étape.
COPY --from=dhi.io/uv:0.13.4-debian13 /usr/local/bin/uv /usr/local/bin/uv

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
# droits à ce groupe. Fait ici, car l'image finale n'a pas de shell pour le faire (les droits
# sont gardés par la copie).
RUN chgrp -R 0 /app && chmod -R g=u /app

# ---------- Étape 2 : exécution ----------
# Même Python que l'étape 1 (/usr/bin/python3.14) : l'environnement .venv y fonctionne tel quel.
# L'image durcie contient le pip de Debian : sans shell, on ne peut pas l'en retirer ; .venv,
# lui, n'en a pas.
FROM dhi.io/python:3.14.8-debian13

WORKDIR /app
COPY --from=build /app /app

# Réglages par défaut dans un conteneur (modifiables au lancement, voir docs/deploiement.md).
# Les données sont dans la base PostgreSQL (APP_DB_*, donnés au lancement) : rien n'est écrit
# dans le conteneur.
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    APP_HOST=0.0.0.0 \
    APP_PORT=8000

USER 1001
EXPOSE 8000
CMD ["python", "-m", "app"]
