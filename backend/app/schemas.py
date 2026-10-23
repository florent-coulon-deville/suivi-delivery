"""Forme des données échangées avec l'API (JSON), décrite avec Pydantic.

Pydantic vérifie automatiquement chaque requête reçue : si un champ manque, a un
mauvais format ou est inconnu, FastAPI répond 422 sans même appeler la route.

Pour chaque objet, trois schémas :
  …Creation      corps d'un POST  : tous les champs obligatoires
  …Modification  corps d'un PATCH : uniquement les champs à changer
  (sans suffixe) réponse renvoyée par l'API, avec l'identifiant technique « id »
"""

from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated, ClassVar, Self

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, model_validator

# --- Énumérations -----------------------------------------------------------


class VersionType(StrEnum):
    """Type d'une version de module."""

    RELEASE = "RELEASE"  # version définitive
    SNAPSHOT = "SNAPSHOT"  # version de travail


class ModuleType(StrEnum):
    """Type d'un module."""

    CAPABILITY = "CAPABILITY"  # brique du socle, commune
    BUSINESS_PROJECT = "BUSINESS_PROJECT"  # programme propre à un métier


class ParameterType(StrEnum):
    """Type d'un paramètre."""

    TECHNICAL = "TECHNICAL"
    APPLICATION = "APPLICATION"


class AccountKind(StrEnum):
    """Qui utilise un compte (comptes gérés dans Keycloak, voir app/directory.py)."""

    PERSON = "PERSON"  # se connecte avec un mot de passe, sur la page de connexion
    PROGRAM = "PROGRAM"  # script, outil de déploiement… : se connecte avec une clé (client credentials)


class Role(StrEnum):
    """Ce qu'un compte a le droit de faire ; chaque rôle comprend les droits du précédent."""

    VIEWER = "VIEWER"  # lire les données
    EDITOR = "EDITOR"  # lire, et saisir les livraisons (versions, paramètres, installations)
    ADMIN = "ADMIN"  # tout : aussi la structure (paramétrage général) et les comptes


class Theme(StrEnum):
    """Thème de couleurs de l'interface, choisi par chaque personne (« Mon compte » → Apparence)."""

    AUTO = "AUTO"  # comme le réglage de l'ordinateur
    LIGHT = "LIGHT"
    DARK = "DARK"


class AuthorKind(StrEnum):
    """Qui a fait une saisie notée au journal."""

    PERSON = "PERSON"
    PROGRAM = "PROGRAM"


class AuditAction(StrEnum):
    """Ce qu'une saisie a fait à un objet (journal des actions, app/audit_log.py)."""

    CREATE = "CREATE"
    UPDATE = "UPDATE"
    DELETE = "DELETE"


# --- Types de champs réutilisables ------------------------------------------
# Tous les codes sont convertis en minuscules : « INT » et « int » sont le même code.

Code = Annotated[
    str,
    Field(
        min_length=1,
        max_length=30,
        pattern=r"^[A-Za-z0-9_-]+$",
        description="Lettres, chiffres, - et _ ; converti en minuscules.",
    ),
    AfterValidator(str.lower),
]

# Codes qui entrent dans le nom d'un namespace OpenShift : pas de « _ », interdit dans ces noms.
NamespaceCode = Annotated[
    str,
    Field(
        min_length=1,
        max_length=30,
        pattern=r"^[A-Za-z0-9-]+$",
        description="Lettres, chiffres et - ; converti en minuscules.",
    ),
    AfterValidator(str.lower),
]

Trigram = Annotated[
    str,
    Field(
        pattern=r"^[A-Za-z0-9]{3}$",
        description="Exactement 3 lettres ou chiffres ; converti en minuscules.",
        examples=["abc"],
    ),
    AfterValidator(str.lower),
]

Label = Annotated[str, Field(min_length=1, max_length=100)]


class Entry(BaseModel):
    """Base des corps de requête."""

    model_config = ConfigDict(
        extra="forbid",  # un champ inconnu est refusé (422)
        str_strip_whitespace=True,  # les espaces autour des textes sont retirés
    )


