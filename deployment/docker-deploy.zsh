#!/bin/zsh
# Fabrique les images (Docker ou Podman) et (re)lance les conteneurs sur le poste : tout, ou un module.
# Voir docs/deploiement.md, section 7.
#
# Usage, depuis n'importe quel dossier :
#   ./deployment/docker-deploy.zsh                     tout : backend, puis frontend ; données CONSERVÉES
#   ./deployment/docker-deploy.zsh backend             l'API seule
#   ./deployment/docker-deploy.zsh frontend            l'interface seule
#   ./deployment/docker-deploy.zsh --reset             tout, en EFFAÇANT les données (repartir de zéro)
#   ./deployment/docker-deploy.zsh backend --reset     l'API seule, en effaçant les données
#   ./deployment/docker-deploy.zsh --podman …          la même chose avec Podman au lieu de Docker
#                                                         (raccourci : ./deployment/podman-deploy.zsh …)
#
# Docker ou Podman : les commandes sont les mêmes ; seul le programme appelé change. Les deux
# utilisent les mêmes noms de conteneurs, les mêmes ports et le même docker.env, mais chacun a
# ses propres images, son réseau et son volume (donc ses propres données) : ne pas les faire tourner
# en même temps (le script s'arrête si un port est déjà pris par l'autre).
#
# Les modules :
#   backend    l'API ; ses données dans un fichier SQLite, rangé dans un volume, conservé d'un
#              lancement à l'autre.
#   frontend   l'interface.
# Pas de connexion : cette version de l'outil n'a pas de comptes (tout le monde peut tout faire).
#
# Réglages : UN seul fichier, deployment/docker.env (non suivi par Git), reçu par chaque
# conteneur. S'il n'existe pas, le script le crée en mettant bout à bout les modèles de chaque
# module (<module>/docker.example.env), précédés de celui du script (deployment/docker.example.env :
# DHI_USERNAME, DHI_TOKEN, la connexion à dhi.io, d'où viennent les images de base ; remplis, le
# script se connecte avant de fabriquer ; ces lignes ne sont jamais transmises aux conteneurs).
# Chaque conteneur y trouve tous ses réglages (pas de « -e »).
#
# Le script s'arrête à la première erreur, avec un message. Une image qui ne se fabrique
# pas laisse les conteneurs en place : on ne supprime l'ancien que si le nouveau est prêt.

setopt errexit nounset pipefail

# --- Noms, images et ports (ports du poste : jamais le même pour deux services) ---
NETWORK=suivi-delivery-local
BACKEND=suivi-delivery-backend-local
FRONTEND=suivi-delivery-frontend-local
VOLUME=suivi-delivery-data-local    # données de l'API (fichier SQLite)
PORT_BACKEND=8000    # développement seulement : backend testable en direct
PORT_FRONTEND=8080

# Le fichier des réglages, et les modèles qui servent à le créer (dans cet ordre).
SETTINGS=deployment/docker.env
TEMPLATES=(deployment/docker.example.env backend/docker.example.env frontend/docker.example.env)
# Réglages du script lui-même (connexion à dhi.io) : retirés de la copie de docker.env donnée aux
# conteneurs, pour qu'aucun jeton n'entre dans un conteneur.
SCRIPT_SETTINGS=(DHI_USERNAME DHI_TOKEN)

# --- Outils d'affichage --------------------------------------------------------
step()  { print -P "\n%F{blue}==> $1%f"; }
ok()     { print -P "%F{green}✔ $1%f"; }
info()   { print -P "%F{yellow}! $1%f"; }
fail() { print -P "%F{red}✘ $1%f" >&2; exit 1; }

usage="Usage : ./deployment/docker-deploy.zsh [backend|frontend] [--reset] [--podman]"

