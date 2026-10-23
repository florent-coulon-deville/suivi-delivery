# API

- **Documentation interactive (Swagger)** : <http://localhost:8000/api/docs>. Le bouton « Try it out » permet de tester chaque appel.
- Tout est servi sous `/api`, et les échanges sont en JSON.
- Les données sont gardées dans une base PostgreSQL (voir [postgresql.md](postgresql.md)). Sans base (`APP_DB_HOST` absente), elles sont en mémoire et perdues à l'arrêt.
- **Chaque appel doit porter un jeton d'accès de Keycloak** (voir § 0). Dans Swagger : bouton **Authorize**, puis la page de connexion de l'outil.

## 0. Connexion et droits

Les comptes, les mots de passe et la fabrication des jetons sont gérés par **Keycloak** (guide : [keycloak.md](keycloak.md)). L'API ne fait que **vérifier** chaque jeton (signature de Keycloak, émetteur, destinataire `suivi-delivery-api`, expiration) et y lire le rôle.

### Les comptes

| Sorte | Se connecte avec | Exemple |
| --- | --- | --- |
| `PERSON` | identifiant + mot de passe, sur la page de connexion de l'outil | un utilisateur de l'interface |
| `PROGRAM` | identifiant + clé (client credentials), clé générée par Keycloak et affichée une seule fois | un script, l'outil de déploiement |

| Rôle | Droits |
| --- | --- |
| `VIEWER` | lire les données (`GET`) |
| `EDITOR` | lire, et modifier les **livraisons** (`POST`, `PUT`, `PATCH`, `DELETE`) : versions de module, paramètres, installations |
| `ADMIN` | tout : aussi la **structure** (environnements, clusters, zones réseau, applications, namespaces, modules, dépendances, compatibilités, emplacements), les comptes (`/api/accounts`) et le journal |

La **structure** est le paramétrage général, fait par l'administrateur. Les développeurs y saisissent ensuite leurs **livraisons**.

- Un rôle insuffisant reçoit un 403 (« Droits insuffisants : rôle ADMIN requis »).
- Un compte sans rôle ne peut rien faire.
- Le rôle est lu **dans le jeton**. Un rôle retiré, ou un compte désactivé, prend donc effet à la fin du jeton en cours (5 minutes au plus) : Keycloak refuse ensuite d'en donner un nouveau.

Le compte **`admin`** est créé par Keycloak à son premier démarrage, avec le mot de passe `APP_ADMIN_PASSWORD` (voir [deploiement.md](deploiement.md)). **Il reste toujours au moins un administrateur actif** : supprimer, désactiver ou rétrograder le dernier est refusé (409).

### Obtenir un jeton

Les jetons viennent de Keycloak, servi sous l'adresse de l'interface (sur le poste : `http://localhost:8080/auth`). Adresses :

| | Adresse |
| --- | --- |
| page de connexion | `<frontend>/auth/realms/suivi-delivery/protocol/openid-connect/auth` |
| jetons | `<frontend>/auth/realms/suivi-delivery/protocol/openid-connect/token` |
| description complète (OpenID Connect) | `<frontend>/auth/realms/suivi-delivery/.well-known/openid-configuration` |

- **Une personne, à la main** (Swagger, Bruno) : on passe par la page de connexion (client `suivi-delivery-tools`). Tout est déjà réglé :
  - Swagger : bouton **Authorize**, *authorizationCode* ;
  - Bruno : ouvrir la collection du projet ([`bruno/`](../bruno/), *Open Collection*), puis *Get Access Token* dans l'onglet *Auth* de la collection.
- **Une personne, dans un script** : un **jeton hors ligne**, obtenu une fois en se connectant dans le navigateur. C'est un jeton de longue durée, qui sert à obtenir des jetons d'accès sans se reconnecter :

  ```bash
  cd backend && uv run python -m scripts.login     # affiche une adresse et un code, puis le jeton hors ligne
  ```

  À chaque lancement, le script l'échange contre un jeton d'accès (`grant_type=refresh_token`, client `suivi-delivery-tools`).
  - Il reste valable 30 jours sans servir, et un an au plus.
  - `DELETE /api/me/offline-access` (« Mon compte » → « Fermer mes accès par script ») les annule tous.
