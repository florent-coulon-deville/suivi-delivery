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
```

- **Le navigateur ne parle jamais à l'API.** Il ne connaît ni son adresse ni ses routes : il reçoit des pages déjà prêtes.
- **Le serveur Next.js lit l'API** (`lib/api.ts`), fait les rapprochements (`lib/state.ts`) et envoie au navigateur la page, plus la seule partie interactive dont elle a besoin (filtres, panneaux, formulaires).
- **Les enregistrements** de l'espace Saisie passent aussi par le serveur (`app/edit/actions.ts`, des « Server Actions » : des fonctions du serveur que le formulaire appelle comme des fonctions ordinaires).
- **Chaque page ne reçoit que son propre code** : la page « Ce qui tourne » ne contient rien de l'espace Saisie.
- **Pas de connexion** (version légère) : pas de comptes ni de rôles, tous les onglets sont ouverts à tous. L'interface est à réserver à un réseau de confiance.

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

| Commande (depuis `frontend/`) | Rôle |
| --- | --- |
| `npm run dev` | site de développement, rechargé à chaque modification |
| `npm run typecheck` | vérifie les types de tout le code (doit passer avant chaque commit) |
| `npm run build` | construit le site pour la mise en ligne (vérifie aussi les types) |

**Réglages** (adresse de l'API, nom de l'instance affiché en bandeau) : variables d'environnement ou fichier `frontend/.env`, voir [deploiement.md](deploiement.md). Par exemple `INSTANCE_NAME=recette npm run dev` affiche un bandeau orange « Instance : recette ». Le **port** se donne au lancement (`PORT=3000 npm run dev`) : il est lu avant le fichier `.env`.

Avec un fichier SQLite (`APP_DB_FILE`, ou `./deployment/docker-deploy.zsh`, voir [sqlite.md](sqlite.md)), les données de l'API sont conservées : inutile de relancer `load_demo.py` après un redémarrage. Pour repartir d'une démonstration propre : `./deployment/docker-deploy.zsh --reset`, puis relancer le script. Sans fichier, l'API garde ses données en mémoire : elles sont perdues à chaque arrêt.

## 2 bis. Les écrans et la barre du haut

| Onglet | Adresse | Rôle |
| --- | --- | --- |
| Ce qui tourne | `/` | la consultation (§ 3) |
| Saisie | `/edit` | gérer tous les objets (§ 4) |
| Import | `/import` | recharger le fichier Excel de l'export |
| Journal | `/audit-log` | quoi a été créé, modifié ou supprimé, et quand |

Pas de page de connexion, ni de « Mon compte », ni d'écran « Comptes » dans cette version.

**Thème** (menu « Thème », en haut à droite) : **Automatique** (comme le réglage clair ou sombre de l'ordinateur), **Clair** ou **Sombre**.

- Le choix est **retenu par ce navigateur**, dans le cookie `sd_theme` (un an), posé par une Server Action (`app/theme.ts`). Il n'y a pas de compte où le ranger.
- Le serveur Next.js lit ce cookie et envoie chaque page directement dans le bon thème, sans clignotement.
- Code : `lib/theme.ts`, attribut `data-theme` de `<html>`, couleurs dans `styles.css`.

**Exporter** (bouton de la barre du haut) : télécharge toute la configuration dans un fichier Excel, `suivi-delivery-<instance>-<date>.xlsx` (`GET /api/configuration`, voir [api.md](api.md#export--get-apiconfiguration)). La route `/configuration` (`app/configuration/route.ts`) demande le fichier à l'API et le transmet : le navigateur ne parle toujours pas à l'API.

**Import** (`/import`) : recharge le fichier de l'export, éventuellement modifié ou partiel (`PATCH /api/configuration`, voir [api.md](api.md#import--patch-apiconfiguration-mode-fusion)).

1. On choisit le fichier.
2. **Vérifier** affiche l'aperçu : par onglet, les ajouts, modifications et lignes inchangées ; le détail des changements ; les problèmes, avec leur onglet et leur ligne.
3. **Importer** l'enregistre, seulement après un aperçu sans problème.

Côté code : le fichier passe par une Server Action (`app/import/actions.ts`, 10 Mo au plus, réglé dans `next.config.ts`), puis part vers l'API. Le formulaire est un composant client (`components/import/ImportForm.tsx`), qui garde le fichier entre les deux étapes.

**Journal** (`/audit-log`) : quoi a été créé, modifié ou supprimé, et quand (`GET /api/audit-log`), sans auteur (pas de comptes). Filtres : objet, action, période (jours, heure de Paris), nombre de lignes ; les plus récentes d'abord. Pour une modification, les champs changés s'affichent (« libellé : A → B ») ; « Avant / après » montre tout. Page calculée sur le serveur : les filtres sont un simple formulaire.

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

- **onglet** : passer d'une partie à une autre. Barre du haut (Ce qui tourne, Saisie, Import, Journal), onglets du panneau de détail, menu à gauche de la Saisie. L'onglet en cours est souligné ;
- **bouton** : agir. Toujours encadré, de la même taille : **plein bleu** pour l'action principale de l'écran, une seule (« + Nouveau… », « Enregistrer ») ; **rouge** seulement pour confirmer une suppression ; **normal** pour tout le reste (⟳ Actualiser, ⤓ Exporter, Effacer les filtres, Tout replier, Filtrer, Copier, Non…). Classes `button-primary`, `button-secondary`, `button-danger` (et `button-icon` pour ⋯) ;
- **choix** : choisir une valeur parmi quelques-unes (Tous / Capacités / Métier, thème de couleurs, environnements du panneau) ;
- le **texte bleu** est réservé aux liens placés dans une phrase (« Réessayer », « continuer »).

Actions regroupées dans un **menu déroulant** (`components/Menu.tsx`, fermé par un choix, Échap ou un clic à côté) :

- **Thème**, en haut à droite : **Automatique**, **Clair**, **Sombre** ;
- **⋯ au bout de chaque ligne** des tableaux de la Saisie : **Modifier**, **Supprimer** (en rouge, puis confirmation « Supprimer ? Oui / Non » à la place du menu) ;
- sur cet écran, un seul bouton **Tout replier**, qui devient **Tout déplier** quand tout est replié.

Tout ce qui se clique est un vrai lien ou un vrai bouton, utilisable au clavier (Tab puis Entrée) avec le même contour bleu : y compris la ligne d'une application (replier) et le nom d'un module (ouvrir sa fiche), boutons qui occupent toute la case (`cell-button`).

**Mode sombre** : par défaut (thème « Automatique »), l'interface suit le réglage clair ou sombre de ton poste. On peut choisir un autre thème dans le menu « Thème ».

## 4. L'espace « Saisie »

On y gère **tous les objets** : la structure (environnements, clusters, zones réseau, applications, namespaces, modules, dépendances, compatibilités, emplacements) comme les livraisons (versions de module, paramètres, installations). Ouvert à tous (pas de rôles).

| Zone | Contenu |
| --- | --- |
| **Menu à gauche** | les 12 objets, regroupés en Listes (environnements, clusters, zones réseau), Socle (applications, namespaces, modules, dépendances) et Déploiement (versions, compatibilités, paramètres, emplacements, installations), avec leur nombre |
| **Liste** | les éléments de l'objet choisi, avec une recherche ; pour chaque ligne, un menu **⋯** : **Modifier** et **Supprimer** (avec confirmation) |
| **Formulaire** (panneau à droite) | création (« + Nouveau… ») ou modification ; les champs obligatoires sont marqués d'une `*`, et une aide est donnée sous les champs utiles |
| **Listes à choix** | toutes les listes des écrans de saisie (objets, installation guidée) sont des **listes filtrables** (`components/FilterableList.tsx`) : on tape directement dans le champ, seuls restent les choix qui contiennent ce texte (sans tenir compte des majuscules ni des accents) ; ↓ ↑ puis Entrée pour choisir, Échap pour fermer la liste (le formulaire reste ouvert). Les choix multiples (cases à cocher) ont un champ « Filtrer… » au-dessus dès qu'il y a plus de 5 choix ; les cases cochées restent toujours visibles. Un namespace s'affiche avec son cluster (`name · cb01`) : le même nom peut exister sur deux clusters. |
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
| GitHub | `_images.yml` (appelée par les pipelines `snapshot.yml` et `release.yml`) |

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
├── Dockerfile          image Docker : construit le site, puis ne garde que le serveur autonome
├── docker.example.env  modèle des réglages du conteneur (port, adresse de l'API, nom de l'instance)
├── .dockerignore       ce qui n'entre pas dans l'image
├── app/                les pages : un dossier = une adresse
│   ├── layout.tsx      cadre commun : bandeau de l'instance, barre du haut, onglets, thème
│   ├── page.tsx        « Ce qui tourne » (adresse /) : lit l'API et calcule l'état, sur le serveur
│   ├── edit/
│   │   ├── page.tsx    « Saisie » (adresse /edit) : lit les données et les listes fermées
│   │   └── actions.ts  les enregistrements et suppressions, exécutés sur le serveur
│   ├── import/         « Import » : page et actions (aperçu, import)
│   ├── audit-log/      « Journal » : quoi a été fait, et quand (filtres en paramètres de l'adresse)
│   ├── configuration/  route.ts : /configuration, l'export Excel (fichier demandé à l'API et transmis)
│   ├── theme.ts        changer le thème (Server Action : cookie sd_theme)
│   ├── health/route.ts /health : probe Kubernetes (répond « ok », même sans API)
│   └── styles.css      l'apparence ; toutes les couleurs sont des variables en haut du fichier,
│                       avec leur version pour le mode sombre
├── lib/                le code sans affichage
│   ├── settings.ts     variables d'environnement (API_URL, INSTANCE_NAME…), lues au lancement
│   ├── api.ts          appels à l'API (lecture, écriture, fichier), côté serveur seulement
│   ├── theme.ts        thème de couleurs : cookie sd_theme, attribut data-theme
│   ├── audit-log.ts    journal : noms des objets et des actions, champs changés, dates de Paris
│   ├── data.ts         chargement de toutes les listes et des listes fermées
│   ├── state.ts        rapprochement des données : ce qui tourne où, historique, fiche module,
│   │                   chiffres clés, activité récente
│   ├── types.ts        forme des données de l'API (pour TypeScript)
│   ├── versions.ts     comparaison des numéros de version, conditions de compatibilité
│   └── format.ts       petites fonctions d'affichage (dates, « il y a 3 j », couleurs de version)
└── components/         les blocs d'affichage
    ├── Navigation.tsx  onglets, « ⟳ Actualiser », « ⤓ Exporter », menu « Thème »
    ├── Menu.tsx        menu déroulant commun (thème, « ⋯ » des lignes de tableau)
    ├── Drawer.tsx      cadre commun des panneaux qui glissent (fermeture par ✕, Échap ou clic à côté)
    ├── ApiAlert.tsx    message « Les données sont momentanément indisponibles »
    ├── FilterableList.tsx  liste à choix filtrable (on tape pour filtrer)
    ├── view/           l'écran « Ce qui tourne »
    │   ├── Summary.tsx       le bandeau des chiffres clés (calculé sur le serveur)
    │   ├── View.tsx          la partie interactive : tableau, activité, panneau
    │   ├── Overview.tsx      le tableau : filtres, groupes repliables, cases
    │   ├── Panel.tsx         le panneau de détail (onglets Ce qui tourne, Historique, Fiche)
    │   └── Activity.tsx      la liste repliable des dernières installations
    ├── import/ImportForm.tsx  le formulaire d'import (fichier, aperçu, import)
    └── edit/           l'espace Saisie
        ├── resources.ts           la description des 12 objets : champs, types, filtres, libellés.
        │                          Ajouter un champ ou un objet à la saisie se fait ici.
        ├── EditArea.tsx           menu, liste, recherche, suppression, panneau du formulaire
        ├── Form.tsx               formulaire générique, construit à partir de resources.ts
        └── InstallationForm.tsx   l'enregistrement guidé d'une installation
```

**Composant « serveur » ou « client »** : par défaut, un composant est calculé sur le serveur et le navigateur ne reçoit que le résultat (HTML). Un fichier qui commence par `"use client"` est aussi envoyé au navigateur, parce qu'il réagit aux clics ou à la saisie (filtres, panneaux, formulaires). On garde le maximum côté serveur.

**Le choix fait** : le serveur charge toutes les listes de l'API à chaque page, puis fait les rapprochements. C'est simple et rapide pour quelques centaines d'éléments. Si les volumes grossissent, l'API pourra fournir directement une vue « ce qui tourne ».
