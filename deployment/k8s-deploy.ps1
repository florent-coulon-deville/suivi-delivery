#!/usr/bin/env pwsh
#Requires -Version 7.0
# Installe (ou met à jour) l'application sur un cluster Kubernetes, quel qu'il soit : OpenShift,
# kind sur le poste, ou tout autre cluster joignable par kubectl. Version PowerShell 7 (pwsh) de
# k8s-deploy.zsh : même comportement, mêmes options. Voir docs/deploiement.md, section 9.
#
# Le cluster visé est un « contexte » kubectl (kubectl config get-contexts) : celui en cours,
# ou celui donné avec --context. Sur OpenShift, « oc login » crée ce contexte.
#
# Usage, depuis n'importe quel dossier :
#   .\deployment\k8s-deploy.ps1                                  le contexte kubectl en cours
#   .\deployment\k8s-deploy.ps1 --context kind-suivi-delivery   un cluster kind sur le poste (créé s'il manque)
#   .\deployment\k8s-deploy.ps1 --context kind-suivi-delivery --podman
#                                                     la même chose, avec kind sur Podman au lieu de Docker
#   .\deployment\k8s-deploy.ps1 --context <contexte> --values helm/valeurs-recette.yaml
#                                                     un cluster, avec ses réglages
#
# Options :
#   --context <nom>      le contexte kubectl visé (défaut : celui en cours)
#   --namespace <nom>    l'espace de noms (namespace) ; défaut : suivi-delivery
#   --values <fichier>   un fichier de valeurs Helm en plus (réglages du cluster) ; répétable
#   --registry <adresse> d'où le cluster télécharge les images (hors kind) ;
#                        défaut : ghcr.io/artenola (images publiées par la CI)
#   --yes                ne pas demander confirmation avant d'installer (hors kind)
#   --reset              kind seulement : supprime d'abord le cluster, on repart de zéro
#   --podman             Podman au lieu de Docker : kind tourne sur Podman, les images sont fabriquées
#                        par Podman ; hors kind, Podman vérifie seulement que les images sont publiées
#
# Ce qui change selon le cluster :
#   kind (contexte « kind-<nom> »)  le cluster est créé s'il n'existe pas ; les images sont
#                                   fabriquées sur le poste et chargées directement dans kind
#                                   (pas de registre) : on essaie le code tel qu'il est.
#                                   Avec Docker (défaut) ou Podman (--podman) : un cluster kind
#                                   créé avec l'un n'est pas vu par l'autre.
#   tout autre cluster              le script demande confirmation ; le cluster télécharge les
#                                   images <registre>/suivi-delivery-*:<version>, qui doivent
#                                   donc être publiées (par la CI, à la sortie de la version).
# Les deux : helm upgrade --install, puis « helm test ». Si helm/suivi-delivery/values-secret.yaml
# existe, il est utilisé (sinon : mots de passe et clé générés à la première installation).
#
# Si Windows refuse de lancer le script (« l'exécution de scripts est désactivée ») :
#   pwsh -ExecutionPolicy Bypass -File .\deployment\k8s-deploy.ps1
# Réservé à pwsh (PowerShell 7 et plus) : l'ancien « Windows PowerShell » 5.1 est refusé d'emblée.
# Chaque commande externe est vérifiée par son code retour ($LASTEXITCODE), comme le « errexit » de zsh.

# Accents, « » et — lus correctement dans les sorties de kubectl, helm, docker et podman.
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$CHART = "helm/suivi-delivery"
$INSTALLATION = "suivi-delivery"    # nom de l'installation Helm
$NAMESPACE = "suivi-delivery"          # espace de noms Kubernetes (--namespace)
$REGISTRY = ""                      # registre des images publiées (--registry ; défaut plus bas)
$LOCAL_PORT = 8080                  # pour « kubectl port-forward » (affiché à la fin)
$ENGINE = "docker"                  # fabrique les images et fait tourner kind : docker, ou podman (--podman)
# Les images du projet : nom → dossier de son Dockerfile (image « suivi-delivery-<nom> »).
$FOLDERS = [ordered]@{ backend = "backend"; frontend = "frontend"; liquibase = "liquibase"; keycloak = "keycloak"; postgres = "postgres" }

