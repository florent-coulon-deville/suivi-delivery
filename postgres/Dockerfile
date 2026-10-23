# Image « suivi-delivery-postgres-local » : PostgreSQL (Docker Hardened Image, dhi.io : connexion
# requise, `docker login dhi.io`), sous le nom du projet (comme suivi-delivery-backend-local,
# -frontend, -liquibase, -keycloak), avec la préparation de la base au premier démarrage
# (initialization/01-schemas.sh : le schéma de nos tables, et l'utilisateur et le schéma de
# Keycloak). Les tables elles-mêmes sont créées par Liquibase (module liquibase/) et par Keycloak.
#
# L'image durcie ne lance pas les scripts de préparation et ne sait pas tourner avec un
# utilisateur au hasard (OpenShift) : notre point d'entrée start.sh s'en charge.
#
# Fabrication, depuis la racine du projet :
#   docker build -t suivi-delivery-postgres-local postgres
# Réglages (nom de la base, utilisateurs, mots de passe) : POSTGRES_*, APP_DB_SCHEMA et KC_DB_* de
# deployment/docker.env.

# PostgreSQL 18.6 sur Alpine 3.24, version figée. Données dans /var/lib/postgresql/18/data (PGDATA).
FROM dhi.io/postgres:18.6-alpine3.24

# Lancés par start.sh au premier démarrage seulement (dossier des données vide).
# Lisibles par tous : OpenShift lance le conteneur avec un utilisateur au hasard (groupe 0).
COPY --chmod=0755 initialization/ /docker-entrypoint-initdb.d/
COPY --chmod=0755 start.sh /usr/local/bin/start.sh

# La liste des utilisateurs du système (/etc/passwd) renvoie vers /tmp/passwd : start.sh peut ainsi
# y ajouter l'utilisateur au hasard d'OpenShift, même quand le reste du système est en lecture
# seule (chart Helm). /tmp/passwd est livré déjà rempli (la liste de l'image), modifiable par le
# groupe 0 : sans lui, le lien pointerait dans le vide, et Podman créerait le fichier lui-même, en
# root, que start.sh ne pourrait plus modifier. Seule étape faite en administrateur (0 : l'image
# durcie n'a pas d'utilisateur nommé root).
USER 0
RUN mv /etc/passwd /etc/passwd.image && cp /etc/passwd.image /tmp/passwd \
    && chgrp 0 /tmp/passwd && chmod 0664 /tmp/passwd && ln -s /tmp/passwd /etc/passwd \
    && chgrp 0 /run/postgresql && chmod 0775 /run/postgresql
# (/run/postgresql, où PostgreSQL ouvre sa prise locale, est lui aussi donné au groupe 0 : un
# utilisateur au hasard doit pouvoir y écrire quand aucun dossier n'y est monté.)

# Jamais en administrateur à l'exécution : l'utilisateur « postgres » de l'image durcie (70), à qui
# appartiennent déjà les dossiers des données (/var/lib/postgresql/18/data) et d'exécution.
USER 70
ENTRYPOINT ["/usr/local/bin/start.sh"]
