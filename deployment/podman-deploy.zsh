#!/bin/zsh
# Comme docker-deploy.zsh, mais avec Podman au lieu de Docker : mêmes modules, mêmes options,
# mêmes réglages (deployment/docker.env). Raccourci de « docker-deploy.zsh --podman ».
# Voir docs/deploiement.md, section 7.
#
# Usage, depuis n'importe quel dossier :
#   ./deployment/podman-deploy.zsh [backend|frontend] [--reset]
#
# Podman doit répondre : sur Mac (et Windows), sa machine doit tourner (podman machine start).

exec "${0:A:h}/docker-deploy.zsh" --podman "$@"
