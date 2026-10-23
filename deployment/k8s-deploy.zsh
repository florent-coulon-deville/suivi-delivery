#!/bin/zsh
# Installe (ou met à jour) l'application sur un cluster Kubernetes, quel qu'il soit : OpenShift,
# kind sur le poste, ou tout autre cluster joignable par kubectl. Voir docs/deploiement.md, section 9.
#
# Le cluster visé est un « contexte » kubectl (kubectl config get-contexts) : celui en cours,
# ou celui donné avec --context. Sur OpenShift, « oc login » crée ce contexte.
#
# Usage, depuis n'importe quel dossier :
#   ./deployment/k8s-deploy.zsh                                  le contexte kubectl en cours
#   ./deployment/k8s-deploy.zsh --context kind-suivi-delivery   un cluster kind sur le poste (créé s'il manque)
#   ./deployment/k8s-deploy.zsh --context kind-suivi-delivery --podman
#                                                     la même chose, avec kind sur Podman au lieu de Docker
#   ./deployment/k8s-deploy.zsh --context <contexte> --values helm/valeurs-recette.yaml
#                                                     un cluster, avec ses réglages
#
# Options :
#   --context <nom>      le contexte kubectl visé (défaut : celui en cours)
#   --namespace <nom>    l'espace de noms (namespace) ; défaut : suivi-delivery
#   --values <fichier>   un fichier de valeurs Helm en plus (réglages du cluster) ; répétable
#   --registry <adresse> d'où le cluster télécharge les images (hors kind) ;
#                        défaut : ghcr.io/florent-coulon-deville (images publiées par la CI)
#   --yes                ne pas demander confirmation avant d'installer (hors kind)
#   --reset              kind seulement : supprime d'abord le cluster, on repart de zéro
#   --podman             Podman au lieu de Docker : kind tourne sur Podman, les images sont fabriquées
#                        par Podman ; hors kind, Podman vérifie seulement que les images sont publiées
#
# Ce qui change selon le cluster :
#   kind (contexte « kind-<nom> »)  le cluster est créé s'il n'existe pas ; les images sont
#                                   fabriquées sur le poste et chargées directement dans kind
#                                   (pas de registre) : on essaie le code tel qu'il est.
#                                   Connexion à Docker Hub (images de base, facultative) : DHI_USERNAME et DHI_TOKEN
#                                   de deployment/docker.env s'ils sont remplis, sinon un
#                                   téléchargement sans connexion (limité par Docker Hub).
#                                   Avec Docker (défaut) ou Podman (--podman) : un cluster kind
#                                   créé avec l'un n'est pas vu par l'autre.
#   tout autre cluster              le script demande confirmation ; le cluster télécharge les
#                                   images <registre>/suivi-delivery-*:<version>, qui doivent
#                                   donc être publiées (par la CI, à la sortie de la version).
# Les deux : helm upgrade --install, puis « helm test ». Si helm/suivi-delivery/values-secret.yaml
# existe (accès à un registre privé), il est utilisé.

setopt errexit nounset pipefail

CHART=helm/suivi-delivery
INSTALLATION=suivi-delivery    # nom de l'installation Helm
NAMESPACE=suivi-delivery          # espace de noms Kubernetes (--namespace)
REGISTRY=""                    # registre des images publiées (--registry ; défaut plus bas)
LOCAL_PORT=8080                # pour « kubectl port-forward » (affiché à la fin)
ENGINE=docker                  # fabrique les images et fait tourner kind : docker, ou podman (--podman)
# Les images du projet : nom → dossier de son Dockerfile (image « suivi-delivery-<nom> »).
typeset -A FOLDERS=(backend backend frontend frontend)

step()  { print -P "\n%F{blue}==> $1%f"; }
ok()     { print -P "%F{green}✔ $1%f"; }
info()   { print -P "%F{yellow}! $1%f"; }
fail() { print -P "%F{red}✘ $1%f" >&2; exit 1; }

# Connexion à Docker Hub (images de base) avant de fabriquer, avec DHI_USERNAME et DHI_TOKEN
# de deployment/docker.env (le fichier de docker-deploy.zsh ; voir deployment/docker.example.env).
login_docker_hub() {
  local settings=deployment/docker.env user="" token=""
  if [[ -f $settings ]]; then
    user=$(sed -n 's/^DHI_USERNAME=//p' $settings | tail -1); token=$(sed -n 's/^DHI_TOKEN=//p' $settings | tail -1)
  fi
  if [[ -z $user || -z $token ]]; then
    info "DHI_USERNAME et DHI_TOKEN absents de $settings : images de base téléchargées sans connexion (Docker Hub limite alors le nombre de téléchargements)"
    return 0
  fi
  # Jeton passé par l'entrée standard : jamais sur la ligne de commande, ni à l'écran.
  print -r -- $token | $ENGINE login docker.io --username $user --password-stdin >/dev/null \
    || fail "Connexion à Docker Hub refusée pour $user : vérifier DHI_USERNAME et DHI_TOKEN dans $settings."
  ok "Connecté à Docker Hub ($user)"
}

