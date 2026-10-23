# Image « suivi-delivery-keycloak-local » : Keycloak, qui gère les comptes et la connexion
# (page de connexion, jetons). Guide : docs/keycloak.md.
#
# Keycloak (Docker Hardened Image, dhi.io : connexion requise, `docker login dhi.io`) + notre thème (pages de connexion à
# l'allure de l'outil) + la configuration du domaine « suivi-delivery » (rôles, clients, compte
# admin), importée au premier démarrage.
#
# Fabrication, depuis la racine du projet :
#   docker build -t suivi-delivery-keycloak-local keycloak
# Réglages au lancement (deployment/docker.env sur le poste, Secret sur un cluster) : KC_DB_*,
# KC_HOSTNAME, KC_BOOTSTRAP_ADMIN_*, et les valeurs reprises dans l'import (APP_FRONTEND_URL,
# APP_API_URL, APP_ADMIN_PASSWORD, APP_KEYCLOAK_CLIENT_SECRET).

# ---------- Étape 1 : préparer Keycloak (« build ») ----------
# Keycloak se prépare une fois pour toutes avec ses options de fabrication (base PostgreSQL,
# adresse sous /auth, sondes de santé) : il démarre ensuite plus vite (« start --optimized »).
# Keycloak 26.7.4, version figée (la même pour les deux étapes).
FROM dhi.io/keycloak:26.7.4-debian13 AS build
ENV KC_DB=postgres \
    KC_HTTP_RELATIVE_PATH=/auth \
    KC_HEALTH_ENABLED=true \
    KC_METRICS_ENABLED=false
COPY themes/ /opt/keycloak/themes/
RUN /opt/keycloak/bin/kc.sh build

# ---------- Étape 2 : l'image finale ----------
FROM dhi.io/keycloak:26.7.4-debian13
COPY --from=build /opt/keycloak/ /opt/keycloak/
# La configuration du domaine, importée au PREMIER démarrage seulement (--import-realm : un
# domaine qui existe déjà n'est pas touché). Les ${…} y sont remplacés par les variables
# d'environnement du même nom.
COPY import/ /opt/keycloak/data/import/
# Démarrage : Keycloak, puis l'adresse de sa console d'administration (KC_HOSTNAME_ADMIN, voir
# start.sh).
COPY --chmod=0755 start.sh /opt/keycloak/bin/start.sh

# Réglages communs à toutes les instances. Les autres sont donnés au lancement.
#   KC_HTTP_ENABLED                  HTTP simple : le chiffrement (HTTPS) est fait devant
#                                    (Route OpenShift, ou rien sur le poste) ;
#   KC_HOSTNAME_BACKCHANNEL_DYNAMIC  l'API et l'interface parlent à Keycloak par son adresse
#                                    interne (http://…:8080/auth), les navigateurs par l'adresse
#                                    publique (KC_HOSTNAME, sous celle de l'interface) ;
#   KC_DB_SCHEMA                     ses tables dans le schéma « keycloak » de notre base.
ENV KC_HTTP_ENABLED=true \
    KC_HOSTNAME_BACKCHANNEL_DYNAMIC=true \
    KC_DB_SCHEMA=keycloak \
    KC_LOG_CONSOLE_COLOR=false

# Keycloak écrit ses fichiers de travail dans /opt/keycloak/data/tmp (dont les pages de la console
# compressées : sans ce droit, la console reste blanche). Dans l'image durcie, ce dossier n'est
# modifiable que par son utilisateur « nonroot » : on le donne aussi au groupe 0, celui des
# utilisateurs au hasard d'OpenShift et de l'utilisateur 1000 ci-dessous. Seule étape faite en
# administrateur (0 : l'image durcie n'a pas d'utilisateur nommé root).
USER 0
RUN chgrp -R 0 /opt/keycloak/data && chmod -R g=u,g+w /opt/keycloak/data

# Utilisateur 1000, par son numéro, du groupe 0 (OpenShift le remplace par un utilisateur au
# hasard, du groupe 0 lui aussi).
USER 1000:0
EXPOSE 8080 9000
ENTRYPOINT ["/opt/keycloak/bin/start.sh"]
CMD ["start", "--optimized", "--import-realm"]
