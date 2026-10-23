# Chart Helm « Suivi de la delivery »

Installe l'outil de suivi des mises en production : l'**API** (backend), avec ses données dans un fichier **SQLite** sur un disque, et l'**interface** (frontend). Cible : **OpenShift** ; fonctionne aussi sur un Kubernetes classique (kind pour les essais).

**Pas de connexion ni de rôles** dans cette version : tout le monde peut tout lire et tout saisir. Réserver l'interface à un réseau de confiance.

## Ce qui est installé

| Objet | Rôle |
| --- | --- |
| Deployment `<installation>-backend` | l'API, **un seul exemplaire** (`backend.replicas` : 0 ou 1), mise à jour en `Recreate` (l'ancien pod s'arrête avant que le nouveau démarre : jamais deux API sur le même fichier) ; probes `/startupz`, `/readyz`, `/livez`. L'API crée elle-même ses tables au premier démarrage |
| PersistentVolumeClaim `<installation>-data` | le disque des données (fichier SQLite, monté sur `/data`), `backend.storage.size` ; **conservé** par `helm uninstall` |
| Deployment `<installation>-frontend` | l'interface (serveur Next.js) ; probe `/health` |
| Services `-backend`, `-frontend` | adresses internes ; l'API n'est jamais exposée à l'extérieur |
| Route (OpenShift) **ou** Ingress | l'adresse publique de l'interface, en HTTPS. La Route n'est créée que sur OpenShift |
| Secret `<installation>-registry` | accès à un registre d'images privé, seulement si values-secret.yaml en donne un (inutile pour ghcr.io : images publiques) |
| NetworkPolicy | seule l'interface (et le test Helm) peut joindre l'API |
| ServiceAccount | sans droits, sans jeton monté : l'application ne parle pas à Kubernetes |

Tous les conteneurs tournent **sans droits administrateur**, sans numéro d'utilisateur imposé sur OpenShift (il en choisit un ; ailleurs, celui de l'image, 1001), avec un système de fichiers en lecture seule (sauf le disque des données), et des ressources (processeur, mémoire, disque temporaire) réservées et plafonnées.

## Version

**Le chart suit la version de l'application** : `version` et `appVersion` de `Chart.yaml` sont égales, et égales aux versions de `backend/pyproject.toml` et `frontend/package.json` (vérifié par la CI). Par défaut, le chart déploie les images de sa propre version : `suivi-delivery-backend:<version>` et `suivi-delivery-frontend:<version>`.

Ces images sont publiées par la CI à la sortie de chaque version (étiquette Git `vX.Y.Z`), dans `ghcr.io/florent-coulon-deville/` : voir `docs/ci.md` § 5. C'est là que le chart les cherche par défaut (`images.registry: ghcr.io/florent-coulon-deville`, placé devant le nom de chaque image). Si le dépôt est privé, donner l'accès au registre dans `values-secret.yaml` (`registry`). Pour un autre registre : changer seulement `images.registry`. Vide : noms courts, pour des images chargées à la main sur le nœud (kind).

## Fichiers de réglages

| Fichier | Publié | Contenu |
| --- | --- | --- |
| `values.yaml` | oui | tous les réglages **non secrets**, commentés : images, nom de l'instance, disque des données, Route, ressources… |
| `values-secret.yaml` | **jamais** (ignoré par Git et par Helm) | le seul **secret** possible : l'accès à un registre d'images privé (vide pour ghcr.io). Modèle : `values-secret.example.yaml` |
| `values-<instance>.yaml` | **non** (ignoré par Git) ; le modèle `values-<instance>.example.yaml` oui | les réglages **propres à une instance** (nom affiché, couleur, Route…), seulement ce qui diffère de `values.yaml`. Exemple : `values-crc.example.yaml` (OpenShift Local), à copier en `values-crc.yaml` |

Helm applique les fichiers dans l'ordre (`values.yaml`, puis chaque `-f`) : le dernier l'emporte.

Chaque réglage est vérifié par `values.schema.json` : un réglage inconnu, du mauvais type, une étiquette `latest` ou plus d'un exemplaire de l'API arrêtent l'installation avec un message clair.

## Installer

### OpenShift

Guide complet, étape par étape : `docs/deploiement.md` § 9.1. En bref :

```bash
helm upgrade --install suivi-delivery ./helm/suivi-delivery -n <espace-de-noms> \
  -f helm/suivi-delivery/values-<instance>.yaml
helm test suivi-delivery -n <espace-de-noms>
```

**Une version publiée** : seules les images sont publiées (`ghcr.io/florent-coulon-deville/suivi-delivery-*:<version>`), pas le chart. On prend le chart dans le dépôt Git, à l'étiquette de la version :

```bash
git clone --branch vX.Y.Z --depth 1 https://github.com/florent-coulon-deville/suivi-delivery.git suivi-delivery-X.Y.Z
helm upgrade --install suivi-delivery ./suivi-delivery-X.Y.Z/helm/suivi-delivery \
  -n <espace-de-noms> -f values-<instance>.yaml
```

### kind (essais sur son poste)

Le script `k8s-deploy.zsh`, dans le dossier `deployment/` du projet, fait tout : `./deployment/k8s-deploy.zsh --context kind-suivi-delivery` crée le cluster kind s'il manque, y charge les images du poste, installe le chart et lance `helm test`. Le même script installe aussi sur OpenShift ou tout autre cluster (contexte kubectl). Voir `docs/deploiement.md` § 9.2.

## Vérification

```bash
helm lint helm/suivi-delivery --strict
docker run --rm -v "$PWD/helm/suivi-delivery:/charts/suivi-delivery:ro" quay.io/redhat-certification/chart-verifier:1.16.0 \
  verify --set profile.vendortype=developer-console /charts/suivi-delivery
```

La CI fait la même vérification (chart-verifier de Red Hat, profil `developer-console`) : voir `docs/ci.md`.

## Désinstaller

```bash
helm uninstall suivi-delivery -n <espace-de-noms>
```

Le disque des données est **conservé** (pour le supprimer vraiment, et repartir de zéro : `kubectl delete pvc <installation>-data`).