class Update(Entry):
    """Base des corps de PATCH : tous les champs sont facultatifs (« = None »).

    Un champ absent n'est pas modifié. Un champ envoyé à null n'est accepté que s'il est
    listé dans NULLABLES (il est alors vidé) ; sinon la requête est refusée (422).
    """

    NULLABLES: ClassVar[frozenset[str]] = frozenset()

    @model_validator(mode="after")
    def reject_null(self) -> Self:
        for field in self.model_fields_set:
            if getattr(self, field) is None and field not in self.NULLABLES:
                raise ValueError(f"{field} ne peut pas être vide (null)")
        return self


# --- Environnement ----------------------------------------------------------

PromotionOrder = Annotated[
    int | None,
    Field(
        ge=1,
        description="Place dans la chaîne de promotion (int=1, rec=2…). "
        "Pour information : aucun ordre de déploiement n'est imposé.",
    ),
]


class EnvironmentCreation(Entry):
    code: NamespaceCode = Field(examples=["int"])
    label: Label
    is_prod: bool = False
    promotion_order: PromotionOrder = None


class EnvironmentUpdate(Update):
    code: NamespaceCode | None = None
    label: Label | None = None
    is_prod: bool | None = None
    promotion_order: PromotionOrder = None  # null autorisé : retire l'ordre

    NULLABLES = frozenset({"promotion_order"})


class Environment(BaseModel):
    id: int
    code: str
    label: str
    is_prod: bool
    promotion_order: int | None


# --- Cluster ----------------------------------------------------------------


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


# --- Zone réseau ------------------------------------------------------------


class NetworkZoneCreation(Entry):
    code: Code = Field(examples=["interne"], description="Gardé en minuscules ; l'interface l'affiche en majuscules.")
    label: Label


class NetworkZoneUpdate(Update):
    code: Code | None = None
    label: Label | None = None


class NetworkZone(BaseModel):
    id: int
    code: str
    label: str


# --- Application ------------------------------------------------------------


class ApplicationCreation(Entry):
    identifier: NamespaceCode = Field(description="Unique. Entre dans le nom des namespaces.")
    name: Label
    trigram: Trigram


class ApplicationUpdate(Update):
    identifier: NamespaceCode | None = None
    name: Label | None = None
    trigram: Trigram | None = None


class Application(BaseModel):
    id: int
    identifier: str
    name: str
    trigram: str


# --- Namespace --------------------------------------------------------------


class NamespaceCreation(Entry):
    application_id: int
    environment_id: int
    cluster_id: int
    suffix: NamespaceCode = Field(examples=["batch"])
    network_zone_id: int


class NamespaceUpdate(Update):
    application_id: int | None = None
    environment_id: int | None = None
    cluster_id: int | None = None
    suffix: NamespaceCode | None = None
    network_zone_id: int | None = None


class Namespace(BaseModel):
    id: int
    name: str = Field(description="Calculé : trigramme-identifiant-environnement-suffixe, en minuscules.")
    application_id: int
    environment_id: int
    cluster_id: int
    suffix: str
    network_zone_id: int


# --- Module -----------------------------------------------------------------


class ModuleCreation(Entry):
    application_id: int
    code: Code
    name: Label
    type: ModuleType


class ModuleCreationWithSlots(ModuleCreation):
    """Corps du POST seulement (pas du PUT) : la création peut aussi poser les emplacements du module."""

    with_slots: bool = Field(
        default=False,
        description="Crée un emplacement pour ce module dans chaque namespace de son application "
        "(nom de release = code du module, « _ » remplacé par « - »). Tout ou rien.",
    )


class ModuleUpdate(Update):
    application_id: int | None = None
    code: Code | None = None
    name: Label | None = None
    type: ModuleType | None = None


class Module(BaseModel):
    id: int
    application_id: int
    code: str
    name: str
    type: ModuleType


