// Forme des données renvoyées par l'API (voir docs/api.md et backend/app/schemas.py).
// TypeScript s'en sert pour vérifier, avant l'exécution, qu'on n'utilise pas un champ
// qui n'existe pas ou avec le mauvais type.

export type Environment = { id: number; code: string; label: string; is_prod: boolean; promotion_order: number | null };
export type Cluster = { id: number; code: string; label: string; is_prod: boolean };
/** Zone réseau : code gardé en minuscules par l'API, affiché en majuscules (toUppercase). */
export type NetworkZone = { id: number; code: string; label: string };
export type Application = { id: number; identifier: string; name: string; trigram: string };
export type Namespace = {
  id: number;
  application_id: number;
  environment_id: number;
  cluster_id: number;
  suffix: string;
  network_zone_id: number;
  name: string; // calculé par l'API : trigramme-identifiant-environnement-suffixe
};
export type ModuleType = "CAPABILITY" | "BUSINESS_PROJECT";
export type Module = { id: number; application_id: number; code: string; name: string; type: ModuleType };
export type Dependency = { id: number; module_id: number; depends_on_id: number };
export type VersionType = "RELEASE" | "SNAPSHOT";
export type ModuleVersion = { id: number; module_id: number; number: string; type: VersionType };
export type Compatibility = {
  id: number;
  module_version_id: number;
  required_module_id: number;
  condition: "EXACT" | "AT_LEAST" | "BETWEEN";
  version: string;
  version_max: string | null;
};
export type ParameterType = "TECHNICAL" | "APPLICATION";
export type Parameter = { id: number; module_id: number; name: string; type: ParameterType; namespace_ids: number[] };
export type Slot = { id: number; namespace_id: number; module_id: number; release_name: string };
export type Installation = {
  id: number;
  slot_id: number;
  module_version_id: number;
  technical_parameter_id: number;
  application_parameter_id: number;
  date: string; // date ISO, ex. 2026-10-09T10:45:00Z
};

/** Toutes les listes de l'API, rangées par nom de ressource (tel qu'il apparaît dans l'adresse). */
export type Data = {
  environments: Environment[];
  clusters: Cluster[];
  "network-zones": NetworkZone[];
  applications: Application[];
  namespaces: Namespace[];
  modules: Module[];
  dependencies: Dependency[];
  "module-versions": ModuleVersion[];
  compatibilities: Compatibility[];
  parameters: Parameter[];
  slots: Slot[];
  installations: Installation[];
};
export type Resource = keyof Data;
export const RESOURCES: Resource[] = [
  "environments",
  "clusters",
  "network-zones",
  "applications",
  "namespaces",
  "modules",
  "dependencies",
  "module-versions",
  "compatibilities",
  "parameters",
  "slots",
  "installations",
];

/** Structure (paramétrage général) : seul l'administrateur la modifie. Le reste (versions,
 *  paramètres, installations) est saisi par les développeurs (rôle EDITOR). Comme dans l'API
 *  (backend/app/main.py). */
export const RESOURCES_STRUCTURE: ReadonlySet<Resource> = new Set<Resource>([
  "environments",
  "clusters",
  "network-zones",
  "applications",
  "namespaces",
  "modules",
  "dependencies",
  "compatibilities",
  "slots",
]);

/** Valeurs des listes fermées : { ModuleType: ["CAPABILITY", "BUSINESS_PROJECT"], VersionType: [...], ... }. */
export type Enumerations = Record<string, string[]>;

/** Un rôle de l'outil (dans Keycloak) ; null : le compte ne peut rien faire dans l'outil. */
export type AccountRole = "VIEWER" | "EDITOR" | "ADMIN";

/** Un compte (voir /api/accounts ; gardé par Keycloak) : jamais de mot de passe ni de clé. */
export type Account = {
  id: string; // identifiant Keycloak
  identifier: string;
  name: string;
  kind: "PERSON" | "PROGRAM";
  role: AccountRole | null;
  active: boolean;
};

/** La personne (ou le programme) connectée (voir /api/me), et ses préférences. */
export type Me = {
  identifier: string;
  name: string;
  kind: "PERSON" | "PROGRAM";
  role: AccountRole | null;
  theme: "AUTO" | "LIGHT" | "DARK"; // thème de couleurs de l'interface (Mon compte → Apparence)
};

/** Une ligne du journal des actions (voir /api/audit-log) : qui a créé, modifié ou supprimé quoi, et quand. */
export type AuditEntry = {
  id: number;
  date: string;
  author_id: string | null; // identifiant Keycloak de l'auteur
  author: string; // identifiant de connexion (ou du programme) au moment de la saisie
  author_kind: "PERSON" | "PROGRAM";
  object: string; // nom de la table : « installations », « comptes »…
  object_id: string;
  action: "CREATE" | "UPDATE" | "DELETE";
  before: Record<string, unknown> | null;
  after: Record<string, unknown> | null;
};

/** Résultat d'un import de la configuration, ou de son essai (voir PATCH /api/configuration). */
export type ImportReport = {
  dry_run: boolean; // vrai : aperçu seulement, rien n'est enregistré
  applied: boolean; // vrai : les changements sont enregistrés
  sheets: { sheet: string; additions: number; updates: number; unchanged: number }[];
  changes: { sheet: string; row: number; action: "ADD" | "UPDATE"; object: string; details: string[] }[];
  problems: { sheet: string | null; row: number | null; message: string }[]; // s'il y en a, rien n'est importé
};
