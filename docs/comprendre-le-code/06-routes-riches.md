# 6. Les routes plus riches

Les autres routes suivent le patron de la page 5. Elles ajoutent seulement des **vérifications propres à leur objet**. Voici les trois cas les plus instructifs.

## La fonction `check` : contrôler l'objet « tel qu'il serait »

Dès qu'un objet a des règles (références, unicité composée…), on les rassemble dans une fonction `check`. Elle est appelée à la création **et** à la modification.

L'astuce, en modification, est de vérifier **l'objet complet tel qu'il serait après le changement** :

```python
def save(storage, namespace_id, changes):
    current = read_or_404(storage.namespaces, namespace_id, OBJECT)
    check(storage, {**current, **changes}, excluding_id=namespace_id)   # ← l'objet après changement
    ...
```

`{**current, **changes}` fusionne les deux dictionnaires : les champs de `changes` remplacent ceux d'`current`. Un PATCH qui ne change que l'environnement est donc vérifié avec l'application, le cluster et le suffixe actuels, ce qui permet de contrôler l'unicité « environnement + suffixe ».

## `namespaces.py` : un champ calculé

Le nom d'un namespace n'est **jamais stocké** : il est recalculé à chaque lecture.

```python
def with_name(storage: Storage, namespace: dict) -> dict:
    application = storage.applications.read_existing(namespace["application_id"])
    environment = storage.environments.read_existing(namespace["environment_id"])
    parts = [application["trigram"], application["identifier"], environment["code"], namespace["suffix"]]
    return {**namespace, "name": "-".join(parts)}
```

- `"-".join([...])` colle les morceaux avec des tirets, par exemple `abc-paiement-int-batch`.
- Toutes les routes de namespaces renvoient `with_name(...)`.
- **Pourquoi ne pas le stocker ?** Si l'identifiant d'une application change, le nom de ses namespaces suit tout seul. Il n'y a jamais de nom périmé.

Ses vérifications (`check`) :

1. l'application, l'environnement et le cluster existent (422) ;
2. le cluster est du même type (prod ou hors prod) que l'environnement (422) ;
3. le trio environnement + cluster + suffixe est unique dans l'application (409).

### Création groupée (`POST /api/namespaces/batch`)

`add_batch` crée le même namespace sur plusieurs clusters. Par défaut, elle crée aussi dans chacun un emplacement par module de l'application. Le nom de release de l'emplacement est le code du module, avec `_` remplacé par `-`.

- Elle réutilise les fonctions `add` des namespaces et des emplacements : les vérifications sont les mêmes qu'une saisie à l'unité.
- Tout se fait dans **`with storage.dry_run() as dry_run:`**. Au premier refus, l'erreur sort du bloc et rien n'est gardé : c'est **tout ou rien**.
- Le journal note chaque élément créé, comme d'habitude.

Même principe dans `modules.py`. `POST /api/modules` avec `with_slots: true` crée le module, puis un emplacement dans chaque namespace de son application, en un seul essai (`add_with_slots`). Ce champ n'existe que pour le `POST` (`ModuleCreationWithSlots`) : le `PUT` le refuse.

## `installations.py` : beaucoup de contrôles, une petite fonction par règle

```python
def reject(message: str):
    raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, message)


def check_parameter(storage, parameter_id, expected_type, namespace_id, module_id) -> None:
    """Le paramètre existe, a le bon type, configure le module de l'emplacement et est affecté au namespace."""
    check_reference(storage.parameters, parameter_id, "Paramètre")
    parameter = storage.parameters.read_existing(parameter_id)
    if parameter["type"] != expected_type:
        reject(f"Paramètre {parametre['nom']} : il n'est pas {type_attendu}")
    if parameter["module_id"] != module_id:
        reject(f"Paramètre {parametre['nom']} : ce n'est pas un paramètre du module …")
    if namespace_id not in parameter["namespace_ids"]:
        reject(f"Paramètre {parametre['nom']} : il n'est pas affecté au namespace de l'emplacement")


def check(storage, installation) -> None:
    check_reference(storage.slots, installation["slot_id"], "Slot")
    check_reference(storage.module_versions, installation["module_version_id"], "Version de module")
    # … la version doit appartenir au module réservé de l'emplacement
    check_parameter(storage, installation["technical_parameter_id"], ParameterType.TECHNICAL, ...)
    check_parameter(storage, installation["application_parameter_id"], ParameterType.APPLICATION, ...)
```

