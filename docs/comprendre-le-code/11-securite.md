# 11. La sécurité — `security.py`, `access.py`, `directory.py`

Qui peut appeler l'API, et pour faire quoi. La vue d'ensemble (routes, codes, exemples `curl`) est dans [api.md § 0](../api.md#0-connexion-et-droits), et le rôle de Keycloak dans [keycloak.md](../keycloak.md) ; ici, on regarde comment le code de l'API s'y prend.

## Ce que l'API ne fait pas

L'API ne garde **aucun mot de passe, aucune clé, aucun jeton**. Elle n'a ni page de connexion, ni adresse qui fabrique des jetons. C'est Keycloak qui fait tout cela. L'API se contente de **vérifier** les jetons qu'on lui présente.

## Les trois fichiers

| Fichier | Rôle |
| --- | --- |
| `security.py` | vérifier un jeton de Keycloak, et lire qui appelle (son identité et son rôle) |
| `access.py` | le contrôle à l'entrée de chaque route : qui appelle (401), a-t-il le droit (403) |
| `directory.py` | les comptes, gardés par Keycloak : l'API les gère pour l'écran Comptes, par l'API d'administration de Keycloak |

S'y ajoutent `routes/accounts.py` (gérer les comptes), `routes/me.py` (mon compte) et `routes/documentation.py` (Swagger).

## Un jeton, vérifié sans rien garder

Un jeton d'accès est un **JWT** : un petit texte en trois parties (en-tête, contenu, signature). Keycloak le signe avec une **clé privée** qu'il garde pour lui ; il publie la **clé publique** correspondante (adresse « certs »). Avec la clé publique, n'importe qui peut vérifier qu'un jeton vient bien de Keycloak, sans pouvoir en fabriquer.

```python
def check(self, token: str) -> Identity:
    key = self._keycloak_keys().get_signing_key_from_jwt(token).key   # la clé publique de Keycloak
    content = jwt.decode(
        token,
        key,
        algorithms=["RS256"],             # signature RSA de Keycloak
        audience="suivi-delivery-api",    # fait pour NOTRE API
        issuer=self.issuer,             # par NOTRE Keycloak, domaine suivi-delivery
        options={"require": ["exp", "iat", "sub", "iss", "aud"]},
    )
    return token_identity(content)
```

Quatre contrôles, et rien d'autre à garder :

| Contrôle | Pourquoi |
| --- | --- |
| **signature** | le jeton vient de notre Keycloak, et personne ne l'a modifié |
| **émetteur** (`iss`) | c'est bien le domaine `suivi-delivery`, à l'adresse que voient les navigateurs (`<APP_FRONTEND_URL>/auth/realms/suivi-delivery`) |
| **destinataire** (`aud`) | le jeton a été fait pour l'API de l'outil : un jeton fait pour une autre application du même Keycloak est refusé |
| **expiration** (`exp`) | 5 minutes : un jeton volé ne sert pas longtemps |

Les clés publiques sont lues sur Keycloak au premier jeton, puis gardées en mémoire. Keycloak change de clé de temps en temps : quand un jeton arrive signé par une clé inconnue, on relit les clés. C'est `PyJWKClient`, de la bibliothèque `pyjwt`, qui s'en occupe.

## Qui appelle : `Identity`

```python
@dataclass(frozen=True)
class Identity:
    subject: str          # identifiant Keycloak, qui ne change jamais (« sub »)
    identifier: str    # « paul », ou le nom du client d'un programme
    name: str            # « Paul Martin »
    kind: AccountKind  # PERSON, ou PROGRAM
    role: Role | None   # le plus fort des trois rôles de l'outil présents dans le jeton
```

Un **programme** obtient son jeton avec sa clé, sans personne derrière (on dit « client credentials »). Son jeton se reconnaît à deux choses : Keycloak y met `client_id`, et un nom d'utilisateur qui commence par `service-account-`. On garde alors le nom du client (par exemple `deployment-tool`) comme identifiant.

Dans Keycloak, les rôles s'emboîtent : `ADMIN` contient `EDITOR`, qui contient `VIEWER` (on dit des rôles « composites »). Un jeton d'administrateur porte donc les trois. `strongest_role` garde le plus fort, et ignore les rôles internes à Keycloak (`offline_access`…).

## Le contrôle à l'entrée : `access.py`

```python
def connected_identity(request, authorization) -> Identity:
    schema, _, token = (authorization or "").partition(" ")     # « Bearer eyJ… »
    if schema.lower() != "bearer" or not token:
        raise _reject("Jeton d'accès manquant : connectez-vous")           # 401
    try:
        identity = request.app.state.verifier.check(token)
    except KeycloakUnreachable:
        raise HTTPException(503, "Keycloak ne répond pas : réessayez")
    except InvalidToken:
        raise _reject("Jeton d'accès invalide ou expiré")                  # 401
    log_author(identity)       # l'auteur des saisies de la requête (journal)
    return identity
```

Ensuite, `require(role)` compare le rôle de la personne au rôle demandé (403 sinon). Le rôle demandé dépend de la méthode et du groupe de routes :

| Action | Rôle demandé |
| --- | --- |
| lire (GET) | VIEWER |
| modifier la **structure** (environnements, clusters, applications, modules…) | ADMIN |
| modifier les **livraisons** (versions de module, paramètres, installations) | EDITOR |

C'est le travail de `structure_rights` et `delivery_rights`, branchés sur chaque groupe de routes dans `main.py`.

Le rôle est **lu dans le jeton**. Si on retire un rôle dans Keycloak, le changement s'applique au jeton suivant, donc au plus tard 5 minutes après. C'est le prix d'une API qui ne garde rien.

## Les comptes : `directory.py`

L'écran Comptes passe toujours par notre API (`/api/accounts`) : l'administrateur ne voit jamais Keycloak. L'API gère les comptes **dans Keycloak**, avec son propre client, `suivi-delivery-api`, qui a le droit de gérer les utilisateurs et les clients du domaine.

Comme pour le stockage, deux réalisations de la même liste d'opérations (`list_all`, `read`, `create_person`, `create_program`, `update`, `delete`, `new_key`, `close_offline_access`) :

| Classe | Où sont les comptes |
| --- | --- |
| `KeycloakDirectory` | dans Keycloak : appels à son API d'administration (`/admin/realms/suivi-delivery/…`), avec un jeton du client de l'API |
| `MemoryDirectory` | en mémoire : les tests, sans Keycloak |

Une **personne** est un utilisateur Keycloak ; son mot de passe est donné **provisoire** (`"temporary": true`) : Keycloak lui en fait choisir un nouveau à sa première connexion. Un **programme** est un client Keycloak confidentiel, avec compte de service ; l'attribut `suivi-delivery.program` le distingue des clients de l'outil lui-même.

La règle « il reste toujours un administrateur actif » est vérifiée par la route (`routes/accounts.py`), avant d'appeler Keycloak. Chaque saisie est notée au journal (`log_edit`, objet `accounts`), sans mot de passe ni clé.

## Mon compte

`GET /api/me` répond avec ce que dit le jeton (identifiant, nom, rôle), plus le **thème** de couleurs, gardé dans notre base (table `preferences`), repéré par le `subject` (l'identifiant Keycloak, qui ne change jamais).

Le mot de passe ne passe **jamais** par l'API : l'interface envoie la personne sur la page de Keycloak (action `UPDATE_PASSWORD`). `DELETE /api/me/offline-access` annule les jetons hors ligne de la personne (ses scripts), en retirant chez Keycloak l'accord donné au client des outils.

## Au démarrage

`main.py` fabrique le vérificateur (`Verificateur.pour(reglages)`) et l'annuaire à partir des réglages (`APP_KEYCLOAK_URL`, `APP_KEYCLOAK_CLIENT_SECRET`, `APP_FRONTEND_URL`). Sans `APP_KEYCLOAK_URL`, aucun jeton n'est accepté (401, avec un message clair) ; sans la clé, l'écran Comptes répond 503. L'API démarre quand même : Keycloak peut démarrer après elle.

## Les tests

Les tests n'ont pas besoin de Keycloak :

- `tests/keys_for_tests.py` tire une clé RSA au hasard, une fois par lancement ;
- `tests/conftest.py` fabrique avec elle des jetons au même contenu que ceux de Keycloak (`token_content`, `sign`) ;
- l'application des tests reçoit un vérificateur qui connaît cette clé, et un `MemoryDirectory` avec le compte `admin`.

L'API vérifie ces jetons exactement comme ceux de Keycloak. `tests/test_security.py` vérifie les refus : jeton expiré, d'un autre émetteur, pour un autre destinataire, signé par une autre clé, illisible.

## Ce qu'il faut retenir

- Keycloak garde les comptes et fabrique les jetons ; l'API **vérifie** (signature, émetteur, destinataire, expiration) et ne garde rien.
- Le rôle vient du jeton : un changement s'applique en 5 minutes au plus.
- L'écran Comptes passe par l'API, qui gère les comptes dans Keycloak (`directory.py`) : l'administrateur ne voit pas Keycloak.
- Les tests fabriquent leurs propres jetons, signés par leur propre clé.