function step($message) { Write-Host "`n==> $message" -ForegroundColor Blue }
function ok($message) { Write-Host "✔ $message" -ForegroundColor Green }
function info($message) { Write-Host "! $message" -ForegroundColor Yellow }
function fail($message) { Write-Host "✘ $message" -ForegroundColor Red; exit 1 }

$usage = "Usage : .\deployment\k8s-deploy.ps1 [--context <nom>] [--namespace <nom>] [--values <fichier>]… [--registry <adresse>] [--yes] [--reset] [--podman]"

# --- Options -------------------------------------------------------------------
$CONTEXT = ""
$VALUES = @()
$CONFIRMED = $false
$RESET = $false
for ($i = 0; $i -lt $args.Count; $i++) {
    $option = $args[$i]
    switch -Exact ($option) {
        { $_ -in "--context", "--namespace", "--values", "--registry" } {
            if ($i + 1 -ge $args.Count) { fail "$option attend une valeur. $usage" }
            $value = $args[++$i]
            switch ($option) {
                "--context" { $CONTEXT = $value }
                "--namespace" { $NAMESPACE = $value }
                "--values" { $VALUES += @("-f", $value) }
                "--registry" { $REGISTRY = $value.TrimEnd("/") }
            }
        }
        "--yes" { $CONFIRMED = $true }
        "--reset" { $RESET = $true }
        "--podman" { $ENGINE = "podman" }
        { $_ -in "-h", "--help" } { Write-Host $usage; exit 0 }
        default { fail "Option inconnue : $option. $usage" }
    }
}

Set-Location (Split-Path $PSScriptRoot -Parent)   # racine du projet, d'où que l'on lance

function outil_present($name) { return [bool](Get-Command $name -CommandType Application -ErrorAction SilentlyContinue) }  # programme installé ?

# --- Vérifications (rien n'est encore modifié) --------------------------------------------
step "Vérifications"
foreach ($tool in "kubectl", "helm") {
    if (-not (outil_present $tool)) { fail "$tool est introuvable : l'installer d'abord (voir docs/deploiement.md)." }
}
$line = Select-String -Path "$CHART/Chart.yaml" -Pattern '^appVersion:\s*"?([^"\s]+)"?' | Select-Object -First 1
if (-not $line) { fail "Version introuvable dans $CHART/Chart.yaml (appVersion)." }
$VERSION = $line.Matches[0].Groups[1].Value
for ($i = 1; $i -lt $VALUES.Count; $i += 2) {
    if (-not (Test-Path $VALUES[$i])) { fail "Fichier de valeurs introuvable : $($VALUES[$i])" }
}

# Le cluster visé : le contexte donné, sinon celui en cours.
if (-not $CONTEXT) {
    $CONTEXT = kubectl config current-context 2> $null
    if ($LASTEXITCODE -ne 0 -or -not $CONTEXT) {
        fail "Aucun contexte kubectl en cours : se connecter au cluster (oc login, kind…), ou préciser --context."
    }
}
$KIND = $CONTEXT.StartsWith("kind-")
$CLUSTER_KIND = $CONTEXT -replace '^kind-', ''
if ($RESET -and -not $KIND) { fail "--reset supprime le cluster : réservé à kind (contexte kind-…)." }
if ($KIND) {
    foreach ($tool in $ENGINE, "kind") {
        if (-not (outil_present $tool)) { fail "$tool est introuvable : l'installer d'abord (voir docs/deploiement.md)." }
    }
    if ($ENGINE -eq "podman") {
        podman info *> $null
        if ($LASTEXITCODE -ne 0) { fail "Podman ne répond pas : démarrez sa machine (podman machine start), puis relancez." }
        # kind sait faire tourner ses nœuds sur Podman : il suffit de le lui dire.
        $env:KIND_EXPERIMENTAL_PROVIDER = "podman"
        # Sans droits administrateur (« rootless »), les nœuds de kind démarrent mal sur Mac et Windows.
        if ((podman info --format '{{.Host.Security.Rootless}}' 2> $null) -eq "true") {
            info "Machine Podman sans droits administrateur : kind risque d'échouer (podman machine stop ; podman machine set --rootful ; podman machine start)"
        }
    } else {
        docker info *> $null
        if ($LASTEXITCODE -ne 0) { fail "Docker ne répond pas : démarrez Docker Desktop, puis relancez." }
        $env:KIND_EXPERIMENTAL_PROVIDER = "docker"  # même si le poste a choisi Podman par défaut
    }
} else {
    $contexts = kubectl config get-contexts -o name
    if ($contexts -notcontains $CONTEXT) { fail "Contexte kubectl inconnu : $CONTEXT (voir : kubectl config get-contexts)." }
}
ok "Outils présents ; version de l'application : $VERSION$(if ($KIND) { " ; kind sur $ENGINE" })"
if (-not $REGISTRY) { $REGISTRY = "ghcr.io/artenola" }