usage="Usage : ./deployment/k8s-deploy.zsh [--context <nom>] [--namespace <nom>] [--values <fichier>]… [--registry <adresse>] [--yes] [--reset] [--podman]"

# --- Options -------------------------------------------------------------------
CONTEXT=""
VALUES=()
CONFIRMED=false
RESET=false
while (( $# > 0 )); do
  case $1 in
    --context| --namespace| --values| --registry)
      (( $# >= 2 )) || fail "$1 attend une valeur. $usage"
      case $1 in
        --context) CONTEXT=$2 ;;
        --namespace)   NAMESPACE=$2 ;;
        --values)  VALUES+=(-f $2) ;;
        --registry) REGISTRY=${2%/} ;;
      esac
      shift 2 ;;
    --yes)           CONFIRMED=true; shift ;;
    --reset) RESET=true; shift ;;
    --podman)        ENGINE=podman; shift ;;
    -h| --help)       print $usage; exit 0 ;;
    *)               fail "Option inconnue : $1. $usage" ;;
  esac
done

cd "${0:A:h}/.."   # racine du projet, d'où que l'on lance

# --- Vérifications (rien n'est encore modifié) --------------------------------------------
step "Vérifications"
for tool in kubectl helm; do
  command -v $tool >/dev/null || fail "$tool est introuvable : l'installer d'abord (voir docs/deploiement.md)."
