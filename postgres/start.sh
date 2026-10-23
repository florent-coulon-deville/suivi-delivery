#!/usr/bin/env bash
# Point d'entrée de l'image « suivi-delivery-postgres » (voir le Dockerfile).
#
# L'image durcie de PostgreSQL (dhi.io) sait créer la base et son utilisateur, mais ne lance pas
# les scripts de préparation (/docker-entrypoint-initdb.d) et ne sait pas tourner avec un
# utilisateur au hasard (OpenShift). Ce script fait les deux, puis passe la main au point d'entrée
# de l'image, qui démarre PostgreSQL :
#   1. à chaque démarrage : déclare l'utilisateur du conteneur au système (PostgreSQL l'exige) ;
#   2. au premier démarrage seulement (dossier des données vide) : crée la base et son utilisateur
#      (POSTGRES_DB, POSTGRES_USER, POSTGRES_PASSWORD), puis lance nos scripts de préparation
#      (initialization/01-schemas.sh : schéma de nos tables, utilisateur et schéma de Keycloak).
set -Eeuo pipefail

# ---------- 1. L'utilisateur du conteneur ----------
# /etc/passwd (la liste des utilisateurs du système) renvoie vers /tmp/passwd, préparé à la
# fabrication : le reste du système est en lecture seule sur un cluster. On y recopie la liste de
# l'image, plus l'utilisateur du conteneur s'il n'y est pas (utilisateur au hasard d'OpenShift).
cp /etc/passwd.image /tmp/passwd
if ! whoami >/dev/null 2>&1; then
    echo "postgres-$(id -u):x:$(id -u):$(id -g):PostgreSQL:/var/lib/postgresql:/sbin/nologin" >> /tmp/passwd
fi

# ---------- 2. Premier démarrage ----------
if [[ ! -s "$PGDATA/PG_VERSION" ]]; then
    : "${POSTGRES_PASSWORD:?POSTGRES_PASSWORD est obligatoire au premier démarrage (mot de passe de la base)}"
    export POSTGRES_USER="${POSTGRES_USER:-postgres}"
    export POSTGRES_DB="${POSTGRES_DB:-$POSTGRES_USER}"

    echo "Premier démarrage : création de la base « $POSTGRES_DB » (utilisateur $POSTGRES_USER)"
    mkdir -p "$PGDATA"
    chmod 0700 "$PGDATA"
    # Mot de passe exigé pour toute connexion par le réseau ; sans mot de passe seulement depuis
    # le conteneur lui-même (comme l'image officielle).
    initdb --username="$POSTGRES_USER" --pwfile=<(printf '%s\n' "$POSTGRES_PASSWORD") \
        --auth-local=trust --auth-host=scram-sha-256 >/dev/null
    printf '\nhost all all all scram-sha-256\n' >> "$PGDATA/pg_hba.conf"

    # Serveur provisoire, sans réseau (listen_addresses vide) : personne ne s'y connecte avant
    # la fin de la préparation.
    pg_ctl -D "$PGDATA" -o "-c listen_addresses=''" -w start >/dev/null
    if [[ "$POSTGRES_DB" != postgres ]]; then
        createdb --username="$POSTGRES_USER" "$POSTGRES_DB"
    fi
    for script in /docker-entrypoint-initdb.d/*.sh; do
        [[ -e "$script" ]] || continue
        echo "Préparation : $(basename "$script")"
        bash "$script"
    done
    pg_ctl -D "$PGDATA" -m fast -w stop >/dev/null
    echo "Premier démarrage : base prête"
fi

# Le point d'entrée de l'image trouve la base prête : il démarre PostgreSQL.
exec docker-entrypoint.sh "$@"
