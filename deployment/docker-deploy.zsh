#!/bin/zsh
# Fabrique les images (Docker ou Podman) et (re)lance les conteneurs sur le poste : tout, ou un module.
# Voir docs/deploiement.md, section 7, et docs/postgresql.md.
#
# Usage, depuis n'importe quel dossier :
#   ./deployment/docker-deploy.zsh                     tout, dans l'ordre : postgres, liquibase, keycloak,
#                                                         backend, frontend ; données CONSERVÉES
#   ./deployment/docker-deploy.zsh postgres            la base seule (par exemple pour l'API lancée avec « uv run »)
#   ./deployment/docker-deploy.zsh liquibase           la structure de la base seule (après un nouveau changement)
#   ./deployment/docker-deploy.zsh keycloak            Keycloak seul (comptes et connexion)
#   ./deployment/docker-deploy.zsh backend             l'API seule
#   ./deployment/docker-deploy.zsh frontend            l'interface seule
#   ./deployment/docker-deploy.zsh --reset             tout, en EFFAÇANT les données (repartir de zéro)
#   ./deployment/docker-deploy.zsh postgres --reset    la base seule, en effaçant les données
#   ./deployment/docker-deploy.zsh --podman …          la même chose avec Podman au lieu de Docker
#                                                         (raccourci : ./deployment/podman-deploy.zsh …)
#
# Docker ou Podman : les commandes sont les mêmes ; seul le programme appelé change. Les deux
# utilisent les mêmes noms de conteneurs, les mêmes ports et le même docker.env, mais chacun a
# ses propres images, son réseau et son volume (donc sa propre base) : ne pas les faire tourner
# en même temps (le script s'arrête si un port est déjà pris par l'autre).
#
# Les modules :
#   postgres   la base (image durcie, sous le nom du projet) ; ses données dans un volume, conservées d'un lancement
#              à l'autre.
#   liquibase  applique les changements de structure qui manquent, puis s'arrête.
#   keycloak   les comptes et la connexion (pages à l'allure de l'outil, servies par l'interface
#              sous /auth). Ses données sont dans la même base (schéma « keycloak ») ; au premier
#              démarrage, il importe le domaine de l'outil, avec le compte « admin ».
#   backend    l'API.
#   frontend   l'interface.
# liquibase, keycloak et backend ont besoin de la base : lancée par un passage précédent, elle est
# redémarrée si besoin ; sinon le script demande de lancer d'abord « postgres ».
#
# Réglages : UN seul fichier, deployment/docker.env (non suivi par Git), reçu par chaque
# conteneur. S'il n'existe pas, le script le crée en mettant bout à bout les modèles de chaque
# module (<module>/docker.example.env), précédés de celui du script (deployment/docker.example.env :
# DHI_USERNAME, DHI_TOKEN, la connexion à dhi.io, d'où viennent les images de base ; remplis, le
# script se connecte avant de fabriquer ; ces lignes ne sont jamais transmises aux conteneurs). Chaque conteneur y trouve tous ses réglages (pas de
# « -e »). La base y figure pour PostgreSQL (POSTGRES_*), Liquibase (LIQUIBASE_COMMAND_*),
# Keycloak (KC_DB_*) et l'API (APP_DB_*) : le script vérifie qu'ils désignent la même base, et
# que Keycloak est bien servi sous l'adresse de l'interface ; il s'arrête sinon.
#
# Le script s'arrête à la première erreur, avec un message. Une image qui ne se fabrique
# pas laisse les conteneurs en place : on ne supprime l'ancien que si le nouveau est prêt.

setopt errexit nounset pipefail

# --- Noms, images et ports (ports du poste : jamais le même pour deux services) ---
NETWORK=suivi-delivery-local
POSTGRES=suivi-delivery-postgres-local
LIQUIBASE=suivi-delivery-liquibase-local
KEYCLOAK=suivi-delivery-keycloak-local
BACKEND=suivi-delivery-backend-local
FRONTEND=suivi-delivery-frontend-local
VOLUME=suivi-delivery-postgres-local            # données de PostgreSQL
PORT_POSTGRES=5432   # développement seulement, et sur ce poste seulement (127.0.0.1)
PORT_KEYCLOAK=8081   # développement seulement, ce poste seulement : console d'administration de Keycloak
PORT_BACKEND=8000    # développement seulement : backend testable en direct
PORT_FRONTEND=8080