À retenir :

- **Une règle répétée devient une fonction** : `check_parameter` sert pour le paramètre technique et pour l'applicatif.
- **L'ordre compte** : d'abord vérifier qu'une référence existe (`check_reference`), ensuite seulement la lire avec `read_existing`.
- **Pas de `PATCH` ni de `PUT`** : une installation est un fait passé. Les routes n'existent pas, donc FastAPI répond 405.
- **La création et la suppression passent par `apply_if_consistent`** : on n'enregistre jamais une installation qui ferait tourner ensemble des versions incompatibles (page 7).

## `dependencies.py` : détecter une boucle

« A dépend de B » est refusé si B a déjà besoin de A, directement ou par l'intermédiaire d'autres modules. Sinon, on aurait A → B → … → A.

```python
def needs(storage: Storage, module_id: int, searched_id: int) -> bool:
    """Vrai si module_id a besoin de cherche_id, directement ou par l'intermédiaire d'autres modules."""
    to_see, seen = [module_id], set()
    while to_see:
        current = to_see.pop()
        if current == searched_id:
            return True
        if current not in seen:
            seen.add(current)
            to_see += [d["depends_on_id"] for d in storage.dependencies.list_all(module_id=current)]
    return False
```

On part du module et on suit ses dépendances, puis les dépendances de ses dépendances, et ainsi de suite :

- `to_see` est la liste des modules qu'il reste à examiner ;
- `seen` évite de repasser deux fois par le même module.

Si on tombe sur le module cherché, la nouvelle dépendance fermerait une boucle : 409.

## `configuration.py` : une réponse qui n'est pas du JSON

`GET /api/configuration` renvoie un **fichier Excel**, et non du JSON. Le travail est partagé en deux :

- `app/configuration.py` fabrique le fichier, en deux temps :
  1. `rows_by_sheet` lit toutes les tables et remplace chaque identifiant par des **noms métier**. Par exemple, un namespace devient `["paiement", "int", "cb01", "batch"]` (application, environnement, cluster, suffixe).
  2. `excel_file` écrit les onglets avec la bibliothèque **openpyxl** (titres en gras, filtres, largeur des colonnes).
- `app/routes/configuration.py` renvoie ce contenu dans une `Response` dont le type est celui d'Excel. L'en-tête `Content-Disposition: attachment; filename="…"` dit au navigateur de l'enregistrer comme fichier.

Pourquoi des noms métier ? Les identifiants (1, 2, 3…) ne valent que dans une base. Sur une autre instance, le module 3 n'est pas le même. Les codes, eux, se retrouvent partout : c'est ce qui permet de recharger le fichier ailleurs.

## `import_configuration.py` : relire le fichier, avec les règles de l'écran

`PATCH /api/configuration` fait le chemin inverse. Trois idées :

1. **Les mêmes vérifications que l'écran.** Chaque fichier de route a deux fonctions, utilisées à la fois par l'écran et par l'import :
   - `add(storage, object)` : vérifier, puis créer ;
   - `save(storage, id, changes)` : vérifier, puis modifier.

   L'import ne réécrit donc aucune règle. Pour chaque ligne, `merge` cherche l'objet par ses codes : absent → `add`, différent → `save`, identique → rien.
2. **Tout signaler d'un coup.** Une ligne refusée (case mal remplie, référence introuvable, refus d'une route) devient un « problème » avec son onglet et son numéro de ligne, et la lecture continue.
3. **Tout ou rien, jugé en entier.**
   - L'import se fait dans un essai du stockage (`storage.dry_run()`), comme `apply_if_consistent`.
   - Dans le bloc `deferred_consistency()`, les règles d'ensemble ne sont pas vérifiées à chaque ligne, mais une seule fois à la fin (`inconsistencies`). En effet, une ligne peut avoir besoin d'une ligne plus bas.
   - S'il reste un problème, ou pour un simple aperçu (`dry_run=true`), une exception annule l'essai : rien n'est enregistré.

La route est `async`, car elle lit le fichier envoyé tel quel (`await request.body()`). Le travail sur la base, qui prend du temps, est confié à un autre fil d'exécution (`run_in_threadpool`) pour ne pas bloquer le serveur. FastAPI fait la même chose tout seul pour les routes ordinaires.

Page suivante : [la cohérence d'ensemble](07-coherence.md).
