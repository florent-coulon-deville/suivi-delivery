# 4. Les schémas — `schemas.py`

## L'idée

Un **schéma** décrit la forme d'un JSON : quels champs, de quel type, avec quelles règles. On les écrit avec **Pydantic**, une bibliothèque qui vérifie automatiquement les données.

Quand une requête arrive, **FastAPI vérifie le JSON avec le schéma avant d'appeler la route**. S'il est invalide, la route n'est même pas exécutée, et la réponse est un 422 qui dit quel champ pose problème.

## Trois schémas par objet

| Schéma | Sert à | Exemple pour les clusters |
| --- | --- | --- |
| `…Creation` | corps d'un `POST`, et d'un `PUT` | `ClusterCreation` : `code` et `label` obligatoires, `is_prod` facultatif |
| `…Update` | corps d'un `PATCH` | `ClusterUpdate` : tout est facultatif |
| sans suffixe | la réponse renvoyée | `Cluster` : les champs, plus l'`id` |

```python
class ClusterCreation(Entry):
    code: Code = Field(examples=["cb01"])
    label: Label
    is_prod: bool = Field(default=False, description="Cluster de prod (vrai) ou de hors prod (faux).")


class ClusterUpdate(Update):
    code: Code | None = None
    label: Label | None = None
    is_prod: bool | None = None


class Cluster(BaseModel):
    id: int
    code: str
    label: str
    is_prod: bool
```

Comment lire une ligne : `name_field: type = value_byéfaut`.

- **Sans `=`**, le champ est **obligatoire** (`label: Label`).
- **Avec `=`**, il est **facultatif** et prend cette valeur s'il est absent (`is_prod: bool = False`).
- **`| None`** veut dire « ou rien ».

## Les types réutilisables

Plutôt que de répéter les mêmes règles dans chaque schéma, on les définit une fois :

```python
Code = Annotated[
    str,                                                          # du texte…
    Field(min_length=1, max_length=30, pattern=r"^[za-z0-9_-]+$"),  # …de 1 à 30 caractères autorisés…
    AfterValidator(str.lower),                                    # …puis converti en minuscules
]
```

- **`Annotated[type, règles…]`** colle des règles à un type.
- **`pattern`** est une *expression régulière* : `^[za-z0-9_-]+$` veut dire « uniquement des lettres, des chiffres, `_` et `-` ».
- **`AfterValidator(str.lower)`** transforme la valeur une fois qu'elle est validée. C'est ainsi que `CB01` devient `cb01`.

| Type | Règle |
| --- | --- |
| `Code` | lettres, chiffres, `-`, `_` ; en minuscules |
| `NamespaceCode` | pareil, mais **sans `_`** (interdit dans un nom de namespace OpenShift) |
| `Trigram` | exactement 3 lettres ou chiffres |
| `Label` | texte de 1 à 100 caractères |
| `VersionNumber` | chiffres séparés par des points, suffixe facultatif (`2.3.0`, `3.0.0-SNAPSHOT`) |

## Les listes fermées (énumérations)

```python
class VersionType(StrEnum):
    RELEASE = "RELEASE"
    SNAPSHOT = "SNAPSHOT"
```

Un champ de type `VersionType` n'accepte que ces valeurs ; toute autre valeur est refusée (422). C'est le cas de `ModuleType`, `ParameterType` et `ConditionType`.

## Les deux classes de base

```python
class Entry(BaseModel):
    model_config = ConfigDict(
        extra="forbid",             # un champ inconnu est refusé (422)
        str_strip_whitespace=True,  # les espaces autour des textes sont retirés
    )
```

Tous les corps de requête héritent d'`Entry`. Une faute de frappe dans un nom de champ (`libele` au lieu de `label`) est donc refusée au lieu d'être ignorée en silence.

```python
class Update(Entry):
    NULLABLES: ClassVar[frozenset[str]] = frozenset()

    @model_validator(mode="after")
    def reject_null(self) -> Self:
        for field in self.model_fields_set:          # les champs réellement envoyés
            if getattr(self, field) is None and field not in self.NULLABLES:
                raise ValueError(f"{champ} ne peut pas être vide (null)")
        return self
```

Les schémas de `PATCH` héritent de `Update`. Tous leurs champs sont facultatifs (`= None`), mais **envoyer `null` sur un champ obligatoire est refusé**. Les seuls champs qu'on a le droit de vider sont listés dans `NULLABLES`, par exemple `promotion_order` pour un environnement :

```python
class EnvironmentUpdate(Update):
    ...
    promotion_order: Order = None
    NULLABLES = frozenset({"promotion_order"})
```

## Ce qu'il faut retenir

- Les schémas vérifient **la forme** : présence, type, format. Ils ne vérifient **pas** que l'application 3 existe, ni qu'un code est déjà pris : ça, ce sont les routes.
- Une règle de format se change **à un seul endroit**.
- `model_dump()` transforme un schéma en dictionnaire, qui est ce que le stockage attend.

Page suivante : [les routes](05-routes.md).