# Le fichier des réglages, et les modèles qui servent à le créer (dans cet ordre).
SETTINGS=deployment/docker.env
TEMPLATES=(deployment/docker.example.env postgres/docker.example.env liquibase/docker.example.env
         keycloak/docker.example.env backend/docker.example.env frontend/docker.example.env)
# Réglages du script lui-même (connexion à dhi.io) : retirés de la copie de docker.env donnée aux
# conteneurs, pour qu'aucun jeton n'entre dans un conteneur.
SCRIPT_SETTINGS=(DHI_USERNAME DHI_TOKEN)
# Réglages de Keycloak, obligatoires dans docker.env : un fichier qui ne les a pas est refusé.
KEYCLOAK_SETTINGS=(KC_DB_URL KC_DB_USERNAME KC_DB_PASSWORD KC_HOSTNAME APP_ADMIN_PASSWORD APP_KEYCLOAK_CLIENT_SECRET
                   APP_KEYCLOAK_URL KEYCLOAK_URL)

# --- Outils d'affichage --------------------------------------------------------
step()  { print -P "\n%F{blue}==> $1%f"; }
ok()     { print -P "%F{green}✔ $1%f"; }
info()   { print -P "%F{yellow}! $1%f"; }
fail() { print -P "%F{red}✘ $1%f" >&2; exit 1; }

usage="Usage : ./deployment/docker-deploy.zsh [postgres|liquibase|keycloak|backend|frontend] [--reset] [--podman]"

# --- Options -------------------------------------------------------------------
TARGET=""
RESET=false
KEYCLOAK_IMPORTED=false   # Keycloak vient d'importer le domaine de l'outil (compte admin créé)
ENGINE=docker         # le programme qui fabrique et lance les conteneurs : docker, ou podman (--podman)
COMMAND=./deployment/docker-deploy.zsh   # pour les conseils affichés (« lancer : … »)
for option in "$@"; do
  case $option in
    postgres|liquibase|keycloak|backend|frontend)
      [[ -z $TARGET ]] || fail "Un seul module à la fois (sans rien : tout). $usage"
      TARGET=$option ;;
    --reset)   RESET=true ;;
    --podman)  ENGINE=podman; COMMAND=./deployment/podman-deploy.zsh ;;
    -h| --help) print $usage; exit 0 ;;
    *)         fail "Option inconnue : $option. $usage" ;;
  esac
done
selected() {  # selected <module> : ce module est-il à lancer ?
  [[ -z $TARGET || $TARGET == $1 ]]
}
selected postgres || [[ $RESET == false ]] || fail "--reset efface les données de la base : il ne s'utilise qu'avec postgres (ou sans module)."
# Les réglages de la base servent à postgres, à liquibase, à keycloak et au backend.
NEEDS_DATABASE=false
for module in postgres liquibase keycloak backend; do
  if selected $module; then NEEDS_DATABASE=true; fi
done

# --- Fonctions --------------------------------------------------------------------

exists() {  # exists <container|network|volume> <nom>
  $ENGINE $1 inspect $2 >/dev/null 2>&1
}

setting() {  # setting <VARIABLE> : sa valeur dans docker.env (vide si absente)
  sed -n "s/^$1=//p" $SETTINGS | tail -1
}

