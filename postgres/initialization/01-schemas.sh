#!/usr/bin/env bash
# Préparation de la base, au PREMIER démarrage seulement (volume des données vide) : l'image
# officielle de PostgreSQL lance alors chaque fichier de /docker-entrypoint-initdb.d, une fois
# la base POSTGRES_DB et son utilisateur POSTGRES_USER créés.
#
# Une seule base, deux schémas (deux « dossiers » de tables, séparés) :
#   suivi_delivery  nos tables, créées ensuite par Liquibase (module liquibase/) ; propriétaire :
#                   POSTGRES_USER (l'utilisateur de Liquibase et de l'API) ;
#   keycloak        les tables de Keycloak, qu'il crée lui-même au démarrage ; propriétaire : son
#                   propre utilisateur (KC_DB_USERNAME), qui n'a accès qu'à ce schéma.
# Le schéma « public » reste vide.
#
# Réglages lus (deployment/docker.env sur le poste, Secret sur un cluster) :
#   APP_DB_SCHEMA    nom du schéma de nos tables          défaut : suivi_delivery
#   KC_DB_USERNAME   utilisateur de Keycloak              absent : pas d'utilisateur ni de schéma Keycloak
#   KC_DB_PASSWORD   son mot de passe (obligatoire avec KC_DB_USERNAME)
#   KC_DB_SCHEMA     schéma de Keycloak                   défaut : keycloak
#
# Les noms et le mot de passe sont passés à psql comme variables (:"nom" pour un nom, :'texte'
# pour une valeur) : psql les protège lui-même, rien n'est recollé à la main dans le SQL.
set -euo pipefail

app_schema="${APP_DB_SCHEMA:-suivi_delivery}"
psql=(psql -v ON_ERROR_STOP=1 --no-psqlrc --username "$POSTGRES_USER" --dbname "$POSTGRES_DB")

echo "Préparation de la base : schéma « $app_schema » pour $POSTGRES_USER"
"${psql[@]}" -v schema="$app_schema" -v owner="$POSTGRES_USER" <<'SQL'
create schema :"schema" authorization :"owner";
SQL

if [[ -n "${KC_DB_USERNAME:-}" ]]; then
    if [[ -z "${KC_DB_PASSWORD:-}" ]]; then
        echo "KC_DB_USERNAME sans KC_DB_PASSWORD : donner un mot de passe à l'utilisateur de Keycloak" >&2
        exit 1
    fi
    keycloak_schema="${KC_DB_SCHEMA:-keycloak}"
    echo "Préparation de la base : utilisateur $KC_DB_USERNAME et schéma « $keycloak_schema » pour Keycloak"
    "${psql[@]}" -v db_user="$KC_DB_USERNAME" -v password="$KC_DB_PASSWORD" \
        -v schema="$keycloak_schema" <<'SQL'
create role :"db_user" login password :'password';
create schema :"schema" authorization :"db_user";
-- Ses tables, et rien d'autre : ses requêtes cherchent d'abord dans son schéma.
alter role :"db_user" set search_path = :"schema";
SQL
fi
