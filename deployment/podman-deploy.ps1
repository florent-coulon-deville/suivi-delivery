#!/usr/bin/env pwsh
#Requires -Version 7.0
# Comme docker-deploy.ps1, mais avec Podman au lieu de Docker : mêmes modules, mêmes options,
# mêmes réglages (deployment/docker.env). Raccourci de « docker-deploy.ps1 --podman ».
# Version PowerShell 7 (pwsh) de podman-deploy.zsh. Voir docs/deploiement.md, section 7.
#
# Usage, depuis n'importe quel dossier :
#   .\deployment\podman-deploy.ps1 [postgres|liquibase|keycloak|backend|frontend] [--reset]
#
# Podman doit répondre : sur Windows (et Mac), sa machine doit tourner (podman machine start).

& (Join-Path $PSScriptRoot "docker-deploy.ps1") --podman @args
exit $LASTEXITCODE