create_settings() {  # docker.env absent : le créer à partir des modèles des modules
  if [[ -f $SETTINGS ]]; then
    ok "Réglages : $SETTINGS"
    return 0
  fi
  local template
  for template in $TEMPLATES; do [[ -f $template ]] || fail "Modèle introuvable : $template"; done
  {
    print "# Réglages des conteneurs sur ce poste (docker-deploy.zsh, docker-deploy.ps1)."
    print "# Le SEUL vrai fichier de réglages, non suivi par Git. Créé en mettant bout à bout les modèles"
    print "# du script (deployment/) et de chaque module (postgres/, liquibase/, keycloak/, backend/, frontend/) : docker.example.env."
    print "# Voir docs/deploiement.md, section 7."
    print "#"
    print "# Une ligne VARIABLE=valeur par réglage, sans guillemets. Ne pas laisser de ligne « VARIABLE= »"
    print "# vide : elle remplacerait la valeur prévue par l'image par du vide. Chaque conteneur reçoit"
    print "# tout le fichier (sauf DHI_USERNAME et DHI_TOKEN, gardés pour le script), et ignore ce qui ne le concerne pas."
    print
    # Les secrets, vides dans les modèles, sont tirés au hasard : le mot de passe de la base,
    # recopié aux trois endroits qui l'attendent ; celui de l'utilisateur de Keycloak dans la base ;
    # l'administrateur provisoire de Keycloak ; le compte « admin » de l'outil ; la clé du client
    # de l'API dans Keycloak (lue par Keycloak et par l'API).
    cat $TEMPLATES | sed -E \
      -e "s/^(POSTGRES_PASSWORD|LIQUIBASE_COMMAND_PASSWORD|APP_DB_PASSWORD)=$/\1=$(openssl rand -hex 16)/" \
      -e "s/^(KC_DB_PASSWORD)=$/\1=$(openssl rand -hex 16)/" \
      -e "s/^(KC_BOOTSTRAP_ADMIN_PASSWORD)=$/\1=$(openssl rand -hex 16)/" \
      -e "s/^(APP_ADMIN_PASSWORD)=$/\1=$(openssl rand -hex 8)/" \
      -e "s/^(APP_KEYCLOAK_CLIENT_SECRET)=$/\1=$(openssl rand -hex 24)/"
  } > $SETTINGS
  info "$SETTINGS créé à partir des modèles des modules, avec ses mots de passe et clés tirés au hasard : à adapter si besoin (nom de l'instance…)"
}

