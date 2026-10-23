#!/usr/bin/env pwsh
#Requires -Version 7.0
# Fabrique les images (Docker ou Podman) et (re)lance les conteneurs sur le poste : tout, ou un module.
# Version PowerShell 7 (pwsh) de docker-deploy.zsh : même comportement.
# Voir docs/deploiement.md, section 7, et docs/postgresql.md.
#
# Usage, depuis n'importe quel dossier :
#   .\deployment\docker-deploy.ps1                     tout, dans l'ordre : postgres, liquibase, keycloak,
#                                                         backend, frontend ; données CONSERVÉES
#   .\deployment\docker-deploy.ps1 postgres            la base seule (par exemple pour l'API lancée avec « uv run »)
#   .\deployment\docker-deploy.ps1 liquibase           la structure de la base seule (après un nouveau changement)
#   .\deployment\docker-deploy.ps1 keycloak            Keycloak seul (comptes et connexion)
#   .\deployment\docker-deploy.ps1 backend             l'API seule
#   .\deployment\docker-deploy.ps1 frontend            l'interface seule
#   .\deployment\docker-deploy.ps1 --reset             tout, en EFFAÇANT les données (repartir de zéro)
#   .\deployment\docker-deploy.ps1 postgres --reset    la base seule, en effaçant les données
#   .\deployment\docker-deploy.ps1 --podman …          la même chose avec Podman au lieu de Docker
#                                                         (raccourci : .\deployment\podman-deploy.ps1 …)
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
# module (<module>/docker.example.env). Chaque conteneur y trouve tous ses réglages (pas de
# « -e »). La base y figure pour PostgreSQL (POSTGRES_*), Liquibase (LIQUIBASE_COMMAND_*),
# Keycloak (KC_DB_*) et l'API (APP_DB_*) : le script vérifie qu'ils désignent la même base, et
# que Keycloak est bien servi sous l'adresse de l'interface ; il s'arrête sinon.
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
$POSTGRES = "suivi-delivery-postgres-local"
$LIQUIBASE = "suivi-delivery-liquibase-local"
$KEYCLOAK = "suivi-delivery-keycloak-local"
$BACKEND = "suivi-delivery-backend-local"
$FRONTEND = "suivi-delivery-frontend-local"
$VOLUME = "suivi-delivery-postgres-local"            # données de PostgreSQL
$PORT_POSTGRES = 5432   # développement seulement, et sur ce poste seulement (127.0.0.1)
$PORT_KEYCLOAK = 8081   # développement seulement, ce poste seulement : console d'administration de Keycloak
$PORT_BACKEND = 8000    # développement seulement : backend testable en direct
$PORT_FRONTEND = 8080

# Le fichier des réglages, et les modèles qui servent à le créer (dans cet ordre).
$SETTINGS = "deployment/docker.env"
$TEMPLATES = "postgres/docker.example.env", "liquibase/docker.example.env", "keycloak/docker.example.env",
    "backend/docker.example.env", "frontend/docker.example.env"
# Réglages de Keycloak, obligatoires dans docker.env : un fichier qui ne les a pas est refusé.
$KEYCLOAK_SETTINGS = "KC_DB_URL", "KC_DB_USERNAME", "KC_DB_PASSWORD", "KC_HOSTNAME", "APP_ADMIN_PASSWORD",
    "APP_KEYCLOAK_CLIENT_SECRET", "APP_KEYCLOAK_URL", "KEYCLOAK_URL"

# --- Outils d'affichage --------------------------------------------------------
function step($message) { Write-Host "`n==> $message" -ForegroundColor Blue }
function ok($message) { Write-Host "✔ $message" -ForegroundColor Green }
function info($message) { Write-Host "! $message" -ForegroundColor Yellow }
function fail($message) { Write-Host "✘ $message" -ForegroundColor Red; exit 1 }

$usage = "Usage : .\deployment\docker-deploy.ps1 [postgres|liquibase|keycloak|backend|frontend] [--reset] [--podman]"

