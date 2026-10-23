# 7. La cohérence d'ensemble — `consistency.py` et `versions.py`

## Le problème

Certaines règles ne concernent pas **un** objet mais **plusieurs à la fois**. Par exemple, « en prod, seules des releases tournent » met en jeu une installation, un emplacement, un namespace, un environnement et une version.

Ces règles peuvent être cassées **par des modifications très différentes** : installer un snapshot en prod, mais aussi passer un environnement en prod alors qu'un snapshot y tourne, ou changer le type d'une version déjà installée.

Vérifier chaque cas dans chaque route serait long et facile à oublier. On a donc fait l'inverse.

## La solution : vérifier le résultat, pas le chemin

1. **`inconsistencies(storage)`** liste tout ce qui ne va pas dans un état des données, quel qu'il soit.
2. **`apply_if_consistent(storage, change)`** fait le changement **à l'essai**, appelle `inconsistencies`, puis :
   - s'il y a un problème, renvoie un 409 avec la liste des problèmes, et **l'essai est annulé** : les données ne sont pas touchées ;
   - sinon, l'essai est gardé.

```python
def apply_if_consistent[T](storage: Storage, change: Callable[[Storage], T]) -> T:
    with storage.dry_run() as dry_run:      # un essai, annulé si une erreur sort du bloc
        result = change(dry_run)     # on fait le changement
        problems = inconsistencies(dry_run)  # on regarde le résultat
        if problems:                    # l'exception sort du bloc « with » : l'essai est annulé
            raise HTTPException(status.HTTP_409_CONFLICT, "Données incohérentes : " + " ; ".join(problems))
    return result                      # c'est bon : le changement est gardé
```

L'essai dépend du stockage ([page 3](03-stockage.md)) : en mémoire, il se fait sur une copie des données ; dans PostgreSQL, dans un « point de sauvegarde » de la transaction, sans rien copier.

Côté route, ça tient en une ligne :

```python
return apply_if_consistent(storage, lambda s: s.clusters.update(cluster_id, changes))
```

La `lambda s: …` est le changement à faire, écrit comme une petite fonction qui reçoit **le stockage de l'essai** : en mémoire, c'est la copie ; dans PostgreSQL, le stockage lui-même.

**Avantage** : une nouvelle règle s'ajoute dans `inconsistencies` (une petite fonction de plus, appelée par `inconsistencies`), et elle est automatiquement vérifiée par toutes les routes qui passent par `apply_if_consistent`.

## Les règles, appelées par `inconsistencies`

Une fonction par règle, pour que chacune reste courte et lisible ; `inconsistencies` les appelle toutes et met leurs messages bout à bout.

| # | Fonction | Règle | Exemple de message |
| --- | --- | --- | --- |
| 0 | `_slots_outside_application` | le module d'un emplacement appartient à l'application de son namespace | « l'emplacement web est réservé au module web, qui n'appartient pas à l'application de son namespace » |
| 1 | `_clusters_of_wrong_type` | un namespace est sur un cluster du même type que son environnement | « l'environnement prod et le cluster cb01 ne sont pas du même type » |
| 2 | `_snapshot_in_prod` | pas de snapshot en prod | « batch 2.4.0-SNAPSHOT est un snapshot : interdit en prod » |
| 3 | `_required_modules` | chaque version qui tourne trouve ses modules requis, dans l'environnement et dans une version compatible | « batch 2.3 a besoin de auth en 1.4 ou plus, mais auth 1.2 tourne en int » |

## « Ce qui tourne » — `versions_in_service`

```python
def versions_in_service(storage: Storage) -> dict[int, list[dict]]:
    last = {}   # emplacement → sa dernière installation
    for installation in storage.installations.list_all():
        current = last.get(installation["slot_id"])
        if current is None or (installation["date"], installation["id"]) > (current["date"], current["id"]):
            last[installation["slot_id"]] = installation
    # … puis on range les versions par environnement
```

Sur chaque emplacement, c'est **la dernière installation** qui tourne : celle de date la plus récente, puis celle saisie en dernier en cas d'égalité. Le résultat est, pour chaque environnement, la liste des versions qui y tournent. C'est sur cette liste que portent les règles 2 et 3.

## Comparer des versions — `versions.py`

On ne peut pas comparer `"1.10"` et `"1.4"` comme du texte : en texte, `"1.10"` vient avant `"1.4"`. `key()` transforme donc un numéro en valeur comparable :

```python
def key(number: str) -> tuple:
    main, _, suffix = number.partition("-")          # "2.3.0-SNAPSHOT" → "2.3.0", "SNAPSHOT"
    numbers = [int(n) for n in main.split(".")]       # → [2, 3, 0]
    while len(numbers) > 1 and numbers[-1] == 0:           # 1.4.0 = 1.4
        numbers.pop()
    return tuple(numbers), 0 if suffix else 1, suffix    # avec suffixe (0) avant sans suffixe (1)
```

Résultat : 1.4 < 1.10 < 2.0, 1.4 = 1.4.0, et 2.3.0-SNAPSHOT < 2.3.0.

`satisfied(number, condition, version, version_max)` dit si un numéro respecte une condition (EXACT, AT_LEAST, BETWEEN). `describe(...)` la met en français pour les messages : « en 1.4 ou plus ».

## Deux saisies en même temps

Avec PostgreSQL, plusieurs exemplaires de l'API peuvent tourner ensemble. Si deux saisies passaient en même temps, chacune pourrait être cohérente seule, mais pas les deux réunies. Pour l'éviter, une requête qui modifie prend un verrou de la base avant de commencer : les écritures passent **une à la fois**, et chaque contrôle voit des données à jour (voir [le stockage](03-stockage.md)).

## La limite connue

`inconsistencies` relit **toutes** les installations, emplacements et namespaces à chaque changement sensible. C'est instantané pour quelques milliers d'éléments. Au-delà, on pourra ne vérifier que l'environnement touché par le changement.

Page suivante : [les règles HTTP](08-http.md).