# --- Options -------------------------------------------------------------------
TARGET=""
RESET=false
ENGINE=docker         # le programme qui fabrique et lance les conteneurs : docker, ou podman (--podman)
COMMAND=./deployment/docker-deploy.zsh   # pour les conseils affichés (« lancer : … »)
for option in "$@"; do
  case $option in
    backend|frontend)
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
selected backend || [[ $RESET == false ]] || fail "--reset efface les données de l'API : il ne s'utilise qu'avec backend (ou sans module)."

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
    print "# du script (deployment/) et de chaque module (backend/, frontend/) : docker.example.env."
    print "# Voir docs/deploiement.md, section 7."
    print "#"
    print "# Une ligne VARIABLE=valeur par réglage, sans guillemets. Ne pas laisser de ligne « VARIABLE= »"
    print "# vide : elle remplacerait la valeur prévue par l'image par du vide. Chaque conteneur reçoit"
    print "# tout le fichier (sauf DHI_USERNAME et DHI_TOKEN, gardés pour le script), et ignore ce qui ne le concerne pas."
    print
    cat $TEMPLATES
  } > $SETTINGS
  info "$SETTINGS créé à partir des modèles des modules : à adapter si besoin (nom de l'instance…)"
}

check_settings() {  # un docker.env d'une version précédente (PostgreSQL, Keycloak) : le dire clairement
  [[ -n $(setting APP_DB_FILE) ]] \
    || fail "$SETTINGS date d'une version précédente (il manque APP_DB_FILE). Le mettre de côté (mv $SETTINGS $SETTINGS.ancien), puis relancer : le script en recrée un."
}

check_port() {  # check_port <port>
  # Les ports tenus par Docker (ou Podman) lui-même, pour nos conteneurs actuels qui vont être
  # remplacés, ne comptent pas. Un autre programme (souvent l'API ou l'interface lancées sans
  # conteneur : uv run / npm run dev, ou l'autre des deux moteurs) bloque le lancement.
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

start_backend() {
  # Le volume est monté sur /data : le fichier SQLite (APP_DB_FILE) y est rangé.
  $ENGINE run -d --name $BACKEND --network $NETWORK -p $PORT_BACKEND:8000 \
    --env-file $CONTAINER_SETTINGS -v $VOLUME:/data $BACKEND >/dev/null
  wait_for "Le backend" $BACKEND "http://localhost:$PORT_BACKEND/readyz"
}

start_frontend() {
  $ENGINE run -d --name $FRONTEND --network $NETWORK -p $PORT_FRONTEND:8080 \
    --env-file $CONTAINER_SETTINGS $FRONTEND >/dev/null
  wait_for "Le frontend" $FRONTEND "http://localhost:$PORT_FRONTEND/health"
  if [[ $($ENGINE container inspect -f '{{.State.Running}}' $BACKEND 2>/dev/null) != true ]]; then
    info "Le backend ne tourne pas : l'interface s'affiche, mais « Les données sont momentanément indisponibles » (lancer : $COMMAND backend)"
  fi
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
! selected backend   || [[ -f backend/Dockerfile ]]   || fail "Fichier introuvable : backend/Dockerfile"
! selected frontend  || [[ -f frontend/Dockerfile ]]  || fail "Fichier introuvable : frontend/Dockerfile"
create_settings
check_settings
CONTAINER_SETTINGS=$(mktemp)
trap 'rm -f $CONTAINER_SETTINGS' EXIT
prepare_container_settings
! selected backend  || check_port $PORT_BACKEND
! selected frontend || check_port $PORT_FRONTEND

# --- 1. Fabriquer les images (avant de toucher aux conteneurs en place) --------
step "Fabrication des images"
login_dhi
! selected backend   || build_image $BACKEND backend
! selected frontend  || build_image $FRONTEND frontend

# --- 2. Supprimer les conteneurs à remplacer (les données restent dans le volume) ---
step "Remplacement des conteneurs"
! selected frontend || remove_container $FRONTEND
! selected backend  || remove_container $BACKEND

# --- 3. Réseau, et volume des données ------------------------------------------
step "Réseau et volume"
prepare_network
! selected backend || prepare_volume

# --- 4. Lancer (l'API d'abord : l'interface s'appuie sur elle) ------------------
step "Démarrage"
! selected backend   || start_backend
! selected frontend  || start_frontend

step "C'est prêt"
! selected frontend || print "  Interface        http://localhost:$PORT_FRONTEND"
! selected backend  || print "  API (Swagger)    http://localhost:$PORT_BACKEND/api/docs"
! selected backend  || print "  Données          volume $VOLUME, fichier $(setting APP_DB_FILE) dans le conteneur"
print "  Journaux         $ENGINE logs -f <conteneur>   ($BACKEND, $FRONTEND)"
