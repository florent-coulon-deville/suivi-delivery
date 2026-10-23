# Image de l'interface (serveur Next.js). Tout se fait ici : `docker build` suffit (pas d'étape à
# faire avant).
#
# Images de base : Docker Hardened Images (dhi.io, connexion requise : `docker login dhi.io`),
# Node.js sur Alpine. Voir docs/deploiement.md.
#
# Deux étapes :
#   1. « build »  : installe les paquets npm aux versions exactes de package-lock.json (« npm ci »,
#                   sans exécuter leurs scripts d'installation), puis construit le site ;
#                   image « -dev » : elle a un shell et npm, l'image finale n'en a pas ;
#   2. l'image finale : Node.js et le site construit seulement, .next/standalone (le serveur
#                   autonome, JavaScript seul : voir next.config.ts) et .next/static. Ni les
#                   sources, ni node_modules, ni npm, ni shell.
# Les failles de l'image de base se corrigent en changeant sa version.
#
# Fabrication, depuis frontend/ :
#   docker build -t suivi-delivery-frontend-local .

# ---------- Étape 1 : construction du site ----------
FROM dhi.io/node:26.12.1-alpine3.24-dev AS build

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
# Fait ici, car l'image finale n'a pas de shell pour le faire : le dossier est préparé dans le
# serveur autonome, copié en entier ensuite (un sous-dossier copié garde ses droits).
RUN mkdir -p /src/.next/standalone/.next/cache \
    && chgrp -R 0 /src/.next/standalone/.next/cache && chmod -R g=u /src/.next/standalone/.next/cache

# ---------- Étape 2 : exécution ----------
FROM dhi.io/node:26.12.1-alpine3.24

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