# --- Options -------------------------------------------------------------------
$TARGET = ""
$RESET = $false
$script:KEYCLOAK_IMPORTED = $false   # Keycloak vient d'importer le domaine de l'outil (compte admin créé)
$ENGINE = "docker"   # le programme qui fabrique et lance les conteneurs : docker, ou podman (--podman)
$COMMAND = ".\deployment\docker-deploy.ps1"   # pour les conseils affichés (« lancer : … »)
foreach ($option in $args) {
    switch -Exact ($option) {
        { $_ -in "postgres", "liquibase", "keycloak", "backend", "frontend" } {
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
if ($RESET -and -not (selected "postgres")) {
    fail "--reset efface les données de la base : il ne s'utilise qu'avec postgres (ou sans module)."
}
# Les réglages de la base servent à postgres, à liquibase, à keycloak et au backend.
$NEEDS_DATABASE = (selected "postgres") -or (selected "liquibase") -or (selected "keycloak") -or (selected "backend")

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
        "# de chaque module (postgres/, liquibase/, keycloak/, backend/, frontend/ : docker.example.env).",
        "# Voir docs/deploiement.md, section 7.",
        "#",
        "# Une ligne VARIABLE=valeur par réglage, sans guillemets. Ne pas laisser de ligne « VARIABLE= »",
        "# vide : elle remplacerait la valeur prévue par l'image par du vide. Chaque conteneur reçoit",
        "# tout le fichier, et ignore ce qui ne le concerne pas.",
        ""
    )
    # Les secrets, vides dans les modèles, sont tirés au hasard : le mot de passe de la base,
    # recopié aux trois endroits qui l'attendent ; celui de l'utilisateur de Keycloak dans la base ;
    # l'administrateur provisoire de Keycloak ; le compte « admin » de l'outil ; la clé du client
    # de l'API dans Keycloak (lue par Keycloak et par l'API).
    function hasard($bytes) { [Convert]::ToHexString([Security.Cryptography.RandomNumberGenerator]::GetBytes($bytes)).ToLower() }
    $password = hasard 16; $keycloakDatabase = hasard 16; $keycloakAdmin = hasard 16; $admin = hasard 8; $key = hasard 24
    $lines = $TEMPLATES | ForEach-Object { Get-Content $_ } |
        ForEach-Object { $_ -replace '^(POSTGRES_PASSWORD|LIQUIBASE_COMMAND_PASSWORD|APP_DB_PASSWORD)=$', "`$1=$password" } |
        ForEach-Object { $_ -replace '^(KC_DB_PASSWORD)=$', "`$1=$keycloakDatabase" } |
        ForEach-Object { $_ -replace '^(KC_BOOTSTRAP_ADMIN_PASSWORD)=$', "`$1=$keycloakAdmin" } |
        ForEach-Object { $_ -replace '^(APP_ADMIN_PASSWORD)=$', "`$1=$admin" } |
        ForEach-Object { $_ -replace '^(APP_KEYCLOAK_CLIENT_SECRET)=$', "`$1=$key" }
    # UTF-8 sans BOM et fins de ligne Unix : Docker lit le fichier tel quel.
    $content = (($header + $lines) -join "`n") + "`n"
    [System.IO.File]::WriteAllText((Join-Path $PWD $SETTINGS), $content)
    info "$SETTINGS créé à partir des modèles des modules, avec ses mots de passe et clés tirés au hasard : à adapter si besoin (nom de l'instance…)"
}

function check_keycloak_settings {  # un docker.env sans les réglages de Keycloak : le dire clairement
    $missing = @($KEYCLOAK_SETTINGS | Where-Object { -not (setting $_) })
    if ($missing.Count -gt 0) {
        fail "$SETTINGS date d'avant Keycloak (il manque $($missing -join ', ')). Le mettre de côté (Move-Item $SETTINGS $SETTINGS.ancien), puis relancer avec --reset : le script en recrée un, et la base repart de zéro."
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
    # programme (souvent l'API ou l'interface lancées sans conteneur : uv run / npm run dev, un
    # PostgreSQL installé sur le poste, ou l'autre des deux moteurs) bloque le lancement.
    $own_processes = if ($ENGINE -eq "podman") { '^(gvproxy|podman|krunkit|vfkit|wslrelay)' } else { '^(com\.docke|docker|vpnkit|wslrelay)' }
    $program = programmes_a_l_ecoute $port |
        Where-Object { $_ -and $_ -notmatch $own_processes } |
        Select-Object -First 1
    if ($program) {
        fail "Le port $port du poste est déjà utilisé par « $program » : arrêtez ce programme, ou changez le port en haut du script."
    }
    ok "Port $port disponible"
}

function build_image($image, $folder) {
    & $ENGINE build -t $image $folder
    if ($LASTEXITCODE -ne 0) { fail "La fabrication de l'image $image a échoué (voir ci-dessus)." }
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

function sql($request) {  # résultat brut d'une requête dans la base (psql du conteneur PostgreSQL)
    return (& $ENGINE exec $POSTGRES psql -U $DB_USER -d $DB_NAME -tAc $request 2> $null)
}

function wait_for_postgres {
    # -h 127.0.0.1 : on attend le vrai serveur (au premier lancement, PostgreSQL démarre d'abord
    # un serveur provisoire, sans réseau, le temps de créer la base).
    for ($i = 1; $i -le 30; $i++) {
        & $ENGINE exec $POSTGRES pg_isready -q -h 127.0.0.1 -U $DB_USER -d $DB_NAME *> $null
        if ($LASTEXITCODE -eq 0) {
            ok "PostgreSQL répond (localhost:$PORT_POSTGRES)"
            return
        }
        Start-Sleep -Seconds 1
    }
    Write-Host "✘ PostgreSQL ne répond pas. Derniers journaux de $POSTGRES :" -ForegroundColor Red
    & $ENGINE logs --tail 20 $POSTGRES 2>&1 | ForEach-Object { "$_" }
    exit 1
}

function start_postgres {
    # Le volume est monté sur /var/lib/postgresql : PostgreSQL 18 range ses fichiers dans un
    # sous-dossier par version (18/data), ce qui facilitera les montées de version.
    & $ENGINE run -d --name $POSTGRES --network $NETWORK -p "127.0.0.1:${PORT_POSTGRES}:5432" `
        --env-file $SETTINGS -v "${VOLUME}:/var/lib/postgresql" $POSTGRES > $null
    if ($LASTEXITCODE -ne 0) { fail "Le lancement du conteneur $POSTGRES a échoué (voir ci-dessus)." }
    wait_for_postgres
}

function ensure_database_running {  # pour liquibase et backend lancés seuls : la base doit tourner
    if (-not (exists container $POSTGRES)) { fail "La base ne tourne pas : lancer d'abord $COMMAND postgres" }
    if ((& $ENGINE container inspect -f '{{.State.Running}}' $POSTGRES) -ne "true") {
        & $ENGINE start $POSTGRES > $null
        if ($LASTEXITCODE -ne 0) { fail "Le redémarrage du conteneur $POSTGRES a échoué." }
        ok "Conteneur $POSTGRES redémarré"
    }
    wait_for_postgres
}

function check_schema {  # la base a-t-elle été préparée pour cette version (schéma de nos tables) ?
    if (-not (sql "select 1 from pg_namespace where nspname = '$DB_SCHEMA'")) {
        fail "La base n'a pas de schéma « $DB_SCHEMA » : elle date d'avant Keycloak. Relancer avec --reset (ses données seront effacées)."
    }
}

function apply_structure {
    # Liquibase reçoit l'adresse de la base, l'utilisateur et le mot de passe, déduits de POSTGRES_*.
    & $ENGINE run --rm --network $NETWORK --env-file $SETTINGS $LIQUIBASE update
    if ($LASTEXITCODE -ne 0) { fail "Liquibase n'a pas pu appliquer la structure de la base (voir ci-dessus)." }
    ok "Structure de la base à jour (Liquibase)"
}

function start_keycloak {
    # Port du poste : la console d'administration de Keycloak (développement). Les pages de
    # connexion, elles, passent par l'interface (http://localhost:$PORT_FRONTEND/auth).
    & $ENGINE run -d --name $KEYCLOAK --network $NETWORK -p "127.0.0.1:${PORT_KEYCLOAK}:8080" `
        --env-file $SETTINGS $KEYCLOAK > $null
    if ($LASTEXITCODE -ne 0) { fail "Le lancement du conteneur $KEYCLOAK a échoué (voir ci-dessus)." }
    # Le premier démarrage prépare ses tables et importe le domaine : jusqu'à une ou deux minutes.
    wait_for "Keycloak" $KEYCLOAK "http://localhost:$PORT_KEYCLOAK/auth/realms/suivi-delivery/.well-known/openid-configuration" 180
    # Domaine importé à l'instant (base neuve) : le compte « admin » de l'outil vient d'être créé.
    # (Keycloak écrit ses journaux sur les deux sorties : d'où « 2>&1 ».)
    $logs = (& $ENGINE logs $KEYCLOAK 2>&1 | ForEach-Object { "$_" }) -join "`n"
    if ($logs -match "Realm 'suivi-delivery' imported") { $script:KEYCLOAK_IMPORTED = $true }
}

function start_backend {
    & $ENGINE run -d --name $BACKEND --network $NETWORK -p "${PORT_BACKEND}:8000" `
        --env-file $SETTINGS $BACKEND > $null
    if ($LASTEXITCODE -ne 0) { fail "Le lancement du conteneur $BACKEND a échoué (voir ci-dessus)." }
    wait_for "Le backend" $BACKEND "http://localhost:$PORT_BACKEND/readyz"
    if ((& $ENGINE container inspect -f '{{.State.Running}}' $KEYCLOAK 2> $null) -ne "true") {
        info "Keycloak ne tourne pas : l'API refusera les jetons (lancer : $COMMAND keycloak)"
    }
}

function start_frontend {
    & $ENGINE run -d --name $FRONTEND --network $NETWORK -p "${PORT_FRONTEND}:8080" `
        --env-file $SETTINGS $FRONTEND > $null
    if ($LASTEXITCODE -ne 0) { fail "Le lancement du conteneur $FRONTEND a échoué (voir ci-dessus)." }
    wait_for "Le frontend" $FRONTEND "http://localhost:$PORT_FRONTEND/health"
    wait_for "La page de connexion" $FRONTEND "http://localhost:$PORT_FRONTEND/login"
    if ((& $ENGINE container inspect -f '{{.State.Running}}' $KEYCLOAK 2> $null) -eq "true") {
        wait_for "Keycloak, servi par l'interface" $FRONTEND `
            "http://localhost:$PORT_FRONTEND/auth/realms/suivi-delivery/.well-known/openid-configuration"
    } else {
        info "Keycloak ne tourne pas : impossible de se connecter (lancer : $COMMAND keycloak)"
    }
    $running = & $ENGINE container inspect -f '{{.State.Running}}' $BACKEND 2> $null
    if ($running -ne "true") {
        info "Le backend ne tourne pas : l'interface s'affiche, mais « Les données sont momentanément indisponibles » (lancer : $COMMAND backend)"
    }
}

function show_admin_account {
    if ($script:KEYCLOAK_IMPORTED) {
        Write-Host "  Compte admin     créé à l'instant. Identifiant : admin   Mot de passe : $(setting 'APP_ADMIN_PASSWORD')" -ForegroundColor Yellow
        Write-Host "                   (APP_ADMIN_PASSWORD de $SETTINGS ; le changer ensuite dans « Mon compte »)" -ForegroundColor Yellow
    } else {
        Write-Host "  Compte admin     créé lors d'un lancement précédent : identifiant admin, mot de passe initial"
        Write-Host "                   APP_ADMIN_PASSWORD de $SETTINGS (sauf s'il a été changé depuis dans « Mon compte »)"
    }
    Write-Host "  Console Keycloak http://localhost:$PORT_KEYCLOAK/auth/admin   (KC_BOOTSTRAP_ADMIN_* de $SETTINGS ; ce poste seulement)"
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
if ((selected "postgres") -and -not (Test-Path "postgres/Dockerfile")) { fail "Fichier introuvable : postgres/Dockerfile" }
if ((selected "liquibase") -and -not (Test-Path "liquibase/Dockerfile")) { fail "Fichier introuvable : liquibase/Dockerfile" }
if ((selected "keycloak") -and -not (Test-Path "keycloak/Dockerfile")) { fail "Fichier introuvable : keycloak/Dockerfile" }
if ((selected "backend") -and -not (Test-Path "backend/Dockerfile")) { fail "Fichier introuvable : backend/Dockerfile" }
if ((selected "frontend") -and -not (Test-Path "frontend/Dockerfile")) { fail "Fichier introuvable : frontend/Dockerfile" }
create_settings
check_keycloak_settings
if ($NEEDS_DATABASE) {
    # La base de référence : POSTGRES_*.
    $DB_NAME = setting "POSTGRES_DB"; $DB_USER = setting "POSTGRES_USER"; $DB_PASSWORD = setting "POSTGRES_PASSWORD"
    if (-not ($DB_NAME -and $DB_USER -and $DB_PASSWORD)) {
        fail "POSTGRES_DB, POSTGRES_USER et POSTGRES_PASSWORD doivent être renseignés dans $SETTINGS"
    }
    $DB_SCHEMA = setting "APP_DB_SCHEMA"; if (-not $DB_SCHEMA) { $DB_SCHEMA = "suivi_delivery" }
    # Règle d'or : rien d'incohérent. Liquibase, Keycloak et l'API doivent viser cette base, avec ce
    # compte (Keycloak : le sien), et le même schéma pour nos tables.
    $expected_values = [ordered]@{}
    if (selected "liquibase") {
        $expected_values["LIQUIBASE_COMMAND_URL"] = "jdbc:postgresql://${POSTGRES}:5432/${DB_NAME}?currentSchema=$DB_SCHEMA"
        $expected_values["LIQUIBASE_COMMAND_USERNAME"] = $DB_USER
        $expected_values["LIQUIBASE_COMMAND_PASSWORD"] = $DB_PASSWORD
    }
    if (selected "keycloak") {
        $expected_values["KC_DB_URL"] = "jdbc:postgresql://${POSTGRES}:5432/$DB_NAME"
    }
    if (selected "backend") {
        $expected_values["APP_DB_HOST"] = $POSTGRES
        $expected_values["APP_DB_PORT"] = "5432"
        $expected_values["APP_DB_NAME"] = $DB_NAME
        $expected_values["APP_DB_USER"] = $DB_USER
        $expected_values["APP_DB_PASSWORD"] = $DB_PASSWORD
    }
    foreach ($variable in $expected_values.Keys) {
        if ((setting $variable) -cne $expected_values[$variable]) {
            $expected = if ($variable -like "*PASSWORD") { "la même valeur que POSTGRES_PASSWORD" } else { $expected_values[$variable] }  # jamais affiché
            fail "$variable de $SETTINGS ne correspond pas à la base : attendu $expected"
        }
    }
    if ($expected_values.Count -gt 0) { ok "Liquibase, Keycloak et l'API visent bien la base $DB_NAME ($POSTGRES)" }
}
# Keycloak est servi par l'interface, sous /auth : son adresse publique en découle, et l'API comme
# l'interface le joignent par son conteneur.
$FRONTEND_URL = setting "APP_FRONTEND_URL"
$urls = [ordered]@{
    KC_HOSTNAME      = "$FRONTEND_URL/auth"
    APP_KEYCLOAK_URL = "http://${KEYCLOAK}:8080/auth"
    KEYCLOAK_URL     = "http://${KEYCLOAK}:8080/auth"
}
foreach ($variable in $urls.Keys) {
    if ((setting $variable) -cne $urls[$variable]) { fail "$variable de $SETTINGS ne correspond pas : attendu $($urls[$variable])" }
}
ok "Keycloak servi sous $FRONTEND_URL/auth, joint par l'API et l'interface sur $KEYCLOAK"
if (selected "postgres") { check_port $PORT_POSTGRES }
if (selected "keycloak") { check_port $PORT_KEYCLOAK }
if (selected "backend") { check_port $PORT_BACKEND }
if (selected "frontend") { check_port $PORT_FRONTEND }

# --- 1. Fabriquer les images (avant de toucher aux conteneurs en place) --------
step "Fabrication des images"
if (selected "postgres") { build_image $POSTGRES postgres }
if (selected "liquibase") { build_image $LIQUIBASE liquibase }
if (selected "keycloak") { build_image $KEYCLOAK keycloak }
if (selected "backend") { build_image $BACKEND backend }
if (selected "frontend") { build_image $FRONTEND frontend }

# --- 2. Supprimer les conteneurs à remplacer (les données de la base restent dans son volume) ---
step "Remplacement des conteneurs"
if (selected "frontend") { remove_container $FRONTEND }
if (selected "backend") { remove_container $BACKEND }
if (selected "keycloak") { remove_container $KEYCLOAK }
if (selected "postgres") { remove_container $POSTGRES }

# --- 3. Réseau, et volume des données (base) ------------------------------------
step "Réseau et volume"
prepare_network
if (selected "postgres") { prepare_volume }

# --- 4. Lancer (dans l'ordre : chacun s'appuie sur le précédent) -----------------
step "Démarrage"
if (selected "postgres") { start_postgres } elseif ($NEEDS_DATABASE) { ensure_database_running }
if ($NEEDS_DATABASE) { check_schema }
if (selected "liquibase") { apply_structure }
if (selected "keycloak") { start_keycloak }
if (selected "backend") { start_backend }
if (selected "frontend") { start_frontend }

step "C'est prêt"
if (selected "frontend") { Write-Host "  Interface        http://localhost:$PORT_FRONTEND" }
if (selected "backend") { Write-Host "  API (Swagger)    http://localhost:$PORT_BACKEND/api/docs" }
if ($NEEDS_DATABASE) { Write-Host "  Base             localhost:$PORT_POSTGRES   base $DB_NAME, utilisateur $DB_USER (mot de passe : $SETTINGS)" }
if (selected "keycloak") { show_admin_account }
Write-Host "  Journaux         $ENGINE logs -f <conteneur>   ($POSTGRES, $KEYCLOAK, $BACKEND, $FRONTEND)"