# Toutes les commandes visent ce contexte, et seulement lui.
function k { kubectl --context $CONTEXT @args }
function helm_context { helm --kube-context $CONTEXT @args }  # pas « h » : alias de Get-History, prioritaire sur une fonction

function kind_cluster_exists { return ((kind get clusters 2> $null) -contains $CLUSTER_KIND) }

# --- 1. Cluster ------------------------------------------------------------------------------
step "Cluster « $CONTEXT »"
if ($KIND) {
    if ($RESET -and (kind_cluster_exists)) {
        kind delete cluster --name $CLUSTER_KIND
        if ($LASTEXITCODE -ne 0) { fail "La suppression du cluster kind a échoué." }
        ok "Cluster kind supprimé (--reset) : on repart de zéro"
    }
    if (kind_cluster_exists) {
        ok "Cluster kind : existe déjà"
    } else {
        kind create cluster --name $CLUSTER_KIND --wait 120s
        if ($LASTEXITCODE -ne 0) { fail "La création du cluster kind a échoué." }
        ok "Cluster kind : créé"
    }
}
k cluster-info *> $null
if ($LASTEXITCODE -ne 0) { fail "Le cluster $CONTEXT ne répond pas (connexion expirée ? oc login…)." }
$SERVER = k config view --minify -o jsonpath='{.clusters[0].cluster.server}'
ok "Cluster joignable : $SERVER"

if (-not $KIND -and -not $CONFIRMED) {
    # Un vrai cluster : on montre où l'on va installer, et on attend un « oui ».
    Write-Host "  Installation « $INSTALLATION », version $VERSION, espace de noms « $NAMESPACE »"
    Write-Host "  sur le cluster $SERVER (contexte $CONTEXT)"
    $answer = Read-Host "  Continuer ? [o/N]"
    if ($answer -notmatch '^[oOyY]') { fail "Abandon : rien n'a été modifié." }
}

# --- 2. Images ---------------------------------------------------------------------------------
step "Images (version $VERSION)"
$IMAGES = @()
if ($KIND) {
    # Fabriquées sur le poste, puis copiées directement dans kind : pas besoin de registre.
    foreach ($part in $FOLDERS.Keys) {
        $image = "suivi-delivery-${part}:$VERSION"
        if ($ENGINE -eq "podman") {
            # « kind load docker-image » ne sait parler qu'à Docker : avec Podman, l'image passe par un
            # fichier (podman save, puis kind load image-archive), effacé aussitôt.
            # Nom complet docker.io/library/… : celui sous lequel kind cherche « suivi-delivery-…:<version> »
            # (Podman nommerait sinon l'image localhost/…, que le cluster ne trouverait pas).
            $complete = "docker.io/library/$image"
            podman build -t $complete $FOLDERS[$part]
            if ($LASTEXITCODE -ne 0) { fail "La fabrication de l'image $part a échoué." }
            $archive = Join-Path ([IO.Path]::GetTempPath()) "suivi-delivery-$part-$PID.tar"
            try {
                podman save -o $archive $complete
                if ($LASTEXITCODE -ne 0) { fail "L'enregistrement de l'image $part a échoué." }
                kind load image-archive $archive --name $CLUSTER_KIND
                if ($LASTEXITCODE -ne 0) { fail "Le chargement de l'image $image dans kind a échoué." }
            } finally {
                Remove-Item $archive -ErrorAction SilentlyContinue
            }
        } else {
            docker build -t $image $FOLDERS[$part]
            if ($LASTEXITCODE -ne 0) { fail "La fabrication de l'image $part a échoué." }
            kind load docker-image $image --name $CLUSTER_KIND
            if ($LASTEXITCODE -ne 0) { fail "Le chargement de l'image $image dans kind a échoué." }
        }
        ok "Image $image fabriquée et chargée dans kind"
    }
    $IMAGES += @("--set", "images.registry=")  # registre vide : le chart les cherche sous leur nom court
} else {
    # Le cluster les télécharge dans le registre : elles doivent y être publiées pour cette version.
    $IMAGES += @("--set", "images.registry=$REGISTRY")
    foreach ($part in $FOLDERS.Keys) {
        $published = $true
        if (outil_present $ENGINE) {
            & $ENGINE manifest inspect "$REGISTRY/suivi-delivery-${part}:$VERSION" *> $null
            $published = ($LASTEXITCODE -eq 0)
        }
        if ($published) {
            ok "Image $REGISTRY/suivi-delivery-${part}:$VERSION"
        } else {
            info "Image $REGISTRY/suivi-delivery-${part}:$VERSION introuvable depuis ce poste (pas publiée, ou registre privé : $ENGINE login)"
        }
    }
}