- **Un programme** : son identifiant et sa clé (créés dans l'écran Comptes) :

  ```bash
  curl -X POST http://localhost:8080/auth/realms/suivi-delivery/protocol/openid-connect/token \
       -d grant_type=client_credentials -d client_id=deployment -d 'client_secret=…'
  # 200 {"access_token": "eyJ…", "expires_in": 300, "token_type": "Bearer", …}
  ```

Puis, à chaque appel : `Authorization: Bearer eyJ…`. Les jetons d'accès durent 5 minutes.

La description OpenAPI (`/api/openapi.json`) déclare la connexion **une fois pour toute l'API**, avec les adresses complètes de Keycloak. Quand on l'importe dans Bruno ou Postman, la connexion est donc déjà réglée.

### Comptes : `/api/accounts` (ADMIN) et `/api/me`

Les comptes sont dans Keycloak. Ces routes les gèrent pour l'écran Comptes, en appelant Keycloak.

- L'identifiant d'un compte (`id`) est celui de Keycloak (lettres, chiffres et tirets).
- Si Keycloak ne répond pas : 503.

| Appel | Rôle |
| --- | --- |
| `GET /api/accounts`, `GET /api/accounts/{id}` | lister, lire (jamais de mot de passe ni de clé) |
| `POST /api/accounts` | créer : `identifier`★, `name`★, `kind`★, `role`★, `password` (★ pour une PERSON : mot de passe **provisoire**, à changer à sa première connexion ; interdit pour un PROGRAM). Pour un PROGRAM, la réponse contient sa **clé**, affichée une seule fois. 409 si l'identifiant est pris (personne ou programme) |
| `PATCH /api/accounts/{id}` | modifier `name`, `role`, `active`, `password` (nouveau mot de passe provisoire, PERSON). Désactiver, ou donner un mot de passe, coupe ses connexions en cours |
| `DELETE /api/accounts/{id}` | supprimer |
| `POST /api/accounts/{id}/key` | nouvelle clé d'un PROGRAM (l'ancienne ne marche plus) |
| `GET /api/me` | qui suis-je (d'après mon jeton : identifiant, nom, sorte, rôle) et mon thème de couleurs (`theme`) |
| `PATCH /api/me` `{"theme": "AUTO" \| "LIGHT" \| "DARK"}` | mes préférences (le thème de l'interface) → 200 ; 422 valeur inconnue |
| `DELETE /api/me/offline-access` | fermer mes accès par script (jetons hors ligne) → 204 ; 422 pour un programme |

Pas de `PUT /api/accounts/{id}` (405) : un mot de passe ne se « remplace » pas avec le reste. Le mot de passe se change sur la page de connexion de l'outil (« Mon compte » → « Changer mon mot de passe »), jamais par l'API.

### Journal des actions : `GET /api/audit-log`

Chaque saisie acceptée (création, modification, suppression) est notée **automatiquement**, avec :

- la date ;
- l'auteur : son identifiant Keycloak, son identifiant de connexion et sa sorte (PERSON ou PROGRAM) ;
- l'objet : le nom de sa table (ou `accounts`) et son identifiant ;
- l'action : `CREATE`, `UPDATE` ou `DELETE` ;
- l'objet **avant** et **après**.

Ne sont pas notées : les saisies refusées, et les connexions. Un mot de passe ou une clé n'apparaît jamais en clair : on note seulement `"changé"`.

Le journal se lit seulement (`POST`, `PUT`, `PATCH`, `DELETE` : 405), les plus récentes d'abord. Il est **réservé à l'ADMIN** (403 pour les autres rôles), qui voit tout : les données et les comptes.

```bash
curl "$API/audit_log?object=installations&since=2026-10-01T00:00:00&limit=50"
# 200 [{"id": 42, "date": "2026-10-12T09:15:03Z", "auteur_id": "5f1c…", "auteur": "paul",
#       "auteur_sorte": "PERSON", "objet": "installations", "objet_id": "7", "action": "CREATE",
#       "avant": null, "apres": {"id": 7, "emplacement_id": 1, …}}, …]
```

Filtres, tous facultatifs : `author` (identifiant), `object`, `object_id`, `action`, `since` et `until` (bornes comprises ; sans fuseau horaire : UTC), `limit` (200 par défaut, 1000 au plus).

### Export et import de la configuration : `/api/configuration`

Toute la configuration dans un **fichier Excel** (`.xlsx`), pour trois usages : la recopier d'une instance à l'autre, la sauvegarder, la saisir en masse dans un tableur.

#### Export : `GET /api/configuration`

Le fichier à télécharger. Ouvert dès le rôle **VIEWER** : on n'exporte que ce qu'on peut déjà lire.

```bash
curl -OJ "$API/configuration"
# 200  fichier suivi-delivery-configuration-2026-10-14.xlsx (Content-Disposition)
```

Contenu :

- un onglet **À propos** : outil, version, numéro du **format** du fichier, date de l'export (UTC) ;
- un onglet par objet, **dans l'ordre de saisie** : Environnements, Clusters, Zones réseau, Applications, Namespaces, Modules, Dépendances, Versions, Compatibilités, Paramètres, Affectations (les namespaces de chaque paramètre, une ligne par couple), Emplacements, Installations ;
- première ligne de chaque onglet : les titres ; puis une ligne par objet.

Les objets se désignent par leurs **noms métier**, jamais par les identifiants de la base, qui changent d'une instance à l'autre :

| Objet | Désigné par |
| --- | --- |
| application, environnement, cluster, zone réseau | son identifiant ou son code |
| module | application + code |
| namespace | application + environnement + cluster + suffixe |
| version | module + numéro |
| paramètre | module + type + nom |
| emplacement | namespace + release |

Quand le lien reste forcément dans la même application (module d'un emplacement, version et paramètres d'une installation), on écrit seulement le code, le numéro ou le nom.

Valeurs :

- `oui` / `non` pour « prod » ;
- dates en UTC (temps universel), à la seconde près ;
- le nom des namespaces est donné pour information : il est calculé.

Détail des colonnes : `SHEETS` dans `backend/app/configuration.py`.

#### Import : `PATCH /api/configuration` (mode fusion)

Le corps de la requête est le **fichier lui-même** (`Content-Type: application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`, 10 Mo au plus). C'est la seule route de l'API qui ne reçoit pas du JSON. Elle est réservée à l'**ADMIN**.

La méthode est `PATCH`, car l'import fusionne sans rien retirer. Un remplacement complet (`PUT`, pour restaurer une sauvegarde) est prévu.

```bash
# Aperçu : rien n'est enregistré
curl -X PATCH "$API/configuration?dry_run=true" \
     -H "Content-Type: application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" \
     --data-binary @suivi-delivery-recette-2026-10-14.xlsx
# 200 {"essai": true, "applique": false,
#      "onglets": [{"onglet": "Modules", "ajouts": 2, "modifications": 1, "inchanges": 5}, …],
#      "changements": [{"onglet": "Modules", "ligne": 4, "action": "UPDATE", "objet": "paiement / web-paie",
#                       "details": ["Nom : Portail paie → Portail de paie"]}, …],
#      "problemes": []}
# Import : la même chose sans ?essai=true → 200 {…, "applique": true}
```

Ce que fait chaque ligne, l'objet étant reconnu par ses noms métier :

| La ligne désigne… | Résultat |
| --- | --- |
| un objet inconnu de l'outil | **ajouté** |
| un objet connu, au contenu différent (libellé, nom, type, zone réseau…) | **mis à jour** |
| un objet connu, au même contenu | inchangé |
| (objet absent du fichier) | **pas touché** : un fichier peut être partiel (un onglet, quelques lignes) et désigner des objets déjà dans l'outil |

Cas particuliers :

- **Installations** : c'est un historique, jamais modifié. Une installation déjà présente (même emplacement, version, paramètres et date à la seconde près) reste telle quelle ; sinon, elle est ajoutée.
- **Affectations** : une ligne ajoute un namespace à un paramètre. L'import n'en retire jamais.
- **Changer un code** dans le fichier ne renomme rien : l'outil y voit un autre objet. Les renommages se font dans l'écran Saisie.

**Tout ou rien.**

- Chaque ligne passe par les mêmes vérifications que la saisie à l'écran.
- Les règles d'ensemble (compatibilités, pas de snapshot en prod…) sont vérifiées une seule fois, sur le résultat. Une ligne peut donc s'appuyer sur une ligne plus bas, par exemple une dépendance déclarée avant l'installation du module requis.
- Chaque problème est donné avec son onglet et son numéro de ligne (sauf pour une règle d'ensemble).
- S'il reste un seul problème, rien n'est importé.
- Chaque objet ajouté ou modifié est noté au journal.

| Code | Quand |
| --- | --- |
| 200 | aperçu (`dry_run=true`, même avec des problèmes), ou import fait |
| 400 | ce n'est pas un fichier Excel lisible |
| 409 | il reste des problèmes : rien n'est importé ; `{"detail": "Import refusé : …", "report": {…}}` |
| 413 | plus de 10 Mo |
| 415 | `Content-Type` autre que celui d'Excel |
| 422 | pas le fichier de l'export : onglet inconnu, colonnes différentes, autre numéro de format (« À propos ») |

### Sans jeton

Seuls répondent sans jeton de connexion : Swagger (`/api/docs`, `/api/openapi.json`) et les probes (`/livez`, `/readyz`, `/startupz`).

## 1. Conventions

### Méthodes

| Méthode | Usage | Sûre ¹ | Idempotente ² | Succès | Erreurs possibles |
| --- | --- | --- | --- | --- | --- |
| `GET /api/<resource>` | lister (filtres possibles : `?application_id=…`) | oui | oui | **200** | 400 |
| `GET /api/<resource>/{id}` | lire un élément | oui | oui | **200** | 404 |
| `HEAD` (sur les mêmes URL que `GET`) | comme `GET`, sans le corps : savoir si un élément existe, connaître la taille de la réponse | oui | oui | **200** | 404 |
| `OPTIONS` (sur toute URL de l'API) | connaître les méthodes possibles, données dans l'en-tête `Allow` | oui | oui | **204** | 404 |
| `POST /api/<resource>` | créer | non | **non** : deux appels créent deux éléments, ou le second est refusé (409) | **201** + en-tête `Location: /api/<resource>/{id}` | 400, 409, 415, 422 |
| `PUT /api/<resource>/{id}` | **remplacer entièrement** un élément existant | non | oui | **200** | 400, 404, 409, 415, 422 |
| `PATCH /api/<resource>/{id}` | modifier **uniquement les champs envoyés** | non | oui ³ | **200** | 400, 404, 409, 415, 422 |
| `DELETE /api/<resource>/{id}` | supprimer | non | oui ⁴ | **204** (réponse vide) | 404, 409 |
| autre méthode | | | | | **405** + en-tête `Allow` |

1. **Sûre** : ne modifie rien.
2. **Idempotente** : la rejouer plusieurs fois donne le même état que la jouer une fois.
3. Nos `PATCH` donnent les nouvelles valeurs, sans les calculer à partir des anciennes : ils sont donc idempotents.
4. Le premier appel supprime (204), les suivants répondent 404, mais l'état reste le même.

**Exceptions** : les **dépendances** et les **installations** ne se modifient pas (ni `PUT` ni `PATCH`, donc 405). Un lien ou un fait passé se supprime, puis se recrée.

Exemple d'`OPTIONS` :

```text
OPTIONS /api/applications/1   →   204   Allow: GET, HEAD, PUT, PATCH, DELETE, OPTIONS
OPTIONS /api/installations/1  →   204   Allow: GET, HEAD, DELETE, OPTIONS
```

### PATCH ou PUT ?

Les deux modifient un élément existant. La différence tient à ce qu'on envoie :

| | `PATCH` : modification partielle | `PUT` : remplacement complet |
| --- | --- | --- |
| **On envoie** | uniquement les champs à changer | l'élément entier (tous les champs) |
| **Champ absent** | **inchangé** | reprend sa **valeur par défaut** s'il est facultatif ; **refusé (422)** s'il est obligatoire |
| **Champ à `null`** | vide le champ s'il est facultatif (`promotion_order`, `version_max`) ; **refusé (422)** sinon | même chose |
| **Rejouer la même requête** | même résultat | même résultat |
| **Élément inexistant** | 404 | 404 : `PUT` ne crée pas, car l'identifiant est attribué par l'outil (on crée avec `POST`) |
| **Contrôles** | les mêmes : unicité (409), références (422), cohérence d'ensemble (409) | |
| **Quand l'utiliser** | changer un ou deux champs, par exemple depuis un formulaire de modification | renvoyer un élément complet qu'on a relu et corrigé |

**Exemple**, avec un environnement qui vaut aujourd'hui :

```json
{ "id": 1, "code": "int", "label": "Intégration", "is_prod": false, "promotion_order": 1 }
```

| Requête | Résultat |
| --- | --- |
| `PATCH /api/environments/1` `{"label": "Intégration 2"}` | **200** : seul le libellé change, `promotion_order` reste à `1` |
| `PUT /api/environments/1` `{"code": "int", "label": "Intégration 2"}` | **200** : le libellé change, et `promotion_order`, absent, redevient `null` (sa valeur par défaut) ; `is_prod` reste à `false` (sa valeur par défaut) |
| `PUT /api/environments/1` `{"label": "Intégration 2"}` | **422** : le `code` est obligatoire en `PUT` |
| `PATCH /api/environments/1` `{"promotion_order": null}` | **200** : l'ordre est vidé |
| `PATCH /api/environments/1` `{"label": null}` | **422** : un libellé ne peut pas être vide |
| `PUT /api/environments/9` `{"code": "rec", "label": "REC"}` | **404** : l'environnement 9 n'existe pas ; pour le créer, `POST /api/environments` |

**En résumé** : `PATCH` dit « change ceci », `PUT` dit « voici l'élément tel qu'il doit être ».

### Codes retour

| Famille | Codes utilisés | Signification | Exemple |
| --- | --- | --- | --- |
| **1xx** information | aucun | Géré par le serveur, jamais renvoyé par l'API | |
| **2xx** succès | **200** OK | Lecture ou modification réussie | `GET`, `PUT`, `PATCH` |
| | **201** Created | Élément créé ; son adresse est dans `Location` | `POST /api/modules` |
| | **204** No Content | Réussi, pas de corps de réponse | `DELETE`, `OPTIONS` |
| **3xx** redirection | **307** | URL terminée par `/` : redirigée vers la même URL sans `/` | `/api/modules/` → `/api/modules` |
| **4xx** erreur de la demande | **400** Bad Request | Requête illisible : corps qui n'est pas du JSON valide, ou paramètre d'URL invalide | `{not from json` ; `?type=UNKNOWN` ; `?application_id=abc` |
| | **401** Unauthorized | Pas de jeton, jeton invalide ou expiré, ou pas fait pour l'outil ; en-tête `WWW-Authenticate: Bearer` | appel sans `Authorization` |
| | **403** Forbidden | Connecté, mais le rôle ne suffit pas | `POST` avec un compte VIEWER |
| | **404** Not Found | L'URL ne désigne aucun élément | `/api/applications/999`, `/api/applications/abc` |
| | **405** Method Not Allowed | Méthode impossible sur cette URL ; l'en-tête `Allow` donne les méthodes possibles | `DELETE /api/applications` |
| | **409** Conflict | Demande valide, mais contraire à l'état des données | identifiant déjà pris ; suppression d'un élément encore utilisé ; versions incompatibles ; saisie refusée par les contrôles de la base (filet de sécurité : « Saisie refusée par la base de données : … ») |
| | **415** Unsupported Media Type | Corps de `POST`, `PUT` ou `PATCH` qui n'est pas du JSON (`Content-Type: application/json`) ; seule exception, l'import de la configuration, qui reçoit un fichier Excel | envoi d'un formulaire ou de texte |
| | **422** Unprocessable Content | JSON lisible, mais contenu invalide | champ manquant ou à `null`, mauvais format, champ inconnu, `application_id` qui n'existe pas |
| **5xx** erreur de l'outil | **500** | Erreur imprévue dans l'outil : c'est un bug à corriger | |

**400 ou 422 ?** On répond 400 quand on ne peut pas lire la demande, et 422 quand on la lit mais que son contenu ne va pas.

Format des réponses d'erreur :

```json
// 400, 404, 409, 415, et 422 pour une référence inexistante : un message
{ "detail": "Application 999 introuvable" }

// 422 (et 400 pour un paramètre d'URL) : la liste des champs en erreur
{ "detail": [ { "loc": ["body", "trigram"], "msg": "String should match pattern '^[A-Za-z0-9]{3}$'", "type": "string_pattern_mismatch" } ] }
```

### Règles de saisie

| Règle | Détail |
| --- | --- |
| **Minuscules** | Tous les codes, l'identifiant, le trigramme et le suffixe sont convertis en minuscules : `INT` devient `int`. |
| **Espaces** | Les espaces autour des textes sont retirés. |
| **Caractères** | Identifiant d'application, code d'environnement et suffixe : lettres, chiffres et `-`. Le `_` est interdit, car ces valeurs forment le nom du namespace. Code de cluster et de module : lettres, chiffres, `-` et `_`. |
| **Trigramme** | Exactement 3 lettres ou chiffres. |
| **Numéro de version de module** | Chiffres séparés par des points, suffixe facultatif : `2.3.0`, `1.4`, `3.0.0-SNAPSHOT`. Refusé : `v1.4`. |
| **Champ inconnu** | Refusé (422) : une faute de frappe dans un nom de champ ne passe pas inaperçue. |
| **PATCH** | Un champ absent n'est pas modifié ; un champ obligatoire envoyé à `null` est refusé (422). |
| **PUT** | Tous les champs obligatoires sont à fournir ; un champ facultatif absent reprend sa valeur par défaut. |

## 2. Ressources

★ = obligatoire à la création.

| Ressource | Champs | Unicité | Tri | Filtre |
| --- | --- | --- | --- | --- |
| `/api/environments` | `code`★, `label`★, `is_prod` (défaut `false`), `promotion_order` (facultatif, ≥ 1) | `code` | ordre, puis code (sans ordre à la fin) | |
| `/api/clusters` | `code`★, `label`★, `is_prod` (défaut `false`) | `code` | code | |
| `/api/network-zones` | `code`★ (gardé en minuscules), `label`★ | `code` | code | |
| `/api/applications` | `identifier`★, `name`★, `trigram`★ | `identifier` | identifiant | |
| `/api/namespaces` | `application_id`★, `environment_id`★, `cluster_id`★, `suffix`★, `network_zone_id`★ ; **`name` calculé** (réponse seulement) | environnement + cluster + suffixe, dans l'application (le même nom une fois par cluster) | nom | `?application_id=` |
| `/api/modules` | `application_id`★, `code`★, `name`★, `type`★ (`CAPABILITY` / `BUSINESS_PROJECT`) | `code`, dans l'application | code | `?application_id=`, `?type=` |
| `/api/dependencies` | `module_id`★ (qui a besoin), `depends_on_id`★ (de qui) | le couple | module | `?module_id=` (ses besoins), `?depends_on_id=` (ses utilisateurs) |
| `/api/module-versions` | `module_id`★, `number`★, `type` (`SNAPSHOT` par défaut, ou `RELEASE`) | `number`, pour le module | module, numéro | `?module_id=` |
| `/api/compatibilities` | `module_version_id`★, `required_module_id`★, `condition`★ (`EXACT` / `AT_LEAST` / `BETWEEN`), `version`★, `version_max` (pour `BETWEEN`) | une par version et par module requis | version | `?module_version_id=`, `?required_module_id=` |
| `/api/parameters` | `module_id`★, `name`★ (libre, ex. une version `2.3` ; en minuscules, 50 caractères au plus), `type`★ (`TECHNICAL` / `APPLICATION`), `namespace_ids` (défaut `[]`, namespaces de l'application du module) | `name`, pour le module et le type | nom | `?module_id=`, `?application_id=`, `?namespace_id=` |
| `/api/slots` | `namespace_id`★, `module_id`★ (le seul module accepté), `release_name`★ | `release_name`, dans le namespace | namespace, nom de release | `?namespace_id=`, `?module_id=` |
| `/api/installations` | `slot_id`★, `module_version_id`★, `technical_parameter_id`★, `application_parameter_id`★, `date` (défaut : maintenant) | | **la plus récente en premier** | `?slot_id=`, `?module_version_id=` |

Précisions :

- **`namespace_ids`** d'un paramètre : en `PATCH`, la liste envoyée **remplace** la précédente. Les namespaces doivent appartenir à l'application du module du paramètre (422 sinon).
- **Installations** : pas de `PATCH` (405), car une installation est un fait passé. Elle est refusée (422) si :
  - la version n'est pas une version du module auquel l'emplacement est réservé ;
  - un paramètre n'a pas le bon type (technique ou applicatif) ;
  - un paramètre n'est pas affecté au namespace de l'emplacement.
- **Compatibilités** : refusées (422) si :
  - le module requis n'est pas déclaré en dépendance ;
  - `version_max` manque pour `BETWEEN`, ou est plus petite que `version` ;
  - `version_max` est donnée pour une autre condition.

  En `PATCH`, seules la condition et les versions se modifient.
- **Emplacements** : le module doit appartenir à l'application du namespace (422). Changer de module n'est possible que tant que l'emplacement n'a aucune installation (409).
- **Namespaces** : le cluster doit être du même type (prod / hors prod) que l'environnement (422).
- **Création groupée de namespaces** : `POST /api/namespaces/batch` (ADMIN) crée le même namespace sur plusieurs clusters.
  - Corps : les champs d'un namespace, mais avec `cluster_ids`★ (une liste, au moins un, sans doublon) au lieu de `cluster_id`.
  - `with_slots` (défaut `true`) : crée aussi, dans chaque namespace, un emplacement par module de l'application. Le nom de release est le code du module (`_` remplacé par `-`).
  - **Tout ou rien** : au moindre refus (409 ou 422, le message nomme le cluster), rien n'est créé.
  - Réponse `201` `{"namespaces": [...], "slots": [...]}`, **sans `Location`**, car plusieurs éléments sont créés (chacun a son `id` dans la réponse).
- **Création d'un module avec ses emplacements** : `POST /api/modules` accepte `with_slots` (défaut `false` ; refusé en `PUT`, 422).
  - Il crée un emplacement pour le nouveau module dans chaque namespace de son application, avec le code du module comme nom de release (`_` remplacé par `-`).
  - **Tout ou rien** : si ce nom est déjà pris dans un namespace (409, le message le nomme), ni le module ni aucun emplacement n'est créé.
  - Réponse : le module, avec `Location`.
- **Données incohérentes (409)**, règles vérifiées à chaque changement qui peut y toucher (voir `app/consistency.py`) :
  - un namespace est sur un cluster du même type que son environnement ;
  - en prod, seules des versions `RELEASE` tournent ;
  - dans un environnement, chaque version qui tourne trouve ses modules requis, dans n'importe quel namespace de l'environnement, et dans une version compatible si une condition est déclarée.

  Ces règles sont vérifiées pour : une installation ou sa suppression, une dépendance, une compatibilité, le numéro ou le type d'une version, l'environnement ou le cluster d'un namespace, le namespace d'un emplacement, et `is_prod` d'un environnement ou d'un cluster. Exemple :
  `{"detail": "Données incohérentes : batch 2.3 a besoin de auth en 1.4 ou plus, mais auth 1.2 tourne en int"}`
- **Dépendances** : pas de `PATCH` (405). Elles sont refusées si le module dépend de lui-même (422) ou si elles créent une boucle (409).
- **Ce qui tourne sur un emplacement** : `GET /api/installations?slot_id=…`, dont le premier élément est l'installation actuelle.

Suppression refusée (409) :

- d'un **environnement** ou d'un **cluster** utilisé par un namespace ;
- d'une **application** liée à un namespace ou à un module ;
- d'un **namespace** qui a des emplacements ou des paramètres affectés ;
- d'un **module** qui a des versions, des paramètres, des emplacements ou des dépendances (dans un sens ou dans l'autre) ;
- d'un **paramètre** utilisé par une installation ;
- d'une **version de module** déjà installée, ou qui a des compatibilités ;
- d'une **dépendance** sur laquelle s'appuient des compatibilités ;
- d'un **emplacement** qui a des installations.

### Listes fermées

`GET /api/enumerations` renvoie les valeurs possibles des listes fermées : `{"ModuleType": [...], "VersionType": [...], "ParameterType": [...], "ConditionType": [...]}`. L'interface s'en sert pour ses listes déroulantes. Elle marche aussi quand Swagger est masqué (`APP_DOCS=non`).

### Santé (probes Kubernetes)

Ces adresses servent à Kubernetes / OpenShift, qui les appelle régulièrement pour surveiller l'API. Elles sont hors de `/api`, sans jeton, et ne montrent aucune donnée (réglage dans [deploiement.md](deploiement.md#8-kubernetes--openshift--les-probes)).

| Route | Question | 200 `{"status": "ok"}` si… | Sinon |
| --- | --- | --- | --- |
| `GET /startupz` | As-tu fini de démarrer ? | démarrage fini (connectée à la base) | 503 `{"status": "unavailable", "detail": "Démarrage en cours"}` |
| `GET /readyz` | Peux-tu recevoir des appels ? | démarrage fini et la base répond | 503, avec la raison dans `detail` |
| `GET /livez` | Es-tu encore en vie ? | l'API répond (rien d'autre n'est vérifié) | pas de réponse : Kubernetes redémarre le pod |

## 3. Exemple pas à pas

On crée une application, un environnement, un cluster, puis un namespace et un module.

```bash
API=http://localhost:8000/api

# Un jeton d'accès (5 minutes) : par exemple celui de Swagger ou de Bruno, ou d'un programme
# (voir § 0), ajouté à chaque appel (dans ce terminal, « curl » l'envoie tout seul)
TOKEN='eyJ…'
alias curl='curl -H "Authorization: Bearer $JETON"'

curl -X POST $API/applications -H "content-type: application/json" \
     -d '{"identifier": "paiement", "name": "Paiement", "trigram": "ABC"}'
# 201  {"id": 1, "identifiant": "paiement", "nom": "Paiement", "trigramme": "abc"}

curl -X POST $API/environments -H "content-type: application/json" \
     -d '{"code": "INT", "label": "Intégration"}'
# 201  {"id": 1, "code": "int", "libelle": "Intégration", "est_prod": false, "ordre": null}

curl -X POST $API/clusters -H "content-type: application/json" \
     -d '{"code": "cb01", "label": "Cluster 1"}'
# 201  {"id": 1, "code": "cb01", "libelle": "Cluster 1", "est_prod": false}

curl -X POST $API/namespaces -H "content-type: application/json" \
     -d '{"application_id": 1, "environment_id": 1, "cluster_id": 1, "suffix": "batch", "network_zone_id": 1}'
# 201  {"id": 1, "nom": "abc-paiement-int-batch", "application_id": 1, ...}

curl -X POST $API/modules -H "content-type: application/json" \
     -d '{"application_id": 1, "code": "batch-paie", "name": "Batch de paie", "type": "BUSINESS_PROJECT"}'
# 201  {"id": 1, "application_id": 1, "code": "batch-paie", "nom": "Batch de paie", "type": "BUSINESS_PROJECT"}

curl "$API/modules?application_id=1"     # les modules visibles depuis les namespaces de l'application 1
curl -X DELETE $API/applications/1       # 409 {"detail": "Application liée à au moins un namespace"}
```

Puis on enregistre une installation : une version du module, des paramètres affectés au namespace, un emplacement réservé au module.

```bash
curl -X POST $API/module-versions -H "content-type: application/json" \
     -d '{"module_id": 1, "number": "2.3.0", "type": "RELEASE"}'
# 201  {"id": 1, "module_id": 1, "numero": "2.3.0", "type": "RELEASE"}

curl -X POST $API/parameters -H "content-type: application/json" \
     -d '{"module_id": 1, "name": "1", "type": "TECHNICAL", "namespace_ids": [1]}'
# 201  {"id": 1, ...}
curl -X POST $API/parameters -H "content-type: application/json" \
     -d '{"module_id": 1, "name": "1", "type": "APPLICATION", "namespace_ids": [1]}'
# 201  {"id": 2, ...}   (même nom, autre type : accepté)

curl -X POST $API/slots -H "content-type: application/json" \
     -d '{"namespace_id": 1, "module_id": 1, "release_name": "batch-paie"}'
# 201  {"id": 1, "namespace_id": 1, "module_id": 1, "release_name": "batch-paie"}

curl -X POST $API/installations -H "content-type: application/json" \
     -d '{"slot_id": 1, "module_version_id": 1, "technical_parameter_id": 1, "application_parameter_id": 2}'
# 201  {"id": 1, "emplacement_id": 1, ..., "date": "2026-10-09T10:45:00Z"}

curl "$API/installations?slot_id=1"    # historique de l'emplacement, le plus récent en premier
```

## 4. Organisation du code (`backend/app/`)

| Fichier | Rôle |
| --- | --- |
| `main.py` | Crée l'application FastAPI et branche les routes |
| `schemas.py` | Forme des données échangées et règles de saisie (Pydantic) |
| `storage.py` | Les opérations sur les tables (`list_all`, `add`…), et leur version en mémoire |
| `storage_postgres.py` | Les mêmes opérations dans la base PostgreSQL |
| `transactions.py` | Une transaction par requête, enregistrée juste avant la réponse ; une écriture à la fois |
| `http.py` | Règles HTTP communes : `HEAD`, `OPTIONS`, en-tête `Allow`, 415, et le choix entre 400, 404 et 422 |
| `routes/__init__.py` | Vérifications communes : 404, 409 (doublon ou élément utilisé), 422 (référence inexistante), en-tête `Location` |
| `routes/<resource>.py` | Les routes d'une ressource : lister, lire, créer, modifier, supprimer |

| `routes/enumerations.py` | Les valeurs des listes fermées, pour l'interface |
| `access.py` | Contrôle d'accès : jeton (401) et rôle (403) |
| `security.py` | Vérification des jetons de Keycloak (signature, émetteur, destinataire, expiration), lecture de l'identité et du rôle |
| `directory.py` | Les comptes dans Keycloak (son API d'administration), et leur version en mémoire pour les tests |
| `routes/accounts.py`, `routes/me.py` | Gestion des comptes, mon compte |
| `routes/documentation.py` | Swagger et description OpenAPI, retouchée pour Bruno (adresses de Keycloak) |
| `routes/health.py` | Les probes Kubernetes `/startupz`, `/readyz`, `/livez` (hors de `/api`) |
| `configuration.py`, `routes/configuration.py` | Toute la configuration dans un fichier Excel (export), objets désignés par leurs codes |
| `import_configuration.py` | Import du fichier de l'export (fusion) : lecture, rapprochement par codes, aperçu, tout ou rien |
| `audit_log.py`, `routes/audit_log.py` | Journal des actions : rempli par le stockage à chaque saisie, lu par `GET /api/audit-log` |
| `versions.py` | Comparaison des numéros de version et des conditions de compatibilité |
| `consistency.py` | Règles d'ensemble (type de cluster, pas de snapshot en prod, modules requis présents et compatibles) ; fait le changement à l'essai, annulé s'il casse une règle |

Le trajet d'une requête, par exemple `POST /api/modules` :

1. **FastAPI** valide le corps avec `ModuleCreation` (`schemas.py`). Si un champ manque ou a un mauvais format : **422**.
2. **La route** (`routes/modules.py`) vérifie que l'application existe (**422** sinon) et que le code est libre dans l'application (**409** sinon).
3. **Le stockage** enregistre le module et la base lui attribue un `id`.
4. **La route** répond **201** avec l'en-tête `Location`, juste après l'enregistrement de la transaction.

Pour ajouter une ressource : créer les schémas dans `schemas.py`, une table dans `storage.py` et dans la base (un changement Liquibase, voir [postgresql.md § 4](postgresql.md#4-faire-évoluer-la-structure)), un fichier `routes/<resource>.py` sur le modèle des autres, le brancher dans `main.py`, puis écrire `tests/test_<resource>.py`.
