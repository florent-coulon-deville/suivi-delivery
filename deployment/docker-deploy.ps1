#!/usr/bin/env pwsh
#Requires -Version 7.0
# Fabrique les images (Docker ou Podman) et (re)lance les conteneurs sur le poste : tout, ou un module.
# Version PowerShell 7 (pwsh) de docker-deploy.zsh : même comportement.
# Voir docs/deploiement.md, section 7.
#
# Usage, depuis n'importe quel dossier :
#   .\deployment\docker-deploy.ps1                     tout : backend, puis frontend ; données CONSERVÉES
#   .\deployment\docker-deploy.ps1 backend             l'API seule
#   .\deployment\docker-deploy.ps1 frontend            l'interface seule
#   .\deployment\docker-deploy.ps1 --reset             tout, en EFFAÇANT les données (repartir de zéro)
#   .\deployment\docker-deploy.ps1 backend --reset     l'API seule, en effaçant les données
#   .\deployment\docker-deploy.ps1 --podman …          la même chose avec Podman au lieu de Docker
#                                                         (raccourci : .\deployment\podman-deploy.ps1 …)
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
# Si Windows refuse de lancer le script (« l'exécution de scripts est désactivée ») :
#   pwsh -ExecutionPolicy Bypass -File .\deployment\docker-deploy.ps1
# Réservé à pwsh (PowerShell 7 et plus) : l'ancien « Windows PowerShell » 5.1 est refusé d'emblée.
#
# Le script s'arrête à la première erreur, avec un message. Une image qui ne se fabrique
# pas laisse les conteneurs en place : on ne supprime l'ancien que si le nouveau est prêt.
#
# Pièges PowerShell évités ici :
#   - une option et sa valeur sont deux arguments séparés (-p "8000:8000"), jamais une seule
#     chaîne "-p 8000:8000" : Docker la refuserait (« invalid hostPort ») ;
#   - chaque commande docker (ou podman) est vérifiée par son code retour ($LASTEXITCODE), comme le
#     « errexit » de zsh ;
#   - GET et non HEAD pour attendre les services : /readyz ne répond qu'au GET.

# Accents, « » et — lus correctement dans les sorties de Docker ou Podman (journaux du backend).
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

# --- Noms, images et ports (ports du poste : jamais le même pour deux services) ---
$NETWORK = "suivi-delivery-local"
$BACKEND = "suivi-delivery-backend-local"
$FRONTEND = "suivi-delivery-frontend-local"
$VOLUME = "suivi-delivery-data-local"    # données de l'API (fichier SQLite)
$PORT_BACKEND = 8000    # développement seulement : backend testable en direct
$PORT_FRONTEND = 8080

# Le fichier des réglages, et les modèles qui servent à le créer (dans cet ordre).
$SETTINGS = "deployment/docker.env"
$TEMPLATES = "deployment/docker.example.env", "backend/docker.example.env", "frontend/docker.example.env"
# Réglages du script lui-même (connexion à dhi.io) : retirés de la copie de docker.env donnée aux
# conteneurs, pour qu'aucun jeton n'entre dans un conteneur.
$SCRIPT_SETTINGS = "DHI_USERNAME", "DHI_TOKEN"

# --- Outils d'affichage --------------------------------------------------------
function step($message) { Write-Host "`n==> $message" -ForegroundColor Blue }
function ok($message) { Write-Host "✔ $message" -ForegroundColor Green }
function info($message) { Write-Host "! $message" -ForegroundColor Yellow }
function fail($message) { Write-Host "✘ $message" -ForegroundColor Red; remove_container_settings; exit 1 }

$usage = "Usage : .\deployment\docker-deploy.ps1 [backend|frontend] [--reset] [--podman]"

# --- Options -------------------------------------------------------------------
$TARGET = ""
$RESET = $false
$ENGINE = "docker"   # le programme qui fabrique et lance les conteneurs : docker, ou podman (--podman)
$COMMAND = ".\deployment\docker-deploy.ps1"   # pour les conseils affichés (« lancer : … »)
foreach ($option in $args) {
    switch -Exact ($option) {
        { $_ -in "backend", "frontend" } {
            if ($TARGET) { fail "Un seul module à la fois (sans rien : tout). $usage" }
            $TARGET = $option
        }
        "--reset" { $RESET = $true }
        "--podman" { $ENGINE = "podman"; $COMMAND = ".\deployment\podman-deploy.ps1" }
        { $_ -in "-h", "--help" } { Write-Host $usage; exit 0 }
        default { fail "Option inconnue : $option. $usage" }
    }
}
function selected($module) { return (-not $TARGET) -or ($TARGET -eq $module) }  # ce module est-il à lancer ?
if ($RESET -and -not (selected "backend")) {
    fail "--reset efface les données de l'API : il ne s'utilise qu'avec backend (ou sans module)."
}

