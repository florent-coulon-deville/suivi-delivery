# Image de l'interface (serveur Next.js). Tout se fait ici : `docker build` suffit (pas d'étape à
# faire avant).
#
# Image de base : Node.js officielle, sur Alpine (Docker Hub, aucune connexion requise).
# Voir docs/deploiement.md.
#
# Deux étapes :
#   1. « build »  : installe les paquets npm aux versions exactes de package-lock.json (« npm ci »,
#                   sans exécuter leurs scripts d'installation), puis construit le site ;
#   2. l'image finale : Node.js et le site construit seulement, .next/standalone (le serveur
#                   autonome, JavaScript seul : voir next.config.ts) et .next/static. Ni les
#                   sources, ni node_modules.
# Les failles de l'image de base se corrigent en changeant sa version.
#
# Fabrication, depuis frontend/ :
#   docker build -t suivi-delivery-frontend-local .

# ---------- Étape 1 : construction du site ----------
FROM docker.io/library/node:26.12.1-alpine3.24 AS build

ENV NEXT_TELEMETRY_DISABLED=1

WORKDIR /src
# D'abord les seules listes de paquets : cette étape reste en cache tant qu'elles ne changent pas.
COPY package.json package-lock.json ./
RUN npm ci --ignore-scripts --no-audit --no-fund

# Puis les sources, et la construction (aucun téléchargement : tout est dans node_modules).
COPY . .
RUN npm run build

# OpenShift lance le conteneur avec un utilisateur au hasard, du groupe 0. Le site est lisible
# par tous ; seul le dossier du cache de Next.js doit être modifiable : on le donne au groupe 0.
# Le dossier est préparé dans le serveur autonome, copié en entier ensuite (un sous-dossier copié
# garde ses droits).
RUN mkdir -p /src/.next/standalone/.next/cache \
    && chgrp -R 0 /src/.next/standalone/.next/cache && chmod -R g=u /src/.next/standalone/.next/cache

# ---------- Étape 2 : exécution ----------
FROM docker.io/library/node:26.12.1-alpine3.24

WORKDIR /app
COPY --from=build /src/.next/standalone ./
COPY --from=build /src/.next/static ./.next/static

# Réglages par défaut dans un conteneur (modifiables au lancement, voir docs/deploiement.md).
# HOSTNAME=0.0.0.0 : écouter sur toutes les adresses du conteneur (sinon injoignable).
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=8080 \
    HOSTNAME=0.0.0.0

USER 1001
EXPOSE 8080
CMD ["node", "server.js"]