# --- Dépendance entre modules -----------------------------------------------
# « Le module A dépend du module B », y compris entre applications différentes.
# Un lien se crée ou se supprime, mais ne se modifie pas.
# Les conditions de version sont portées par les compatibilités (voir plus bas).


class DependencyCreation(Entry):
    module_id: int = Field(description="Le module qui a besoin d'un autre.")
    depends_on_id: int = Field(description="Le module dont il a besoin.")


class Dependency(BaseModel):
    id: int
    module_id: int
    depends_on_id: int


# ============================================================================
# Déploiement
# ============================================================================

# Numéro d'une version de module : il doit pouvoir être comparé (1.4 < 1.10 < 2.0).
# Chiffres séparés par des points, suivis éventuellement d'un suffixe : 2.3.0, 1.4, 3.0.0-SNAPSHOT.
VersionNumber = Annotated[
    str,
    Field(
        min_length=1,
        max_length=50,
        pattern=r"^[0-9]+(\.[0-9]+)*(-[0-9A-Za-z.]+)?$",
        description="Chiffres séparés par des points, suffixe facultatif : 2.3.0, 3.0.0-SNAPSHOT.",
        examples=["2.3.0"],
    ),
]


# --- Version de module ------------------------------------------------------


class ModuleVersionCreation(Entry):
    module_id: int
    number: VersionNumber
    type: VersionType = VersionType.SNAPSHOT  # snapshot par défaut


class ModuleVersionUpdate(Update):
    module_id: int | None = None
    number: VersionNumber | None = None
    type: VersionType | None = None


class ModuleVersion(BaseModel):
    id: int
    module_id: int
    number: str
    type: VersionType


# --- Paramètre --------------------------------------------------------------


# Nom d'un paramètre : texte libre (une version comme « 2.3 », ou tout autre chose), en minuscules.
ParameterName = Annotated[
    str,
    Field(
        min_length=1,
        max_length=50,
        description="Texte libre (ex. une version : 2.3), unique par module et par type ; converti en minuscules.",
        examples=["2.3"],
    ),
    AfterValidator(str.lower),
]


class ParameterCreation(Entry):
    module_id: int = Field(description="Le module que ce paramètre configure.")
    name: ParameterName
    type: ParameterType
    namespace_ids: list[int] = Field(default=[], description="Namespaces (de l'application du module) affectés.")


class ParameterUpdate(Update):
    module_id: int | None = None
    name: ParameterName | None = None
    type: ParameterType | None = None
    namespace_ids: list[int] | None = Field(
        default=None, description="Remplace toute la liste des namespaces affectés."
    )


class Parameter(BaseModel):
    id: int
    module_id: int
    name: str
    type: ParameterType
    namespace_ids: list[int]


# --- Emplacement ------------------------------------------------------------


class SlotCreation(Entry):
    namespace_id: int
    module_id: int = Field(description="Le seul module qui pourra être installé sur cet emplacement.")
    release_name: NamespaceCode = Field(examples=["batch-paie"])


class SlotUpdate(Update):
    namespace_id: int | None = None
    module_id: int | None = Field(default=None, description="Modifiable seulement tant que l'emplacement est vide.")
    release_name: NamespaceCode | None = None


class Slot(BaseModel):
    id: int
    namespace_id: int
    module_id: int
    release_name: str


# --- Création groupée de namespaces -------------------------------------------
# Un même namespace sur plusieurs clusters d'un coup, avec, par défaut, un emplacement
# par module de l'application. Tout ou rien.


class NamespaceBatchCreation(Entry):
    application_id: int
    environment_id: int
    cluster_ids: list[int] = Field(min_length=1, description="Un namespace est créé sur chacun de ces clusters.")
    suffix: NamespaceCode = Field(examples=["batch"])
    network_zone_id: int
    with_slots: bool = Field(
        default=True,
        description="Crée dans chaque namespace un emplacement par module de l'application "
        "(nom de release = code du module, « _ » remplacé par « - »).",
    )

    @model_validator(mode="after")
    def distinct_clusters(self) -> Self:
        if len(set(self.cluster_ids)) != len(self.cluster_ids):
            raise ValueError("Un même cluster est donné deux fois")
        return self