check_keycloak_settings() {  # un docker.env sans les réglages de Keycloak : le dire clairement
  local variable missing=()
  for variable in $KEYCLOAK_SETTINGS; do
    [[ -n $(setting $variable) ]] || missing+=($variable)
  done
  (( ${#missing} == 0 )) || fail "$SETTINGS date d'avant Keycloak (il manque ${(j:, :)missing}). Le mettre de côté (mv $SETTINGS $SETTINGS.ancien), puis relancer avec --reset : le script en recrée un, et la base repart de zéro."
}

check_port() {  # check_port <port>
  # Les ports tenus par Docker (ou Podman) lui-même, pour nos conteneurs actuels qui vont être
  # remplacés, ne comptent pas. Un autre programme (souvent l'API ou l'interface lancées sans
  # conteneur : uv run / npm run dev, un PostgreSQL installé sur le poste, ou l'autre des deux
  # moteurs) bloque le lancement.
  local program own_processes
  if [[ $ENGINE == podman ]]; then own_processes='^(gvproxy|podman|krunkit|vfkit)'; else own_processes='^(com\.docke|docker|vpnkit)'; fi
  program=$(lsof -nP -iTCP:$1 -sTCP:LISTEN 2>/dev/null | awk 'NR>1 {print $1}' \
    | grep -vE $own_processes | head -1 || true)
  [[ -z $program ]] || fail "Le port $1 du poste est déjà utilisé par « $program » : arrêtez ce programme, ou changez le port en haut du script."
  ok "Port $1 disponible"
}

login_dhi() {  # connexion à dhi.io (images de base durcies), si docker.env en donne les moyens
  local user token
  user=$(setting DHI_USERNAME); token=$(setting DHI_TOKEN)
  if [[ -z $user || -z $token ]]; then
    info "DHI_USERNAME et DHI_TOKEN vides dans $SETTINGS : on compte sur un « $ENGINE login dhi.io » déjà fait"
    return 0
  fi
  # Jeton passé par l'entrée standard : jamais sur la ligne de commande, ni à l'écran.
  print -r -- $token | $ENGINE login dhi.io --username $user --password-stdin >/dev/null \
    || fail "Connexion à dhi.io refusée pour $user : vérifier DHI_USERNAME et DHI_TOKEN dans $SETTINGS (jeton en lecture seule, voir docs/deploiement.md, section 7)."
  ok "Connecté à dhi.io ($user)"
}

prepare_container_settings() {  # copie de docker.env pour les conteneurs, sans les réglages du script
  # CONTAINER_SETTINGS : fichier provisoire (mktemp, lisible par vous seul), effacé à la sortie du
  # script par le « trap » posé à côté de l'appel (dans une fonction, zsh l'exécuterait dès sa fin).
  grep -vE "^(${(j:|:)SCRIPT_SETTINGS})=" $SETTINGS > $CONTAINER_SETTINGS || true
}

build_image() {  # build_image <image> <dossier du module>
  $ENGINE build -t $1 $2 || fail "La fabrication de l'image $1 a échoué (voir ci-dessus ; image de base refusée : connexion à dhi.io, DHI_USERNAME et DHI_TOKEN de $SETTINGS)."
  ok "Image $1 prête"
}

remove_container() {  # remove_container <nom>
  if exists container $1; then
    $ENGINE rm -f $1 >/dev/null
    ok "Conteneur $1 supprimé"
  fi
}

prepare_network() {
  if exists network $NETWORK; then
    ok "Réseau $NETWORK : existe déjà"
  else
    $ENGINE network create $NETWORK >/dev/null
    ok "Réseau $NETWORK : créé"
  fi
}

prepare_volume() {
  if [[ $RESET == true ]] && exists volume $VOLUME; then
    $ENGINE volume rm $VOLUME >/dev/null
    ok "Volume $VOLUME effacé (--reset) : on repart de zéro"
  fi
  if exists volume $VOLUME; then
    ok "Volume $VOLUME : existe déjà, données conservées"
  else
    $ENGINE volume create $VOLUME >/dev/null
    ok "Volume $VOLUME : créé"
  fi
}

wait_for() {  # wait_for <ce qu'on vérifie> <conteneur dont afficher les journaux> <adresse> [secondes]
  for _ in {1..${4:-30}}; do
    curl -fs -o /dev/null "$3" && { ok "$1 répond ($3)"; return 0; }
    sleep 1
  done
  print -P "%F{red}✘ $1 ne répond pas. Derniers journaux de $2 :%f" >&2
  $ENGINE logs --tail 20 $2 >&2
  exit 1
}

sql() {  # sql <requête> : résultat brut d'une requête dans la base (psql du conteneur PostgreSQL)
  $ENGINE exec $POSTGRES psql -U $DB_USER -d $DB_NAME -tAc "$1"
}

wait_for_postgres() {
  # -h 127.0.0.1 : on attend le vrai serveur (au premier lancement, PostgreSQL démarre d'abord
  # un serveur provisoire, sans réseau, le temps de créer la base).
  for _ in {1..30}; do
    if $ENGINE exec $POSTGRES pg_isready -q -h 127.0.0.1 -U $DB_USER -d $DB_NAME 2>/dev/null; then
      ok "PostgreSQL répond (localhost:$PORT_POSTGRES)"
      return 0
    fi
    sleep 1
  done
  print -P "%F{red}✘ PostgreSQL ne répond pas. Derniers journaux de $POSTGRES :%f" >&2
  $ENGINE logs --tail 20 $POSTGRES >&2
  exit 1
}

start_postgres() {
  # Le volume est monté sur /var/lib/postgresql : PostgreSQL 18 range ses fichiers dans un
  # sous-dossier par version (18/data), ce qui facilitera les montées de version.
  $ENGINE run -d --name $POSTGRES --network $NETWORK -p 127.0.0.1:$PORT_POSTGRES:5432 \
    --env-file $CONTAINER_SETTINGS -v $VOLUME:/var/lib/postgresql $POSTGRES >/dev/null
  wait_for_postgres
}

ensure_database_running() {  # pour liquibase et backend lancés seuls : la base doit tourner
  exists container $POSTGRES || fail "La base ne tourne pas : lancer d'abord $COMMAND postgres"
  if [[ $($ENGINE container inspect -f '{{.State.Running}}' $POSTGRES) != true ]]; then
    $ENGINE start $POSTGRES >/dev/null
    ok "Conteneur $POSTGRES redémarré"
  fi
  wait_for_postgres
}

check_schema() {  # la base a-t-elle été préparée pour cette version (schéma de nos tables) ?
  [[ -n $(sql "select 1 from pg_namespace where nspname = '$DB_SCHEMA'") ]] \
    || fail "La base n'a pas de schéma « $DB_SCHEMA » : elle date d'avant Keycloak. Relancer avec --reset (ses données seront effacées)."
}

apply_structure() {
  # Liquibase reçoit l'adresse de la base, l'utilisateur et le mot de passe, déduits de POSTGRES_*.
  $ENGINE run --rm --network $NETWORK --env-file $CONTAINER_SETTINGS $LIQUIBASE update || fail "Liquibase n'a pas pu appliquer la structure de la base (voir ci-dessus)."
  ok "Structure de la base à jour (Liquibase)"
}

start_keycloak() {
  # Port du poste : la console d'administration de Keycloak (développement). Les pages de
  # connexion, elles, passent par l'interface (http://localhost:$PORT_FRONTEND/auth).
  $ENGINE run -d --name $KEYCLOAK --network $NETWORK -p 127.0.0.1:$PORT_KEYCLOAK:8080 \
    --env-file $CONTAINER_SETTINGS $KEYCLOAK >/dev/null
  # Le premier démarrage prépare ses tables et importe le domaine : jusqu'à une ou deux minutes.
  wait_for "Keycloak" $KEYCLOAK "http://localhost:$PORT_KEYCLOAK/auth/realms/suivi-delivery/.well-known/openid-configuration" 180
  # Domaine importé à l'instant (base neuve) : le compte « admin » de l'outil vient d'être créé.
  # (Keycloak écrit ses journaux sur les deux sorties : d'où « 2>&1 ». Lus d'abord en entier :
  # « grep -q » s'arrêtant au premier résultat, « pipefail » prendrait la fin de la lecture pour une erreur.)
  local logs
  logs=$($ENGINE logs $KEYCLOAK 2>&1)
  if [[ $logs == *"Realm 'suivi-delivery' imported"* ]]; then KEYCLOAK_IMPORTED=true; fi
}

start_backend() {
  $ENGINE run -d --name $BACKEND --network $NETWORK -p $PORT_BACKEND:8000 \
    --env-file $CONTAINER_SETTINGS $BACKEND >/dev/null
  wait_for "Le backend" $BACKEND "http://localhost:$PORT_BACKEND/readyz"
  if [[ $($ENGINE container inspect -f '{{.State.Running}}' $KEYCLOAK 2>/dev/null) != true ]]; then
    info "Keycloak ne tourne pas : l'API refusera les jetons (lancer : $COMMAND keycloak)"
  fi
}

start_frontend() {
  $ENGINE run -d --name $FRONTEND --network $NETWORK -p $PORT_FRONTEND:8080 \
    --env-file $CONTAINER_SETTINGS $FRONTEND >/dev/null
  wait_for "Le frontend" $FRONTEND "http://localhost:$PORT_FRONTEND/health"
  wait_for "La page de connexion" $FRONTEND "http://localhost:$PORT_FRONTEND/login"
  if [[ $($ENGINE container inspect -f '{{.State.Running}}' $KEYCLOAK 2>/dev/null) == true ]]; then
    wait_for "Keycloak, servi par l'interface" $FRONTEND \
      "http://localhost:$PORT_FRONTEND/auth/realms/suivi-delivery/.well-known/openid-configuration"
  else
    info "Keycloak ne tourne pas : impossible de se connecter (lancer : $COMMAND keycloak)"
  fi
  if [[ $($ENGINE container inspect -f '{{.State.Running}}' $BACKEND 2>/dev/null) != true ]]; then
    info "Le backend ne tourne pas : l'interface s'affiche, mais « Les données sont momentanément indisponibles » (lancer : $COMMAND backend)"
  fi
}

show_admin_account() {
  if [[ $KEYCLOAK_IMPORTED == true ]]; then
    print -P "  %F{yellow}Compte admin     créé à l'instant. Identifiant : admin   Mot de passe : %B$(setting APP_ADMIN_PASSWORD)%b%f"
    print -P "  %F{yellow}                 (APP_ADMIN_PASSWORD de $SETTINGS ; le changer ensuite dans « Mon compte »)%f"
  else
    print "  Compte admin     créé lors d'un lancement précédent : identifiant admin, mot de passe initial"
    print "                   APP_ADMIN_PASSWORD de $SETTINGS (sauf s'il a été changé depuis dans « Mon compte »)"
  fi
  print "  Console Keycloak http://localhost:$PORT_KEYCLOAK/auth/admin   (KC_BOOTSTRAP_ADMIN_* de $SETTINGS ; ce poste seulement)"
}

# --- Vérifications avant de commencer (rien n'est encore modifié) --------------
# Se placer à la racine du projet (le dossier au-dessus du script), d'où que l'on lance.
cd "${0:A:h}/.."   # racine du projet, d'où que l'on lance

step "Vérifications"
command -v $ENGINE >/dev/null || fail "$ENGINE est introuvable : l'installer d'abord (voir docs/deploiement.md, section 7)."
if [[ $ENGINE == podman ]]; then
  podman info >/dev/null 2>&1 || fail "Podman ne répond pas : démarrez sa machine (podman machine start), puis relancez."
else
  docker info >/dev/null 2>&1 || fail "Docker ne répond pas : démarrez Docker Desktop, puis relancez."
fi
ok "Conteneurs fabriqués et lancés par $ENGINE"
! selected postgres  || [[ -f postgres/Dockerfile ]]  || fail "Fichier introuvable : postgres/Dockerfile"
! selected liquibase || [[ -f liquibase/Dockerfile ]] || fail "Fichier introuvable : liquibase/Dockerfile"
! selected keycloak  || [[ -f keycloak/Dockerfile ]]  || fail "Fichier introuvable : keycloak/Dockerfile"
! selected backend   || [[ -f backend/Dockerfile ]]   || fail "Fichier introuvable : backend/Dockerfile"
! selected frontend  || [[ -f frontend/Dockerfile ]]  || fail "Fichier introuvable : frontend/Dockerfile"
create_settings
check_keycloak_settings
CONTAINER_SETTINGS=$(mktemp)
trap 'rm -f $CONTAINER_SETTINGS' EXIT
prepare_container_settings
if [[ $NEEDS_DATABASE == true ]]; then
  # La base de référence : POSTGRES_*.
  DB_NAME=$(setting POSTGRES_DB); DB_USER=$(setting POSTGRES_USER); DB_PASSWORD=$(setting POSTGRES_PASSWORD)
  [[ -n $DB_NAME && -n $DB_USER && -n $DB_PASSWORD ]] \
    || fail "POSTGRES_DB, POSTGRES_USER et POSTGRES_PASSWORD doivent être renseignés dans $SETTINGS"
  DB_SCHEMA=$(setting APP_DB_SCHEMA); DB_SCHEMA=${DB_SCHEMA:-suivi_delivery}
  # Règle d'or : rien d'incohérent. Liquibase, Keycloak et l'API doivent viser cette base, avec ce
  # compte (Keycloak : le sien), et le même schéma pour nos tables.
  expected_values=()
  if selected liquibase; then
    expected_values+=(LIQUIBASE_COMMAND_URL "jdbc:postgresql://$POSTGRES:5432/$DB_NAME?currentSchema=$DB_SCHEMA"
               LIQUIBASE_COMMAND_USERNAME $DB_USER LIQUIBASE_COMMAND_PASSWORD $DB_PASSWORD)
  fi
  if selected keycloak; then
    expected_values+=(KC_DB_URL "jdbc:postgresql://$POSTGRES:5432/$DB_NAME")
  fi
  if selected backend; then
    expected_values+=(APP_DB_HOST $POSTGRES APP_DB_PORT 5432 APP_DB_NAME $DB_NAME
               APP_DB_USER $DB_USER APP_DB_PASSWORD $DB_PASSWORD)
  fi
  for variable expected in "${expected_values[@]}"; do
    if [[ $(setting $variable) != $expected ]]; then
      [[ $variable == *PASSWORD ]] && expected="la même valeur que POSTGRES_PASSWORD"  # jamais affiché
      fail "$variable de $SETTINGS ne correspond pas à la base : attendu $expected"
    fi
  done
  (( ${#expected_values} == 0 )) || ok "Liquibase, Keycloak et l'API visent bien la base $DB_NAME ($POSTGRES)"
fi
# Keycloak est servi par l'interface, sous /auth : son adresse publique en découle, et l'API comme
# l'interface le joignent par son conteneur.
FRONTEND_URL=$(setting APP_FRONTEND_URL)
for variable expected in KC_HOSTNAME "$FRONTEND_URL/auth" \
    APP_KEYCLOAK_URL "http://$KEYCLOAK:8080/auth" KEYCLOAK_URL "http://$KEYCLOAK:8080/auth"; do
  [[ $(setting $variable) == $expected ]] || fail "$variable de $SETTINGS ne correspond pas : attendu $expected"
done
ok "Keycloak servi sous $FRONTEND_URL/auth, joint par l'API et l'interface sur $KEYCLOAK"
! selected postgres || check_port $PORT_POSTGRES
! selected keycloak || check_port $PORT_KEYCLOAK
! selected backend  || check_port $PORT_BACKEND
! selected frontend || check_port $PORT_FRONTEND

# --- 1. Fabriquer les images (avant de toucher aux conteneurs en place) --------
step "Fabrication des images"
login_dhi
! selected postgres  || build_image $POSTGRES postgres
! selected liquibase || build_image $LIQUIBASE liquibase
! selected keycloak  || build_image $KEYCLOAK keycloak
! selected backend   || build_image $BACKEND backend
! selected frontend  || build_image $FRONTEND frontend

# --- 2. Supprimer les conteneurs à remplacer (les données de la base restent dans son volume) ---
step "Remplacement des conteneurs"
! selected frontend || remove_container $FRONTEND
! selected backend  || remove_container $BACKEND
! selected keycloak || remove_container $KEYCLOAK
! selected postgres || remove_container $POSTGRES

# --- 3. Réseau, et volume des données (base) ------------------------------------
step "Réseau et volume"
prepare_network
! selected postgres || prepare_volume

# --- 4. Lancer (dans l'ordre : chacun s'appuie sur le précédent) -----------------
step "Démarrage"
if selected postgres; then start_postgres; elif [[ $NEEDS_DATABASE == true ]]; then ensure_database_running; fi
[[ $NEEDS_DATABASE == false ]] || check_schema
! selected liquibase || apply_structure
! selected keycloak  || start_keycloak
! selected backend   || start_backend
! selected frontend  || start_frontend

step "C'est prêt"
! selected frontend || print "  Interface        http://localhost:$PORT_FRONTEND"
! selected backend  || print "  API (Swagger)    http://localhost:$PORT_BACKEND/api/docs"
[[ $NEEDS_DATABASE == false ]] || print "  Base             localhost:$PORT_POSTGRES   base $DB_NAME, utilisateur $DB_USER (mot de passe : $SETTINGS)"
! selected keycloak || show_admin_account
print "  Journaux         $ENGINE logs -f <conteneur>   ($POSTGRES, $KEYCLOAK, $BACKEND, $FRONTEND)"