done
VERSION=$(sed -n 's/^appVersion: *"\{0,1\}\([^"]*\)"\{0,1\}$/\1/p' $CHART/Chart.yaml)
[[ -n $VERSION ]] || fail "Version introuvable dans $CHART/Chart.yaml (appVersion)."
for (( i = 2; i <= ${#VALUES}; i += 2 )); do
  [[ -f ${VALUES[i]} ]] || fail "Fichier de valeurs introuvable : ${VALUES[i]}"
done

# Le cluster visé : le contexte donné, sinon celui en cours.
if [[ -z $CONTEXT ]]; then
  CONTEXT=$(kubectl config current-context 2>/dev/null) \
    || fail "Aucun contexte kubectl en cours : se connecter au cluster (oc login, kind…), ou préciser --context."
fi
KIND=false
[[ $CONTEXT == kind-* ]] && KIND=true
CLUSTER_KIND=${CONTEXT#kind-}
[[ $RESET == false || $KIND == true ]] || fail "--reset supprime le cluster : réservé à kind (contexte kind-…)."
if [[ $KIND == true ]]; then
  for tool in $ENGINE kind; do
    command -v $tool >/dev/null || fail "$tool est introuvable : l'installer d'abord (voir docs/deploiement.md)."
  done
  if [[ $ENGINE == podman ]]; then
    podman info >/dev/null 2>&1 || fail "Podman ne répond pas : démarrez sa machine (podman machine start), puis relancez."
    # kind sait faire tourner ses nœuds sur Podman : il suffit de le lui dire.
    export KIND_EXPERIMENTAL_PROVIDER=podman
    # Sans droits administrateur (« rootless »), les nœuds de kind démarrent mal sur Mac et Windows.
    [[ $(podman info --format '{{.Host.Security.Rootless}}' 2>/dev/null) != true ]] \
      || info "Machine Podman sans droits administrateur : kind risque d'échouer (podman machine stop ; podman machine set --rootful ; podman machine start)"
  else
    docker info >/dev/null 2>&1 || fail "Docker ne répond pas : démarrez Docker Desktop, puis relancez."
    export KIND_EXPERIMENTAL_PROVIDER=docker  # même si le poste a choisi Podman par défaut
  fi
else
  kubectl config get-contexts -o name | grep -qx -- "$CONTEXT" \
    || fail "Contexte kubectl inconnu : $CONTEXT (voir : kubectl config get-contexts)."
fi
ok "Outils présents ; version de l'application : $VERSION${${KIND:#false}:+ ; kind sur $ENGINE}"
[[ -n $REGISTRY ]] || REGISTRY=ghcr.io/florent-coulon-deville

# Toutes les commandes visent ce contexte, et seulement lui.
K=(kubectl --context $CONTEXT)
H=(helm --kube-context $CONTEXT)

# --- 1. Cluster ------------------------------------------------------------------------------
step "Cluster « $CONTEXT »"
if [[ $KIND == true ]]; then
  if [[ $RESET == true ]] && kind get clusters 2>/dev/null | grep -qx -- $CLUSTER_KIND; then
    kind delete cluster --name $CLUSTER_KIND
    ok "Cluster kind supprimé (--reset) : on repart de zéro"
  fi
  if kind get clusters 2>/dev/null | grep -qx -- $CLUSTER_KIND; then
    ok "Cluster kind : existe déjà"
  else
    kind create cluster --name $CLUSTER_KIND --wait 120s
    ok "Cluster kind : créé"
  fi
fi
$K cluster-info >/dev/null 2>&1 || fail "Le cluster $CONTEXT ne répond pas (connexion expirée ? oc login…)."
SERVER=$($K config view --minify -o jsonpath='{.clusters[0].cluster.server}')
ok "Cluster joignable : $SERVER"

if [[ $KIND == false && $CONFIRMED == false ]]; then
  # Un vrai cluster : on montre où l'on va installer, et on attend un « oui ».
  print "  Installation « $INSTALLATION », version $VERSION, espace de noms « $NAMESPACE »"
  print "  sur le cluster $SERVER (contexte $CONTEXT)"
  read -r "answer?  Continuer ? [o/N] "
  [[ $answer == [oOyY]* ]] || fail "Abandon : rien n'a été modifié."
fi

# --- 2. Images ---------------------------------------------------------------------------------
step "Images (version $VERSION)"
IMAGES=()
if [[ $KIND == true ]]; then
  # Fabriquées sur le poste, puis copiées directement dans kind : pas besoin de registre.
  login_docker_hub
  if [[ $ENGINE == podman ]]; then
    # « kind load docker-image » ne sait parler qu'à Docker : avec Podman, l'image passe par un
    # fichier (podman save, puis kind load image-archive), effacé à la fin.
    ARCHIVES=$(mktemp -d)
    trap 'rm -rf $ARCHIVES' EXIT
  fi
  for part in ${(k)FOLDERS}; do
    if [[ $ENGINE == podman ]]; then
      # Nom complet docker.io/library/… : celui sous lequel kind cherche « suivi-delivery-…:<version> »
      # (Podman nommerait sinon l'image localhost/…, que le cluster ne trouverait pas).
      image=docker.io/library/suivi-delivery-$part:$VERSION
      podman build -t $image ${FOLDERS[$part]} || fail "La fabrication de l'image $part a échoué (image de base introuvable, ou limite de téléchargement de Docker Hub atteinte)."
      podman save -o $ARCHIVES/$part.tar $image || fail "L'enregistrement de l'image $part a échoué."
      kind load image-archive $ARCHIVES/$part.tar --name $CLUSTER_KIND
      rm -f $ARCHIVES/$part.tar
    else
      docker build -t suivi-delivery-$part:$VERSION ${FOLDERS[$part]} \
        || fail "La fabrication de l'image $part a échoué (image de base introuvable, ou limite de téléchargement de Docker Hub atteinte)."
      kind load docker-image suivi-delivery-$part:$VERSION --name $CLUSTER_KIND
    fi
    ok "Image suivi-delivery-$part:$VERSION fabriquée et chargée dans kind"
  done
  IMAGES+=(--set images.registry=)  # registre vide : le chart les cherche sous leur nom court
else
  # Le cluster les télécharge dans le registre : elles doivent y être publiées pour cette version.
  IMAGES+=(--set images.registry=$REGISTRY)
  for part in ${(k)FOLDERS}; do
    if command -v $ENGINE >/dev/null && ! $ENGINE manifest inspect $REGISTRY/suivi-delivery-$part:$VERSION >/dev/null 2>&1; then
      info "Image $REGISTRY/suivi-delivery-$part:$VERSION introuvable depuis ce poste (pas publiée, ou registre privé : $ENGINE login)"
    else
      ok "Image $REGISTRY/suivi-delivery-$part:$VERSION"
    fi
  done
fi

# --- 3. Installation ---------------------------------------------------------------------------
step "Installation du chart"
SECRETS=()
if [[ -f $CHART/values-secret.yaml ]]; then
  SECRETS=(-f $CHART/values-secret.yaml)
  ok "Secrets lus dans $CHART/values-secret.yaml"
else
  info "Pas de $CHART/values-secret.yaml : pas de registre privé"
fi
INSTANCE=()
[[ $KIND == false ]] || INSTANCE=(--set application.instanceName=kind)
$H upgrade --install $INSTALLATION ./$CHART -n $NAMESPACE --create-namespace \
  "${SECRETS[@]}" "${VALUES[@]}" "${IMAGES[@]}" "${INSTANCE[@]}" --wait --timeout 5m
ok "Chart installé (installation « $INSTALLATION », espace de noms « $NAMESPACE »)"

# --- 4. Test -------------------------------------------------------------------------------------
step "Test Helm"
$H test $INSTALLATION -n $NAMESPACE --logs || fail "Le test a échoué (voir ci-dessus ; ${K[*]} get pods -n $NAMESPACE)."

# --- Récapitulatif ---------------------------------------------------------------------------------
step "C'est prêt"
ROUTE=$($K get route $INSTALLATION -n $NAMESPACE -o jsonpath='{.spec.host}' 2>/dev/null || true)
if [[ -n $ROUTE ]]; then
  print "  Interface           https://$ROUTE"
else
  print "  Ouvrir l'interface  ${K[*]} port-forward -n $NAMESPACE service/$INSTALLATION-frontend $LOCAL_PORT:8080"
  print "                      puis http://localhost:$LOCAL_PORT"
fi
print "  État des pods       ${K[*]} get pods -n $NAMESPACE"
if [[ $KIND == true ]]; then
  print "  Tout supprimer      ${${ENGINE:#docker}:+KIND_EXPERIMENTAL_PROVIDER=podman }kind delete cluster --name $CLUSTER_KIND"
else
  print "  Désinstaller        ${H[*]} uninstall $INSTALLATION -n $NAMESPACE   (le disque des données est conservé)"
fi