# --- Fonctions --------------------------------------------------------------------

function exists($type, $name) {  # exists <container|network|volume|image> <nom>
    & $ENGINE $type inspect $name *> $null
    return $LASTEXITCODE -eq 0
}

function setting($variable) {  # sa valeur dans docker.env (vide si absente)
    $lines = Get-Content $SETTINGS | Where-Object { $_ -match "^$variable=" }
    if ($lines) { return (@($lines)[-1] -replace "^$variable=", "") }
    return ""
}

function create_settings {  # docker.env absent : le créer à partir des modèles des modules
    if (Test-Path $SETTINGS) { ok "Réglages : $SETTINGS"; return }
    foreach ($template in $TEMPLATES) { if (-not (Test-Path $template)) { fail "Modèle introuvable : $template" } }
    $header = @(
        "# Réglages des conteneurs sur ce poste (docker-deploy.zsh, docker-deploy.ps1).",
        "# Le SEUL vrai fichier de réglages, non suivi par Git. Créé en mettant bout à bout les modèles",
        "# du script (deployment/) et de chaque module (backend/, frontend/) : docker.example.env.",
        "# Voir docs/deploiement.md, section 7.",
        "#",
        "# Une ligne VARIABLE=valeur par réglage, sans guillemets. Ne pas laisser de ligne « VARIABLE= »",
        "# vide : elle remplacerait la valeur prévue par l'image par du vide. Chaque conteneur reçoit",
        "# tout le fichier (sauf DHI_USERNAME et DHI_TOKEN, gardés pour le script), et ignore ce qui ne le concerne pas.",
        ""
    )
    $lines = $TEMPLATES | ForEach-Object { Get-Content $_ }
    # UTF-8 sans BOM et fins de ligne Unix : Docker lit le fichier tel quel.
    $content = (($header + $lines) -join "`n") + "`n"
    [System.IO.File]::WriteAllText((Join-Path $PWD $SETTINGS), $content)
    info "$SETTINGS créé à partir des modèles des modules : à adapter si besoin (nom de l'instance…)"
}

function check_settings {  # un docker.env d'une version précédente (PostgreSQL, Keycloak) : le dire clairement
    if (-not (setting "APP_DB_FILE")) {
        fail "$SETTINGS date d'une version précédente (il manque APP_DB_FILE). Le mettre de côté (Move-Item $SETTINGS $SETTINGS.ancien), puis relancer : le script en recrée un."
    }
}

function programmes_a_l_ecoute($port) {  # noms des programmes qui écoutent sur ce port du poste
    if (Get-Command Get-NetTCPConnection -ErrorAction SilentlyContinue) {
        # Windows
        Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue |
            Select-Object -ExpandProperty OwningProcess -Unique |
            ForEach-Object { (Get-Process -Id $_ -ErrorAction SilentlyContinue).ProcessName }
    } else {
        # macOS / Linux (PowerShell installé à part)
        lsof -nP "-iTCP:$port" -sTCP:LISTEN 2> $null | Select-Object -Skip 1 |
            ForEach-Object { ($_ -split '\s+')[0] }
    }
}

function check_port($port) {
    # Les ports tenus par Docker (ou Podman) lui-même, pour nos conteneurs actuels qui vont être
    # remplacés, ne comptent pas : sous Windows, com.docker.backend, gvproxy ou wslrelay. Un autre
    # programme (souvent l'API ou l'interface lancées sans conteneur : uv run / npm run dev, ou
    # l'autre des deux moteurs) bloque le lancement.
    $own_processes = if ($ENGINE -eq "podman") { '^(gvproxy|podman|krunkit|vfkit|wslrelay)' } else { '^(com\.docke|docker|vpnkit|wslrelay)' }
    $program = programmes_a_l_ecoute $port |
        Where-Object { $_ -and $_ -notmatch $own_processes } |
        Select-Object -First 1
    if ($program) {
        fail "Le port $port du poste est déjà utilisé par « $program » : arrêtez ce programme, ou changez le port en haut du script."
    }
    ok "Port $port disponible"
}

