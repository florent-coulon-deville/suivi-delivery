# Interface web (frontend)

## 1. Les outils

| Outil | Rôle |
| --- | --- |
| **React** | construit l'écran à partir de petits blocs (« composants ») : un tableau, une fiche, une ligne… Quand les données changent, React redessine seulement ce qui a changé. |
| **Next.js** | le cadre autour de React : il fait tourner un **serveur** (Node.js) qui lit l'API, prépare les pages et ne les envoie au navigateur qu'une fois prêtes. Il sert aussi le site pendant le développement (`npm run dev`) et le construit pour la mise en ligne (`npm run build`). |
| **TypeScript** | du JavaScript avec des **types** : les erreurs (champ qui n'existe pas, mauvais type) sont repérées avant l'exécution, comme `ty` le fait pour le Python. `npm run typecheck` vérifie tout le code. |
| **npm** | installe React, Next.js et TypeScript (dans `frontend/node_modules/`), comme `uv` pour le Python. |

### Qui parle à qui

```Plaintext
navigateur ──► serveur Next.js (PORT) ──► API (API_URL)
                       └── /auth/… ──────► Keycloak (KEYCLOAK_URL) : pages de connexion, jetons
```

- **Le navigateur ne parle jamais à l'API.** Il ne connaît ni son adresse ni ses routes : il reçoit des pages déjà prêtes.
- **Le navigateur ne parle pas directement à Keycloak** non plus : les pages de connexion de Keycloak passent par le serveur Next.js, sous `/auth`.
- **Le serveur Next.js lit l'API** (`lib/api.ts`), fait les rapprochements (`lib/state.ts`) et envoie au navigateur la page, plus la seule partie interactive dont elle a besoin (filtres, panneaux, formulaires).
- **Les enregistrements** de l'espace Saisie passent aussi par le serveur (`app/edit/actions.ts`, des « Server Actions » : des fonctions du serveur que le formulaire appelle comme des fonctions ordinaires).
- **Chaque page ne reçoit que son propre code**, et seulement si le rôle de l'utilisateur y donne droit : la page « Ce qui tourne » ne contient rien de l'espace Saisie, et un compte en consultation ne reçoit ni les données ni le code de la Saisie.
- **Les jetons restent sur le serveur.** Le navigateur n'a que deux cookies protégés (voir § 2 bis), illisibles pour le code de la page.

L'interface n'a **aucune donnée propre** : tout vient de l'API.

## 2. Lancer l'interface

Il faut **Node.js 26** et npm (sur Mac, par exemple avec MacPorts : `sudo port install nodejs26 npm11`), et deux terminaux.

```bash
# Terminal 1 : l'API (depuis backend/)
uv run python -m app --reload
uv run python scripts/load_demo.py      # facultatif : charge des données de démonstration

# Terminal 2 : l'interface (depuis frontend/)
npm install                                # la première fois, ou après une mise à jour des dépendances
npm run dev
```

Ouvre ensuite **<http://localhost:5173>**.

**Connexion (Keycloak)** : il faut Keycloak (`./deployment/docker-deploy.zsh keycloak`, voir [keycloak.md](keycloak.md)).

- Keycloak doit connaître l'adresse de l'interface : `KC_HOSTNAME=<url>/auth`, et l'adresse de retour du client `suivi-delivery-frontend` (importée au premier démarrage avec `APP_FRONTEND_URL`).
- Avec `npm run dev` sur le port 5173, il faut donc un Keycloak réglé pour `http://localhost:5173` : changer `APP_FRONTEND_URL` et `KC_HOSTNAME` dans `docker.env`, puis `--reset`.
- Le plus simple reste d'essayer l'interface dans Docker (`./deployment/docker-deploy.zsh`), où tout est déjà réglé.

| Commande (depuis `frontend/`) | Rôle |
| --- | --- |
| `npm run dev` | site de développement, rechargé à chaque modification |
| `npm run typecheck` | vérifie les types de tout le code (doit passer avant chaque commit) |
| `npm run build` | construit le site pour la mise en ligne (vérifie aussi les types) |

**Réglages** (adresse de l'API, nom de l'instance affiché en bandeau) : variables d'environnement ou fichier `frontend/.env`, voir [deploiement.md](deploiement.md). Par exemple `INSTANCE_NAME=recette npm run dev` affiche un bandeau orange « Instance : recette ». Le **port** se donne au lancement (`PORT=3000 npm run dev`) : il est lu avant le fichier `.env`.

**Première connexion** : identifiant `admin`, avec le mot de passe `APP_ADMIN_PASSWORD` de `deployment/docker.env` (affiché par `docker-deploy.zsh` quand Keycloak vient de créer le compte). Le script de démo, lui, se connecte par Keycloak : il affiche une adresse et un code à ouvrir dans le navigateur (ou utilise un compte programme, voir [deploiement.md § 2](deploiement.md#2-les-réglages)).

Avec une base PostgreSQL (`./deployment/docker-deploy.zsh`, voir [postgresql.md](postgresql.md)), les données de l'API sont conservées : inutile de relancer `load_demo.py` après un redémarrage. Pour repartir d'une démonstration propre : `./deployment/docker-deploy.zsh --reset`, puis relancer le script. Sans base (`APP_DB_HOST` absente), l'API garde ses données en mémoire : elles sont perdues à chaque arrêt.

## 2 bis. Connexion, session et rôles

| Étape | Ce qui se passe |
| --- | --- |
| **Connexion** (`/login`) | par **Keycloak**, selon la norme **OAuth 2.1** (authorization code + PKCE). L'interface est le client `suivi-delivery-frontend` de Keycloak. Le parcours, pas à pas, est décrit juste sous ce tableau. |
| **Page de connexion** (Keycloak, sous `/auth`) | elle a **l'allure de l'outil** (thème `keycloak/themes/suivi-delivery`) et la **même adresse** : `proxy.ts` relaie `/auth/realms/suivi-delivery/…` et `/auth/resources/…` vers Keycloak (jamais sa console d'administration). On ne voit pas qu'on passe par Keycloak. Le thème clair ou sombre choisi est recopié pour elle dans le cookie `sd_theme_auth`. Voir [keycloak.md § 3](keycloak.md#3-les-pages-de-connexion-à-lallure-de-loutil). |
| **Chaque page** | `proxy.ts` passe avant : jeton d'accès valable → on continue ; bientôt expiré → nouvelle paire de jetons demandée à Keycloak, sans que l'utilisateur ne voie rien ; pas de session → page de connexion (immédiate et invisible si la session Keycloak est encore ouverte), puis retour à la page demandée. |
| **Appels à l'API** | `lib/api.ts` lit le jeton dans le cookie et l'ajoute à chaque appel. Si l'API le refuse (401), la session est effacée (`/login/end`, page qui relance une navigation complète vers la route `/login/end/clear`) et on revient à la connexion. |
| **Déconnexion** | menu du nom, en haut à droite (« Se déconnecter ») : cookies effacés, et la session est fermée chez Keycloak : la connexion suivante redemande le mot de passe. |

**Le parcours de connexion, pas à pas** :

1. `/login` est une page qui relance aussitôt une **navigation complète** du navigateur vers `/login/start`. (La navigation interne de Next.js ne sait pas suivre les routes qui posent des cookies.)
2. `/login/start` prépare un secret PKCE et un « state » (une valeur au hasard, vérifiée au retour), les garde dans le cookie `sd_oauth` (10 min), puis envoie sur **la page de connexion** de Keycloak.
3. L'utilisateur y saisit son identifiant et son mot de passe. Keycloak renvoie vers `/login/callback` avec un code à usage unique.
4. `/login/callback` vérifie le « state », puis échange le code contre les jetons (avec le secret PKCE, auprès de l'adresse interne de Keycloak).
5. Les jetons sont rangés dans deux **cookies protégés** : `sd_access` (5 min) et `sd_refresh` (24 h sans servir).
   - `HttpOnly` : le code de la page ne peut pas les lire ;
   - `SameSite=Lax` : ils ne sont pas envoyés depuis un autre site ;
   - `Secure` en HTTPS : ils ne passent que par une connexion chiffrée.

**Selon le rôle** (lu dans le jeton, pour l'affichage seulement) :

| Rôle | Onglets | Pages |
| --- | --- | --- |
| Consultation | Ce qui tourne | `/`, `/me` |
| Saisie | + Saisie (livraisons seulement) | + `/edit` |
| Administration | + Import, Journal, Comptes | + `/import`, `/audit-log`, `/accounts` |

Une page demandée sans le rôle affiche « Accès réservé » : **ni ses données ni son code ne partent vers le navigateur**. Les actions (enregistrer, supprimer…) revérifient le rôle sur le serveur, puis l'API revérifie tout. L'interface masque, l'API interdit.

**Mon compte** (`/me`, clic sur son nom en haut à droite) :

- **changer son mot de passe** : le bouton envoie sur la page de Keycloak (à l'allure de l'outil), qui redemande le mot de passe actuel si la connexion date un peu, puis le nouveau ; retour sur « Mon compte » avec « Mot de passe changé » (ou « annulé ») ;
- **Apparence** : le thème de couleurs, ◐ Automatique (comme l'ordinateur), ☀ Clair ou ☾ Sombre.
  - Le choix est **retenu dans le compte** (`PATCH /api/me`) : il suit la personne sur tous ses postes.
  - Le serveur Next.js en garde une copie dans le cookie `sd_theme` (posé à la connexion et à chaque changement). Il envoie ainsi chaque page dans le bon thème, sans clignotement.
  - La page de connexion garde le dernier thème de ce navigateur.
  - Code : `lib/theme.ts`, attribut `data-theme` de `<html>`, couleurs dans `styles.css` ;
- **Accès par script** : comment appeler l'API depuis un script (jeton hors ligne de Keycloak, voir [api.md § 0](api.md#obtenir-un-jeton)), et le bouton **Fermer mes accès par script**, qui les annule tous.

**Exporter** (bouton de la barre du haut, tous les rôles) : télécharge toute la configuration dans un fichier Excel, `suivi-delivery-<instance>-<date>.xlsx` (`GET /api/configuration`, voir [api.md](api.md#export--get-apiconfiguration)). La route `/configuration` (`app/configuration/route.ts`) demande le fichier à l'API et le transmet : le navigateur ne parle toujours pas à l'API.

**Import** (`/import`, administration) : recharge le fichier de l'export, éventuellement modifié ou partiel (`PATCH /api/configuration`, voir [api.md](api.md#import--patch-apiconfiguration-mode-fusion)).

1. On choisit le fichier.
2. **Vérifier** affiche l'aperçu : par onglet, les ajouts, modifications et lignes inchangées ; le détail des changements ; les problèmes, avec leur onglet et leur ligne.
3. **Importer** l'enregistre, seulement après un aperçu sans problème.

Côté code : le fichier passe par une Server Action (`app/import/actions.ts`, 10 Mo au plus, réglé dans `next.config.ts`), puis part vers l'API. Le formulaire est un composant client (`components/import/ImportForm.tsx`), qui garde le fichier entre les deux étapes.

**Journal** (`/audit-log`, administration) : qui a créé, modifié ou supprimé quoi, et quand (`GET /api/audit-log`). Filtres : auteur, objet, action, période (jours, heure de Paris), nombre de lignes ; les plus récentes d'abord. Pour une modification, les champs changés s'affichent (« libellé : A → B ») ; « Avant / après » montre tout. Page calculée sur le serveur : les filtres sont un simple formulaire.

**Comptes** (`/accounts`, administration), en deux onglets. Les comptes sont gardés par Keycloak, mais gérés ici (par l'API) : l'administrateur ne voit jamais Keycloak.

- **Utilisateurs** (des personnes) : créer avec un mot de passe **provisoire** (la personne en choisit un nouveau à sa première connexion), changer le rôle, désactiver, donner un nouveau mot de passe provisoire (mot de passe oublié), supprimer ;
- **Programmes** (scripts, outil de déploiement) : créer (la clé est générée et **affichée une seule fois**, avec un bouton « Copier »), changer le rôle, désactiver, générer une **nouvelle clé**, supprimer.

Le dernier administrateur actif ne peut être ni supprimé, ni désactivé, ni rétrogradé.

## 3. L'espace « Ce qui tourne » (consultation)

C'est l'écran principal. **Toutes les informations y sont, mais le détail est caché** et ne s'ouvre qu'à la demande.

| Zone | Contenu | Comment l'ouvrir |
| --- | --- | --- |
| **Chiffres clés** (en haut) | nombre d'applications et de modules, déploiements en service, snapshots en service, dernière mise en production | toujours visible |
| **Tableau** | les modules en lignes, regroupés par application ; les environnements en colonnes, dans l'ordre de promotion. Chaque case affiche la version qui tourne et depuis quand, une pastille par emplacement, **une par ligne** ; quand une case en a plusieurs (ex. le même namespace sur deux clusters), chacune est précédée du code de son cluster (`cb01`). Vert = release, orange = snapshot, pointillé gris = emplacement réservé mais vide. Chaque environnement a sa **teinte pastel** (liseré à gauche des cases de sa colonne, en-tête légèrement teinté, pastille du panneau), donnée automatiquement dans l'ordre de promotion parmi 8 teintes (`environmentTint`, `lib/format.ts` ; couleurs `--env-0` à `--env-7` de `styles.css`, plus sourdes en thème sombre). | toujours visible ; la colonne survolée est mise en évidence |
| **Groupe d'application** | les modules d'une application | clic sur la ligne de l'application, ou « Tout replier » (« Tout déplier » quand tout est replié) |
| **Panneau de détail** (à droite) | trois onglets : **Ce qui tourne** (emplacement, namespace, cluster, zone réseau, paramètres, date), **Historique** (frise des installations successives), **Fiche** (besoins, utilisateurs, versions, compatibilités). On change d'environnement avec les pastilles en haut du panneau. | clic sur une version (onglet Ce qui tourne) ou sur un module (onglet Fiche) ; fermeture avec ✕, Échap ou un clic à côté |
| **Activité récente** (en bas) | les 10 dernières installations ; un clic ouvre l'historique correspondant | clic sur « Activité récente » |

Filtres : recherche par code ou nom, application, type (tous, capacités, métier), interrupteur « installés seulement », et un bouton pour effacer les filtres.

**Boutons, liens et menus** (toute l'interface) : trois allures seulement, pour qu'on devine ce qui se passe avant de cliquer, et des actions regroupées pour ne pas multiplier les boutons :

- **onglet** : passer d'une partie à une autre. Barre du haut (Ce qui tourne, Saisie, Journal, Comptes), sous-onglets de Comptes, onglets du panneau de détail, menu à gauche de la Saisie. L'onglet en cours est souligné ;
- **bouton** : agir. Toujours encadré, de la même taille : **plein bleu** pour l'action principale de l'écran, une seule (« + Nouveau… », « Enregistrer ») ; **rouge** seulement pour confirmer une suppression ; **normal** pour tout le reste (⟳ Actualiser, ⤓ Exporter, Effacer les filtres, Tout replier, Filtrer, Copier, Non…). Classes `button-primary`, `button-secondary`, `button-danger` (et `button-icon` pour ⋯) ;
- **choix** : choisir une valeur parmi quelques-unes (Tous / Capacités / Métier, thème de couleurs, environnements du panneau) ;
- le **texte bleu** est réservé aux liens placés dans une phrase (« Réessayer », « continuer »).

Actions regroupées dans un **menu déroulant** (`components/Menu.tsx`, fermé par un choix, Échap ou un clic à côté) :

- **le nom de la personne**, en haut à droite : son rôle, **Mon compte**, **Se déconnecter** (souligné quand on est sur « Mon compte ») ;
- **⋯ au bout de chaque ligne** des tableaux de la Saisie et des Comptes : **Modifier**, **Nouvelle clé** (programmes), **Supprimer** (en rouge, puis confirmation « Supprimer ? Oui / Non » à la place du menu) ;
- sur cet écran, un seul bouton **Tout replier**, qui devient **Tout déplier** quand tout est replié.

Tout ce qui se clique est un vrai lien ou un vrai bouton, utilisable au clavier (Tab puis Entrée) avec le même contour bleu : y compris la ligne d'une application (replier) et le nom d'un module (ouvrir sa fiche), boutons qui occupent toute la case (`cell-button`).

**Mode sombre** : par défaut (thème « Automatique »), l'interface suit le réglage clair ou sombre de ton poste. On peut choisir un autre thème dans « Mon compte ».

## 4. L'espace « Saisie »

On y gère **les objets**. Réservé aux rôles Saisie et Administration :

- **Administration** : tous les objets, dont la **structure** (environnements, clusters, zones réseau, applications, namespaces, modules, dépendances, compatibilités, emplacements) ;
- **Saisie** (les développeurs) : seulement les **livraisons** (versions de module, paramètres, installations). La structure n'apparaît pas dans le menu ; elle reste lue pour remplir les listes des formulaires.

La liste de la structure est dans `lib/types.ts` (`RESOURCES_STRUCTURE`), la même que dans l'API ; `canUpdate` (`lib/session.ts`) décide, et les Server Actions la revérifient.

| Zone | Contenu |
| --- | --- |
| **Menu à gauche** | les 12 objets, regroupés en Listes (environnements, clusters, zones réseau), Socle (applications, namespaces, modules, dépendances) et Déploiement (versions, compatibilités, paramètres, emplacements, installations), avec leur nombre |
| **Liste** | les éléments de l'objet choisi, avec une recherche ; pour chaque ligne, un menu **⋯** : **Modifier** et **Supprimer** (avec confirmation) |
| **Formulaire** (panneau à droite) | création (« + Nouveau… ») ou modification ; les champs obligatoires sont marqués d'une `*`, et une aide est donnée sous les champs utiles |
| **Listes à choix** | toutes les listes des écrans de saisie (objets, installation guidée, comptes) sont des **listes filtrables** (`components/FilterableList.tsx`) : on tape directement dans le champ, seuls restent les choix qui contiennent ce texte (sans tenir compte des majuscules ni des accents) ; ↓ ↑ puis Entrée pour choisir, Échap pour fermer la liste (le formulaire reste ouvert). Les choix multiples (cases à cocher) ont un champ « Filtrer… » au-dessus dès qu'il y a plus de 5 choix ; les cases cochées restent toujours visibles. Un namespace s'affiche avec son cluster (`name · cb01`) : le même nom peut exister sur deux clusters. |
| **Nouveau namespace** | on **coche les clusters** : le même namespace est créé sur chacun. La case **« Créer les emplacements des modules »** (cochée par défaut) ajoute dans chaque namespace un emplacement par module de l'application, nommé d'après le code du module. **Tout ou rien** : au moindre refus, rien n'est créé et le message nomme le cluster en cause. La modification, elle, porte sur un seul namespace (un cluster). Dans `resources.ts`, ce sont les champs `batchCreationFields`, envoyés par la Server Action `createBatch` à `POST /api/namespaces/batch`. |
| **Nouveau module** | une case **« Lui créer un emplacement dans chaque namespace de l'application »** (cochée par défaut ; nom de release = code du module). Tout ou rien. Elle n'apparaît qu'à la création : `extraCreationFields` de `resources.ts`. |

**Les formulaires ne proposent que des choix cohérents** :

- pour un namespace, seuls les clusters du même type (prod ou hors prod) que l'environnement choisi ;
- pour un emplacement, seuls les modules de l'application du namespace ;
- pour une compatibilité, seuls les modules déclarés en dépendance, et la version max n'apparaît que pour la condition « BETWEEN » ;
- pour un paramètre, seuls les namespaces de l'application de son module.

**Enregistrer une installation** se fait pas à pas : environnement, puis namespace, puis emplacement (le formulaire rappelle ce qui y tourne), puis version du module réservé, puis paramètres technique et applicatif affectés au namespace, et enfin la date.

**Quand l'API refuse**, son message s'affiche tel quel en haut du formulaire, ou dans un bandeau pour une suppression. Par exemple : « batch-paie 2.4.0-SNAPSHOT est un snapshot : interdit en prod ». Les règles restent toutes côté API : l'interface ne fait qu'aider à saisir juste.

**Les dépendances et les installations** ne se modifient pas (pas de bouton Modifier) : on les supprime et on les recrée.

Après chaque enregistrement ou suppression, la page est redemandée au serveur, qui relit l'API : l'écran « Ce qui tourne » est aussitôt à jour. Le bouton **⟳ Actualiser** (en haut à droite) fait de même à tout moment.

## L'image Docker : site construit avant, puis copié

L'image du frontend ne télécharge **aucun** paquet npm et ne construit rien : le site est construit
avant, par `npm ci --ignore-scripts` puis `npm run build`, et l'image copie seulement le résultat,
`.next/standalone` (le serveur autonome) et `.next/static` (CSS, JavaScript du navigateur).

| Où | Qui construit le site |
| --- | --- |
| Poste | `docker-deploy` et `k8s-deploy` (en fabriquant l'image) |
| GitHub | `ci-docker.yml`, `publication.yml` (étapes « Construire le site du frontend ») |

**Le même site pour amd64 et arm64** :

- dans `next.config.ts`, le module `sharp` (qui retaille les images ; l'interface n'en affiche
  pas) est exclu, avec `images: { unoptimized: true }` ;
- c'était le seul module à contenir du code propre à un système et à un processeur. Sans lui, le
  serveur autonome est du JavaScript seul : construit sur un Mac, il tourne tel quel dans les
  images Linux amd64 et arm64 (vérifié) ;
- si un jour l'interface affiche des images optimisées, il faudra reprendre `sharp` et construire
  le site pour chaque processeur.

**Versions de Node.js** : l'image se construit avec `dhi.io/node:26.12.1-alpine3.24-dev` et tourne
avec `dhi.io/node:26.12.1-alpine3.24` (Docker Hardened Images ; l'image d'exécution n'a ni shell
ni npm) ; le poste et la CI vérifient le code avec leur propre Node.js : garder la même version
majeure partout (Node 26, `setup-node` 26).

## 5. Organisation du code (`frontend/`)

```Plaintext
frontend/
├── package.json        dépendances (Next.js, React, TypeScript) et commandes (dev, build, typecheck)
├── tsconfig.json       réglages de TypeScript (vérification stricte)
├── next.config.ts      réglages de Next.js (serveur autonome pour Docker, sans sharp : JavaScript seul)
├── .env.example        modèle des réglages (à copier en .env)
├── Dockerfile          image Docker : copie le site construit avant (voir « L'image Docker » ci-dessous)
├── docker.example.env  modèle des réglages du conteneur (port, adresse de l'API, nom de l'instance)
├── .dockerignore       seuls .next/standalone et .next/static entrent dans l'image
├── proxy.ts            passe avant chaque page : relais des pages de Keycloak (/auth),
│                       session valable, renouvellement des jetons, sinon page de connexion
├── app/                les pages : un dossier = une adresse
│   ├── layout.tsx      cadre commun : bandeau de l'instance, barre du haut, onglets selon le rôle
│   ├── connexion/      connexion par Keycloak : page.tsx (navigation complète vers demarrer/),
│   │                   demarrer/ (envoie sur la page de connexion ; ?action=mot-de-passe),
│   │                   retour/ (échange du code), indisponible/, fin/ (page, puis la route
│   │                   fin/effacer/ efface une session refusée par l'API), actions.ts (se déconnecter)
│   ├── moi/            « Mon compte » : changer son mot de passe (lien vers Keycloak), apparence,
│   │                   accès par script (AccesParScript.tsx)
│   ├── comptes/        « Comptes » (administration) : page et actions
│   ├── configuration/  route.ts : /configuration, l'export Excel (fichier demandé à l'API et transmis)
│   ├── import/         « Import » (administration) : page et actions (aperçu, import)
│   ├── journal/        « Journal » : qui a fait quoi, et quand (filtres en paramètres de l'adresse)
│   ├── page.tsx        « Ce qui tourne » (adresse /) : lit l'API et calcule l'état, sur le serveur
│   ├── saisie/
│   │   ├── page.tsx    « Saisie » (adresse /edit) : lit les données et les listes fermées
│   │   └── actions.ts  les enregistrements et suppressions, exécutés sur le serveur
│   ├── sante/route.ts  /health : probe Kubernetes (répond « ok », même sans API)
│   └── styles.css      l'apparence ; toutes les couleurs sont des variables en haut du fichier,
│                       avec leur version pour le mode sombre
├── lib/                le code sans affichage
│   ├── reglages.ts     variables d'environnement (API_URL, KEYCLOAK_URL, INSTANCE_NAME…), lues au lancement
│   ├── session.ts      cookies de session, lecture du nom et du rôle, droits par rôle
│   ├── api.ts          appels à l'API avec le jeton (lecture, écriture, fichier), côté serveur seulement
│   ├── oauth.ts        connexion par Keycloak : adresse de la page de connexion, PKCE, échange du code,
│   │                   renouvellement, fermeture de la session
│   ├── theme.ts        thème de couleurs : cookies sd_theme et sd_theme_auth (pages de Keycloak)
│   ├── journal.ts      journal : noms des objets et des actions, champs changés, dates de Paris
│   ├── donnees.ts      chargement de toutes les listes et des listes fermées
│   ├── etat.ts         rapprochement des données : ce qui tourne où, historique, fiche module,
│   │                   chiffres clés, activité récente
│   ├── types.ts        forme des données de l'API (pour TypeScript)
│   ├── versions.ts     comparaison des numéros de version, conditions de compatibilité
│   └── format.ts       petites fonctions d'affichage (dates, « il y a 3 j », couleurs de version)
└── components/         les blocs d'affichage
    ├── Navigation.tsx  onglets selon le rôle, « ⟳ Actualiser », « ⤓ Exporter », menu du nom (Mon compte, déconnexion)
    ├── Menu.tsx        menu déroulant commun (nom de la personne, « ⋯ » des lignes de tableau)
    ├── AccesRefuse.tsx message « Accès réservé » d'une page réservée à un autre rôle
    ├── Tiroir.tsx      cadre commun des panneaux qui glissent (fermeture par ✕, Échap ou clic à côté)
    ├── AlerteApi.tsx   message « Les données sont momentanément indisponibles »
    ├── consultation/   l'écran « Ce qui tourne »
    │   ├── Synthese.tsx      le bandeau des chiffres clés (calculé sur le serveur)
    │   ├── Consultation.tsx  la partie interactive : tableau, activité, panneau
    │   ├── VueEnsemble.tsx   le tableau : filtres, groupes repliables, cases
    │   ├── Panneau.tsx       le panneau de détail (onglets Ce qui tourne, Historique, Fiche)
    │   └── Activite.tsx      la liste repliable des dernières installations
    ├── comptes/GestionComptes.tsx  l'écran des comptes : onglets Utilisateurs et Programmes, formulaire
    ├── SecretAffiche.tsx           un secret montré une seule fois (clé de programme)
    └── saisie/         l'espace Saisie
        ├── ressources.ts            la description des 12 objets : champs, types, filtres, libellés.
        │                            Ajouter un champ ou un objet à la saisie se fait ici.
        ├── EspaceSaisie.tsx         menu, liste, recherche, suppression, panneau du formulaire
        ├── Formulaire.tsx           formulaire générique, construit à partir de ressources.ts
        └── FormulaireInstallation.tsx  l'enregistrement guidé d'une installation
```

**Composant « serveur » ou « client »** : par défaut, un composant est calculé sur le serveur et le navigateur ne reçoit que le résultat (HTML). Un fichier qui commence par `"use client"` est aussi envoyé au navigateur, parce qu'il réagit aux clics ou à la saisie (filtres, panneaux, formulaires). On garde le maximum côté serveur.

**Le choix fait** : le serveur charge toutes les listes de l'API à chaque page, puis fait les rapprochements. C'est simple et rapide pour quelques centaines d'éléments. Si les volumes grossissent, l'API pourra fournir directement une vue « ce qui tourne ».