class NamespaceBatch(BaseModel):
    namespaces: list[Namespace]
    slots: list[Slot]


# --- Compatibilité ----------------------------------------------------------
# « La version 2.3 du batch de paie a besoin de l'authentification en 1.4 ou plus. »
# Portée par une version de module, pour l'un des modules dont ce module dépend.


class ConditionType(StrEnum):
    """Comment la version du module requis est contrainte (bornes comprises)."""

    EXACT = "EXACT"  # précisément « version »
    AT_LEAST = "AT_LEAST"  # « version » ou plus récente
    BETWEEN = "BETWEEN"  # de « version » à « version_max »


class CompatibilityCreation(Entry):
    module_version_id: int = Field(description="La version qui a un besoin (ex. batch de paie 2.3).")
    required_module_id: int = Field(description="Le module dont elle a besoin (ex. authentification).")
    condition: ConditionType
    version: VersionNumber = Field(description="Version exacte, ou borne basse.")
    version_max: VersionNumber | None = Field(default=None, description="Borne haute : uniquement pour BETWEEN.")


class CompatibilityUpdate(Update):
    condition: ConditionType | None = None
    version: VersionNumber | None = None
    version_max: VersionNumber | None = None

    NULLABLES = frozenset({"version_max"})  # null : retire la borne haute


class Compatibility(BaseModel):
    id: int
    module_version_id: int
    required_module_id: int
    condition: ConditionType
    version: str
    version_max: str | None


# --- Installation -----------------------------------------------------------
# Une installation est un fait passé : on la crée, on la lit, on peut la supprimer
# (erreur de saisie), mais on ne la modifie pas.


class InstallationCreation(Entry):
    slot_id: int
    module_version_id: int
    technical_parameter_id: int = Field(description="Paramètre TECHNICAL du module, affecté au namespace.")
    application_parameter_id: int = Field(description="Paramètre APPLICATION du module, affecté au namespace.")
    date: datetime = Field(
        default_factory=lambda: datetime.now(UTC), description="Date de l'installation ; maintenant si absente."
    )


class Installation(BaseModel):
    id: int
    slot_id: int
    module_version_id: int
    technical_parameter_id: int
    application_parameter_id: int
    date: datetime


# --- Comptes (gérés dans Keycloak, voir app/directory.py) ---------------------

Password = Annotated[
    str,
    Field(
        min_length=12,
        max_length=128,
        description="12 caractères au moins, différent de l'identifiant.",
        examples=["a-strong-password"],
    ),
]


class AccountCreation(Entry):
    identifier: Code = Field(examples=["paul"])
    name: Label = Field(examples=["Paul Martin"])
    kind: AccountKind
    role: Role
    password: Password | None = Field(
        default=None,
        description="PERSON : mot de passe PROVISOIRE, obligatoire (elle en choisit un nouveau à sa première "
        "connexion). Interdit pour un PROGRAM (sa clé est générée).",
    )

    @model_validator(mode="after")
    def secret_according_to_kind(self) -> Self:
        if self.kind == AccountKind.PERSON and self.password is None:
            raise ValueError("password est obligatoire pour une PERSON")
        if self.kind == AccountKind.PROGRAM and self.password is not None:
            raise ValueError("un PROGRAM n'a pas de mot de passe : sa clé est générée par l'outil")
        if self.password is not None and self.password.lower() == self.identifier:
            raise ValueError("le mot de passe doit être différent de l'identifiant")
        return self


class AccountUpdate(Update):
    name: Label | None = None
    role: Role | None = None
    active: bool | None = Field(default=None, description="Faux : le compte ne peut plus se connecter.")
    password: Password | None = Field(
        default=None,
        description="Nouveau mot de passe PROVISOIRE (PERSON seulement) : à changer à la prochaine connexion.",
    )