function login_dhi {  # connexion à dhi.io (images de base durcies), si docker.env en donne les moyens
    $user = setting "DHI_USERNAME"; $token = setting "DHI_TOKEN"
    if (-not $user -or -not $token) {
        info "DHI_USERNAME et DHI_TOKEN vides dans $SETTINGS : on compte sur un « $ENGINE login dhi.io » déjà fait"
        return
    }
    # Jeton passé par l'entrée standard : jamais sur la ligne de commande, ni à l'écran.
    $token | & $ENGINE login dhi.io --username $user --password-stdin > $null
    if ($LASTEXITCODE -ne 0) {
        fail "Connexion à dhi.io refusée pour $user : vérifier DHI_USERNAME et DHI_TOKEN dans $SETTINGS (jeton en lecture seule, voir docs/deploiement.md, section 7)."
    }
    ok "Connecté à dhi.io ($user)"
}

# Copie de docker.env pour les conteneurs, sans les réglages du script : un fichier provisoire
# (dossier temporaire de l'utilisateur), effacé à la fin du script, ou à son arrêt sur une erreur.
$script:CONTAINER_SETTINGS = ""
function prepare_container_settings {
    $script:CONTAINER_SETTINGS = (New-TemporaryFile).FullName
    $pattern = "^(" + ($SCRIPT_SETTINGS -join "|") + ")="
    $lines = Get-Content $SETTINGS | Where-Object { $_ -notmatch $pattern }
    # UTF-8 sans BOM et fins de ligne Unix : Docker lit le fichier tel quel.
    [System.IO.File]::WriteAllText($script:CONTAINER_SETTINGS, (($lines -join "`n") + "`n"))
}
function remove_container_settings {
    if ($script:CONTAINER_SETTINGS -and (Test-Path $script:CONTAINER_SETTINGS)) { Remove-Item $script:CONTAINER_SETTINGS }
}

function build_image($image, $folder) {
    & $ENGINE build -t $image $folder
    if ($LASTEXITCODE -ne 0) { fail "La fabrication de l'image $image a échoué (voir ci-dessus ; image de base refusée : connexion à dhi.io, DHI_USERNAME et DHI_TOKEN de $SETTINGS)." }
    ok "Image $image prête"
}

function remove_container($name) {
    if (exists container $name) {
        & $ENGINE rm -f $name > $null
        if ($LASTEXITCODE -ne 0) { fail "La suppression du conteneur $name a échoué." }
        ok "Conteneur $name supprimé"
    }
}

function prepare_network {
    if (exists network $NETWORK) {
        ok "Réseau $NETWORK : existe déjà"
    } else {
        & $ENGINE network create $NETWORK > $null
        if ($LASTEXITCODE -ne 0) { fail "La création du réseau $NETWORK a échoué." }
        ok "Réseau $NETWORK : créé"
    }
}

function prepare_volume {
    if ($RESET -and (exists volume $VOLUME)) {
        & $ENGINE volume rm $VOLUME > $null
        if ($LASTEXITCODE -ne 0) { fail "L'effacement du volume $VOLUME a échoué." }
        ok "Volume $VOLUME effacé (--reset) : on repart de zéro"
    }
    if (exists volume $VOLUME) {
        ok "Volume $VOLUME : existe déjà, données conservées"
    } else {
        & $ENGINE volume create $VOLUME > $null
        if ($LASTEXITCODE -ne 0) { fail "La création du volume $VOLUME a échoué." }
        ok "Volume $VOLUME : créé"
    }
}

function wait_for($what, $container, $url, $seconds = 30) {  # wait_for <ce qu'on vérifie> <conteneur dont afficher les journaux> <adresse> [secondes]
    # GET, pas HEAD : /readyz ne répond qu'au GET (HEAD donnerait 405).
    for ($i = 1; $i -le $seconds; $i++) {
        try {
            Invoke-WebRequest -Uri $url -TimeoutSec 2 -ErrorAction Stop > $null
            ok "$what répond ($url)"
            return
        } catch {
            Start-Sleep -Seconds 1
        }
    }
    Write-Host "✘ $what ne répond pas. Derniers journaux de $container :" -ForegroundColor Red
    & $ENGINE logs --tail 20 $container 2>&1 | ForEach-Object { "$_" }
    exit 1
}

