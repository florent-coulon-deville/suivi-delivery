# Keycloak : les comptes et la connexion

L'outil ne gère pas lui-même les comptes, les mots de passe ni les jetons : c'est **Keycloak** qui s'en charge. Keycloak est un logiciel libre de Red Hat, très répandu, qui sert de « serveur de connexion ». Il suit les normes OAuth 2.1 et OpenID Connect, qui décrivent comment une application obtient la preuve qu'une personne est connectée.

Pour les utilisateurs, la page de connexion **ressemble à l'outil** et a la même adresse que lui : on ne voit pas qu'on passe par Keycloak.

Deux mots à connaître :

- **jeton** (*token*) : un petit texte signé par Keycloak, qui prouve qui on est. On le joint à chaque appel de l'API ;
- **PKCE** : une protection de la connexion par le navigateur, qui empêche qu'un code de connexion volé serve à quelqu'un d'autre.

## 1. Qui fait quoi

| Brique | Rôle |
| --- | --- |
| **Keycloak** (module `keycloak/`) | garde les comptes et les mots de passe, affiche la page de connexion, fabrique et renouvelle les jetons, bloque un compte après 5 échecs (15 minutes) |
| **Interface** (Next.js) | envoie la personne sur la page de connexion, échange le code reçu contre les jetons, les garde dans des cookies protégés ; **relaie les pages de Keycloak** sous `/auth` (même adresse que l'outil) |
| **API** | vérifie chaque jeton (signature de Keycloak, destinataire, expiration), y lit le rôle ; gère les comptes **dans Keycloak** pour l'écran Comptes (`/api/accounts`) |
| **Base PostgreSQL** | une seule base : nos tables dans le schéma `suivi_delivery`, celles de Keycloak dans le schéma `keycloak`, avec son propre utilisateur (qui n'a accès qu'à son schéma) |

```
navigateur ──► interface (https://outil/…)          pages de l'outil
           └─► interface (https://outil/auth/…) ──► Keycloak (adresse interne)   pages de connexion
interface ──(jeton)──► API ──(clés de signature, gestion des comptes)──► Keycloak
```

## 2. Le domaine « suivi-delivery »

Keycloak range tout dans un « domaine » (realm). Celui de l'outil est décrit dans `keycloak/import/suivi-delivery.json`, **importé au premier démarrage** (une base neuve). Les valeurs `${…}` y sont remplacées par les variables d'environnement du même nom.

**Rôles** (rôles du domaine, chacun comprend le précédent) : `VIEWER` < `EDITOR` < `ADMIN`. Un compte n'en a qu'un ; sans rôle, il ne peut rien faire dans l'outil (403).

**Clients** (les applications qui demandent une connexion) :

| Client | Sorte | Sert à |
| --- | --- | --- |
| `suivi-delivery-frontend` | public, PKCE | la connexion des personnes dans l'interface |
| `suivi-delivery-tools` | public, PKCE, connexion d'un appareil | Bruno, Swagger, et les scripts d'une personne (jeton hors ligne) |
| `suivi-delivery-api` | confidentiel (clé `APP_KEYCLOAK_CLIENT_SECRET`) | l'API, qui gère les comptes pour l'écran Comptes |
| un client par **programme** | confidentiel (sa clé) | un programme (outil de déploiement…), créé depuis l'écran Comptes |

Les jetons des clients de l'outil portent le destinataire `suivi-delivery-api` : l'API refuse tout autre jeton, même venu du même Keycloak.

**Compte `admin`** : créé à l'import, avec le mot de passe `APP_ADMIN_PASSWORD` et le rôle `ADMIN`. Le changer ensuite dans « Mon compte ».

**Durées** :

| Quoi | Durée |
| --- | --- |
| jeton d'accès | 5 minutes (renouvelé sans que la personne le voie) |
| session | 24 h sans servir, 7 jours au plus |
| jeton hors ligne (scripts) | 30 jours sans servir, 1 an au plus |

Un rôle retiré ou un compte désactivé prend donc effet au plus tard 5 minutes après.

> Changer `keycloak/import/suivi-delivery.json` ne change pas un domaine déjà importé (l'import n'a lieu qu'une fois). Sur le poste : `./deployment/docker-deploy.zsh --reset`. Sur un cluster : faire le changement dans la console de Keycloak (voir § 6), ou repartir d'une base neuve.

## 3. Les pages de connexion à l'allure de l'outil

Deux choses font qu'on ne voit pas Keycloak :

1. **Le thème `suivi-delivery`** (`keycloak/themes/suivi-delivery/login/`) : la même barre du haut, la même carte de connexion, les mêmes couleurs que l'interface, et le bandeau de l'instance (`INSTANCE_NAME`).
   - Les couleurs (`resources/css/suivi-delivery.css`, recopiées de `frontend/app/styles.css`) sont écrites dans chaque page. Ainsi, un navigateur ne peut pas garder une ancienne version en cache.
   - Le thème clair ou sombre choisi dans « Mon compte » est recopié par l'interface dans le cookie `sd_theme_auth`, que la page lit.
2. **La même adresse** : Keycloak est servi sous `<url de l'frontend>/auth`.
   - Le proxy de l'interface (`frontend/proxy.ts`) relaie ces adresses vers Keycloak, seulement pour le domaine de l'outil (jamais pour sa console d'administration).
   - Keycloak connaît cette adresse publique par `KC_HOSTNAME=<APP_FRONTEND_URL>/auth`. L'API et l'interface, elles, lui parlent par son adresse interne.

Pages réécrites : connexion (`login.ftl`) et choix d'un nouveau mot de passe (`login-update-password.ftl`). Les autres (page expirée, erreur…) gardent celles de Keycloak, dans le cadre de l'outil.

## 4. Les parcours

- **Se connecter** : l'interface envoie sur `/auth/realms/suivi-delivery/protocol/openid-connect/auth` (PKCE), Keycloak renvoie sur `/login/callback` avec un code, échangé contre les jetons.
- **Première connexion** : l'administrateur a donné un mot de passe **provisoire** ; Keycloak demande d'en choisir un nouveau.
- **Changer son mot de passe** : « Mon compte » → « Changer mon mot de passe » envoie sur Keycloak avec l'action `UPDATE_PASSWORD` (il redemande le mot de passe actuel si la connexion date un peu), puis revient sur « Mon compte » avec le résultat.
- **Se déconnecter** : l'interface ferme la session chez Keycloak : la connexion suivante redemande le mot de passe.
- **Mot de passe oublié** : pas de lien « mot de passe oublié » (pas d'envoi de courriel) : l'administrateur donne un nouveau mot de passe provisoire dans l'écran Comptes.

## 5. Appeler l'API sans l'interface

Il y a trois façons de faire, toutes fournies par Keycloak :

| Qui | Comment | Détail |
| --- | --- | --- |
| une personne, **à la main** (Bruno, Swagger) | connexion sur la page de l'outil, client `suivi-delivery-tools` | la collection Bruno (`bruno/`) et Swagger sont déjà réglés |
| une personne, **dans un script** | un **jeton hors ligne**, obtenu une fois par une connexion dans le navigateur | `uv run python -m scripts.login` (dans `backend/`) l'affiche ; le script l'échange ensuite à chaque lancement contre un jeton d'accès (variable `API_OFFLINE_TOKEN`). « Mon compte » → « Fermer mes accès par script » les annule tous |
| un **programme** | son identifiant et sa clé (client credentials) | créé dans l'écran Comptes (onglet Programmes), clé affichée une seule fois ; variables `API_CLIENT_ID` et `API_CLIENT_SECRET` de `scripts/login.py` |

Adresse des jetons, pour un programme : `<url de l'frontend>/auth/realms/suivi-delivery/protocol/openid-connect/token`.

## 6. La console d'administration de Keycloak

Rarement utile (l'écran Comptes de l'outil suffit au quotidien). Elle n'est **jamais exposée** :

- sur le poste : `http://localhost:8081/auth/admin`, avec `KC_BOOTSTRAP_ADMIN_USERNAME` / `KC_BOOTSTRAP_ADMIN_PASSWORD` de `deployment/docker.env` ;
- sur un cluster : `kubectl port-forward service/<installation>-keycloak 8081:8080`, puis la même adresse (mot de passe : `KC_BOOTSTRAP_ADMIN_PASSWORD` du Secret `<installation>-application`).

C'est un administrateur **provisoire** de Keycloak (domaine `master`), pas un compte de l'outil.

**Pourquoi la console a sa propre adresse.**

- La console se connecte par le domaine d'administration (`master`).
- Par défaut, ce domaine annoncerait l'adresse publique (`<frontend>/auth`). Mais l'interface refuse de relayer ce domaine (seul celui de l'outil passe) : la console resterait blanche.
- Au démarrage, le script `keycloak/start.sh` de l'image donne donc au domaine `master` l'adresse de la console, `KC_HOSTNAME_ADMIN`. C'est `http://localhost:8081/auth` sur le poste comme sur un cluster (par port-forward ; réglage `keycloak.consoleUrl` du chart).
- C'est refait à chaque démarrage, avec l'administrateur provisoire. S'il a été supprimé, la console n'est plus réglée (Keycloak, lui, marche normalement).

**Ne jamais ouvrir de Route ni d'Ingress vers la console** sur OpenShift : le chart n'en crée pas, et c'est voulu.

## 7. Réglages

| Variable | Qui la lit | Rôle |
| --- | --- | --- |
| `KC_DB_URL`, `KC_DB_USERNAME`, `KC_DB_PASSWORD`, `KC_DB_SCHEMA` | Keycloak (et l'image PostgreSQL, qui crée l'utilisateur et le schéma) | sa base |
| `KC_HOSTNAME` | Keycloak | son adresse publique : `<APP_FRONTEND_URL>/auth` |
| `KC_HOSTNAME_ADMIN` | Keycloak (`start.sh`) | l'adresse de sa console (poste et cluster : `http://localhost:8081/auth`) |
| `KC_BOOTSTRAP_ADMIN_USERNAME`, `KC_BOOTSTRAP_ADMIN_PASSWORD` | Keycloak | administrateur provisoire de la console |
| `APP_ADMIN_PASSWORD` | Keycloak (import) | mot de passe initial du compte `admin` de l'outil |
| `APP_KEYCLOAK_CLIENT_SECRET` | Keycloak (import), API | clé du client de l'API |
| `APP_KEYCLOAK_URL`, `APP_KEYCLOAK_REALM` | API | adresse interne de Keycloak, domaine |
| `KEYCLOAK_URL`, `KEYCLOAK_REALM` | interface | adresse interne de Keycloak, domaine |
| `APP_FRONTEND_URL` | tous | adresse publique de l'interface (et de Keycloak, sous `/auth`) |

`docker-deploy.zsh` vérifie que ces adresses se correspondent, et tire les secrets au hasard. Sur un cluster, le chart Helm les règle tout seul (`docs/deploiement.md` § 9).

## 8. Base fournie (hors base intégrée)

L'équipe des bases de données crée, dans la base de l'outil :

```sql
create schema suivi_delivery authorization suivi_delivery;
create role keycloak login password '…';
create schema keycloak authorization keycloak;
alter role keycloak set search_path = keycloak;
```

puis donne les deux mots de passe (`database.password`, `database.keycloakPassword` de `values-secret.yaml`).

## 9. Version

Keycloak **26.7.4**, image durcie de Docker (`dhi.io/keycloak:26.7.4-debian13`, Docker Hardened Image). Version figée dans `keycloak/Dockerfile` (l'étiquette `:26` suivrait toute la série 26.x) ; dans cette image, le dossier de travail `/opt/keycloak/data` est donné au groupe 0 à la fabrication (sinon Keycloak ne peut pas compresser les pages de la console, qui reste blanche) ; comme toujours, jamais une version de moins de deux semaines.