# --- 3. Installation ---------------------------------------------------------------------------
step "Installation du chart"
$SECRETS = @()
if (Test-Path "$CHART/values-secret.yaml") {
    $SECRETS = @("-f", "$CHART/values-secret.yaml")
    ok "Secrets lus dans $CHART/values-secret.yaml"
} else {
    info "Pas de $CHART/values-secret.yaml : mots de passe (admin, base, Keycloak) et clé du client de l'API générés"
}
$INSTANCE = @()
if ($KIND) { $INSTANCE = @("--set", "application.nomInstance=kind") }
helm_context upgrade --install $INSTALLATION "./$CHART" -n $NAMESPACE --create-namespace @SECRETS @VALUES @IMAGES @INSTANCE --wait --timeout 10m  # Keycloak : long au premier démarrage
if ($LASTEXITCODE -ne 0) { fail "L'installation du chart a échoué (voir ci-dessus ; kubectl --context $CONTEXT get pods -n $NAMESPACE)." }
ok "Chart installé (installation « $INSTALLATION », espace de noms « $NAMESPACE »)"

# --- 4. Test -------------------------------------------------------------------------------------
step "Test Helm"
helm_context test $INSTALLATION -n $NAMESPACE --logs
if ($LASTEXITCODE -ne 0) { fail "Le test a échoué (voir ci-dessus ; kubectl --context $CONTEXT get pods -n $NAMESPACE)." }

# --- Récapitulatif ---------------------------------------------------------------------------------
step "C'est prêt"
$ROUTE = k get route $INSTALLATION -n $NAMESPACE -o jsonpath='{.spec.host}' 2> $null
if ($LASTEXITCODE -eq 0 -and $ROUTE) {
    Write-Host "  Interface           https://$ROUTE"
} else {
    Write-Host "  Ouvrir l'interface  kubectl --context $CONTEXT port-forward -n $NAMESPACE service/$INSTALLATION-frontend ${LOCAL_PORT}:8080"
    Write-Host "                      puis http://localhost:$LOCAL_PORT"
}
# Windows n'a pas la commande base64 : le mot de passe est décodé par PowerShell.
Write-Host "  Compte admin        mot de passe initial : [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String((kubectl --context $CONTEXT get secret $INSTALLATION-application -n $NAMESPACE -o jsonpath='{.data.APP_ADMIN_PASSWORD}')))"
Write-Host "  État des pods       kubectl --context $CONTEXT get pods -n $NAMESPACE"
if ($KIND) {
    $provider = if ($ENGINE -eq "podman") { '$env:KIND_EXPERIMENTAL_PROVIDER = "podman" ; ' } else { "" }
    Write-Host "  Tout supprimer      ${provider}kind delete cluster --name $CLUSTER_KIND"
} else {
    Write-Host "  Désinstaller        helm --kube-context $CONTEXT uninstall $INSTALLATION -n $NAMESPACE   (la base et le Secret sont conservés)"
}