function start_backend {
    # Le volume est monté sur /data : le fichier SQLite (APP_DB_FILE) y est rangé.
    & $ENGINE run -d --name $BACKEND --network $NETWORK -p "${PORT_BACKEND}:8000" `
        --env-file $script:CONTAINER_SETTINGS -v "${VOLUME}:/data" $BACKEND > $null
    if ($LASTEXITCODE -ne 0) { fail "Le lancement du conteneur $BACKEND a échoué (voir ci-dessus)." }
    wait_for "Le backend" $BACKEND "http://localhost:$PORT_BACKEND/readyz"
}

function start_frontend {
    & $ENGINE run -d --name $FRONTEND --network $NETWORK -p "${PORT_FRONTEND}:8080" `
        --env-file $script:CONTAINER_SETTINGS $FRONTEND > $null
    if ($LASTEXITCODE -ne 0) { fail "Le lancement du conteneur $FRONTEND a échoué (voir ci-dessus)." }
    wait_for "Le frontend" $FRONTEND "http://localhost:$PORT_FRONTEND/health"
    $running = & $ENGINE container inspect -f '{{.State.Running}}' $BACKEND 2> $null
    if ($running -ne "true") {
        info "Le backend ne tourne pas : l'interface s'affiche, mais « Les données sont momentanément indisponibles » (lancer : $COMMAND backend)"
    }
}

# --- Vérifications avant de commencer (rien n'est encore modifié) --------------
# Se placer à la racine du projet (le dossier au-dessus du script), d'où que l'on lance.
Set-Location (Split-Path $PSScriptRoot -Parent)   # racine du projet, d'où que l'on lance

step "Vérifications"
if (-not (Get-Command $ENGINE -CommandType Application -ErrorAction SilentlyContinue)) {
    fail "$ENGINE est introuvable : l'installer d'abord (voir docs/deploiement.md, section 7)."
}
& $ENGINE info *> $null
if ($LASTEXITCODE -ne 0) {
    if ($ENGINE -eq "podman") { fail "Podman ne répond pas : démarrez sa machine (podman machine start), puis relancez." }
    fail "Docker ne répond pas : démarrez Docker Desktop, puis relancez."
}
ok "Conteneurs fabriqués et lancés par $ENGINE"
if ((selected "backend") -and -not (Test-Path "backend/Dockerfile")) { fail "Fichier introuvable : backend/Dockerfile" }
if ((selected "frontend") -and -not (Test-Path "frontend/Dockerfile")) { fail "Fichier introuvable : frontend/Dockerfile" }
create_settings
check_settings
prepare_container_settings
if (selected "backend") { check_port $PORT_BACKEND }
if (selected "frontend") { check_port $PORT_FRONTEND }

# --- 1. Fabriquer les images (avant de toucher aux conteneurs en place) --------
step "Fabrication des images"
login_dhi
if (selected "backend") { build_image $BACKEND backend }
if (selected "frontend") { build_image $FRONTEND frontend }

# --- 2. Supprimer les conteneurs à remplacer (les données restent dans le volume) ---
step "Remplacement des conteneurs"
if (selected "frontend") { remove_container $FRONTEND }
if (selected "backend") { remove_container $BACKEND }

# --- 3. Réseau, et volume des données ------------------------------------------
step "Réseau et volume"
prepare_network
if (selected "backend") { prepare_volume }

# --- 4. Lancer (l'API d'abord : l'interface s'appuie sur elle) ------------------
step "Démarrage"
if (selected "backend") { start_backend }
if (selected "frontend") { start_frontend }

step "C'est prêt"
if (selected "frontend") { Write-Host "  Interface        http://localhost:$PORT_FRONTEND" }
if (selected "backend") { Write-Host "  API (Swagger)    http://localhost:$PORT_BACKEND/api/docs" }
if (selected "backend") { Write-Host "  Données          volume $VOLUME, fichier $(setting 'APP_DB_FILE') dans le conteneur" }
Write-Host "  Journaux         $ENGINE logs -f <conteneur>   ($BACKEND, $FRONTEND)"
remove_container_settings
