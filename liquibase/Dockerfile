# Image « suivi-delivery-liquibase-local » : applique les changements de structure de la base.
#
# Liquibase (Docker Hardened Image, dhi.io : connexion requise, `docker login dhi.io`), qui
# embarque déjà le connecteur PostgreSQL (pgjdbc), + nos fichiers de changements (changelog/).
# Guide : docs/postgresql.md. Tout se fait ici : `docker build` suffit (pas d'étape à faire avant).
#
# Fabrication, depuis la racine du projet :
#   docker build -t suivi-delivery-liquibase-local liquibase
# Lancement, depuis la racine du projet (applique ce qui manque, puis s'arrête ; adresse de la
# base, utilisateur et mot de passe : LIQUIBASE_COMMAND_* de docker.env) :
#   docker run --rm --network suivi-delivery-local --env-file deployment/docker.env suivi-delivery-liquibase-local
# Autre commande : ajouter son nom à la fin (status, history, validate, update-sql…).

# Liquibase 4.33.0 (la DHI n'existe pas en 5.x), connecteur PostgreSQL 42.7.12 inclus.
FROM dhi.io/liquibase:4.33.0-debian13

# Nos fichiers de changements, lisibles par tous : Liquibase ne fait que les lire (OpenShift le
# lance avec un utilisateur au hasard, du groupe 0, qui n'a besoin d'aucun autre droit).
COPY --chmod=0755 changelog /liquibase/changelog

# Réglages par défaut (les variables LIQUIBASE_* remplacent les options de la ligne de commande) :
#   LIQUIBASE_SEARCH_PATH             le dossier où chercher nos fichiers de changements ;
#   LIQUIBASE_COMMAND_CHANGELOG_FILE  le fichier principal, qui liste les autres ;
#   LIQUIBASE_ANALYTICS_ENABLED       pas d'envoi de statistiques d'utilisation à l'éditeur ;
#   LIQUIBASE_SHOW_BANNER             pas de bannière publicitaire dans les journaux.
# L'adresse de la base, l'utilisateur et le mot de passe sont donnés au lancement
# (docker.env sur le poste, Secret sur un cluster) :
#   LIQUIBASE_COMMAND_URL, LIQUIBASE_COMMAND_USERNAME, LIQUIBASE_COMMAND_PASSWORD.
ENV LIQUIBASE_SEARCH_PATH=/liquibase/changelog \
    LIQUIBASE_COMMAND_CHANGELOG_FILE=main.yaml \
    LIQUIBASE_ANALYTICS_ENABLED=false \
    LIQUIBASE_SHOW_BANNER=false

# Utilisateur « liquibase » de l'image durcie, par son numéro : Kubernetes ne peut vérifier
# qu'un numéro n'est pas root (OpenShift, lui, le remplace par un utilisateur au hasard, du groupe 0).
USER 1001
# Par défaut : « update », appliquer les changements qui manquent.
CMD ["update"]
