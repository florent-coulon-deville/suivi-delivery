# 9. Les tests — `tests/`

## Le principe

Un test est une fonction qui **appelle l'API comme le ferait un utilisateur**, puis **vérifie la réponse** avec `assert` (« affirmer »). Si une affirmation est fausse, le test échoue et pytest dit lequel et pourquoi.

```bash
uv run pytest          # tous les tests (depuis backend/)
uv run pytest -k loop   # seulement ceux dont le nom contient « boucle »
```

**Deux façons de les lancer.** Sans réglage, les données sont **en mémoire** : rapide, rien à installer. Avec la variable `TESTS_DB_FILE`, **les mêmes tests** tournent sur un vrai fichier SQLite, effacé avant chaque test (son nom doit finir par `_tests.sqlite`). Les commandes sont dans [sqlite.md](../sqlite.md#les-tests). La CI fait les deux.

## `conftest.py` : les outils partagés

pytest charge ce fichier automatiquement. Il fournit des **fixtures** : des éléments préparés à l'avance, qu'un test reçoit simplement en les nommant en paramètre.

```python
@pytest.fixture
def client() -> TestClient:
    """Un client HTTP de test sur une application neuve (stockage vide) à chaque test."""
    return TestClient(create_application())
```

- Un test qui écrit `def test_x(client):` reçoit un client branché sur une **application neuve** : chaque test part de données vides.
- **`TestClient`** envoie de vraies requêtes HTTP à l'application, sans démarrer de serveur.

Les autres fixtures préparent des données :

- **`dataset`** : une application, deux environnements (int et prod) et deux clusters (hors prod et prod) ;
- **`deployment`** : tout ce qu'il faut pour une installation (namespace, module, version, paramètres, emplacement).

Une fixture peut en utiliser une autre : `deployment` reçoit `dataset`, qui reçoit `client`.

**`test_storage.py`** vérifie le stockage lui-même. Certains de ses tests n'ont de sens qu'avec une base : ils sont marqués `@with_sqlite` et sautés en mémoire (`skipped` dans le résumé de pytest). Par exemple : après un « redémarrage » (une nouvelle application sur la même base, sans la vider), tout est retrouvé ; une erreur imprévue annule toute la requête ; la base refuse un doublon que l'API aurait laissé passer.

La fonction **`create(client, "clusters", code="cb01", label="…")`** fait un POST qui doit réussir (201) et renvoie l'élément créé. Elle rend les tests plus courts.

## Un test, ligne par ligne

```python
@LISTS   # = pytest.mark.parametrize("ressource", ["environnements", "clusters"])
def test_create_201_with_location_and_lowercase_code(client, resource):
    answer = client.post(f"/api/{resource}", json={"code": "ABC1", "label": "  Libellé  "})
    assert answer.status_code == 201
    assert answer.json()["code"] == "abc1"            # converti en minuscules
    assert answer.json()["label"] == "Libellé"      # espaces retirés
    assert answer.headers["Location"] == f"/api/{resource}/1"
```

- **`parametrize`** joue le même test plusieurs fois avec des valeurs différentes : ici, une fois pour les environnements et une fois pour les clusters.
- Le nom du test dit ce qu'il vérifie. Quand il échoue, on sait tout de suite ce qui est cassé.

## Comment les fichiers sont organisés

| Fichier | Vérifie |
| --- | --- |
| `test_lists.py` | environnements et clusters (les mêmes tests joués sur les deux) |
| `test_applications.py`, `test_namespaces.py`, `test_modules.py`… | une ressource par fichier : création, unicité, références, modification, suppression |
| `test_dependencies.py`, `test_compatibilities.py` | dépendances, boucles, conditions de version et refus des installations incompatibles |
| `test_rules.py` | les règles d'ensemble : type de cluster, pas de snapshot en prod, modules requis présents |
| `test_http.py` | HEAD, OPTIONS, Allow, PUT, et les codes 400, 404, 415 et 422 |

## Pourquoi c'est important

Avant chaque envoi sur GitHub, les tests rejouent tous les comportements, plus de 200 cas, en quelques secondes. Une modification qui casse quelque chose ailleurs est repérée tout de suite.

Page suivante : [recette : ajouter une ressource](10-ajouter-une-ressource.md).