class Account(BaseModel):
    """Un compte, tel que l'API le montre : jamais de mot de passe ni de clé."""

    id: str = Field(description="Identifiant du compte dans Keycloak.")
    identifier: str
    name: str
    kind: AccountKind
    role: Role | None = Field(description="Aucun : le compte ne peut rien faire dans l'outil.")
    active: bool


class CreatedAccount(Account):
    key: str | None = Field(
        default=None, description="Clé d'un PROGRAM : affichée UNE SEULE FOIS, à noter tout de suite."
    )


class NewKey(BaseModel):
    key: str = Field(description="Nouvelle clé du PROGRAM : affichée UNE SEULE FOIS. L'ancienne ne marche plus.")


class Me(BaseModel):
    """Le compte connecté (GET /api/me), tel que son jeton le décrit, et ses préférences."""

    identifier: str = Field(description="Identifiant de connexion (PERSON), ou du programme.")
    name: str
    kind: AccountKind
    role: Role | None
    theme: Theme = Field(default=Theme.AUTO, description="Thème de couleurs de l'interface.")


class MyPreferences(Update):
    """Corps de PATCH /api/me : les préférences que chacun règle lui-même."""

    theme: Theme | None = None


# --- Journal des actions (voir app/audit_log.py) ------------------------------


class AuditEntry(BaseModel):
    """Une saisie acceptée : qui, quand, sur quel objet, et l'objet avant / après."""

    id: int
    date: datetime
    author_id: str | None = Field(description="Identifiant Keycloak de l'auteur (il a pu être supprimé depuis).")
    author: str = Field(description="Identifiant de connexion de l'auteur (ou du programme), au moment de la saisie.")
    author_kind: AuthorKind
    object: str = Field(examples=["installations"], description="Nature de l'objet : le nom de sa table (ou comptes).")
    object_id: str = Field(description="Identifiant de l'objet (un nombre, ou l'identifiant Keycloak d'un compte).")
    action: AuditAction
    before: dict | None = Field(description="L'objet avant la saisie (absent pour une création).")
    after: dict | None = Field(description="L'objet après la saisie (absent pour une suppression).")


# --- Erreurs ----------------------------------------------------------------


class Error(BaseModel):
    """Corps des réponses d'erreur 404, 409 et 422 (référence inexistante)."""

    detail: str


# --- Import de la configuration (voir app/import_configuration.py) -----------


class ImportAction(StrEnum):
    """Ce que l'import fait (ou ferait, à l'essai) d'une ligne du fichier."""

    ADD = "ADD"
    UPDATE = "UPDATE"


class SheetSummary(BaseModel):
    """Le compte des lignes d'un onglet, selon ce que l'import en fait."""

    sheet: str
    additions: int = 0
    updates: int = 0
    unchanged: int = 0


class ImportChange(BaseModel):
    """Un objet ajouté ou modifié par l'import."""

    sheet: str
    row: int = Field(description="Numéro de la ligne dans l'onglet (comme dans le tableur).")
    action: ImportAction
    object: str = Field(examples=["paiement / batch-paie"], description="L'objet, désigné par ses codes.")
    details: list[str] = Field(description="Pour une modification : « champ : avant → après ».")


class ImportProblem(BaseModel):
    """Ce qui empêche l'import : une ligne refusée, ou une règle d'ensemble cassée."""

    sheet: str | None = Field(description="Absent pour une règle d'ensemble (vérifiée sur tout le fichier).")
    row: int | None
    message: str


class ImportReport(BaseModel):
    """Résultat d'un import, ou de son essai (aperçu)."""

    dry_run: bool = Field(description="Vrai : aperçu seulement, rien n'est enregistré.")
    applied: bool = Field(description="Vrai : les changements sont enregistrés.")
    sheets: list[SheetSummary]
    changes: list[ImportChange]
    problems: list[ImportProblem] = Field(description="S'il y en a, rien n'est importé.")
