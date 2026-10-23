// Description des objets que l'on saisit : leurs champs, et comment les afficher.
//
// Les écrans de saisie sont génériques : ils lisent cette description pour construire la
// liste et le formulaire de chaque objet. Ajouter un champ ou un objet se fait donc ici.
import { toUppercase, asText, formatDate } from "@/lib/format";
import type {
  Compatibility,
  Dependency,
  Data,
  Slot,
  Installation,
  Environment,
  Module,
  Namespace,
  Parameter,
  Resource,
  ModuleVersion,
  Cluster,
} from "@/lib/types";

/** Un élément de n'importe quelle ressource, lu champ par champ. */
export type Element = { id: number } & Record<string, unknown>;

/** Valeurs d'un formulaire : du texte (listes, nombres compris), une case à cocher, ou plusieurs identifiants. */
export type Value = string | boolean | number[];
export type Values = Record<string, Value>;

/** Données brutes + accès par identifiant, partagés par les écrans de saisie. */
export type Context = {
  d: Data;
  byId: (resource: Resource, id: unknown) => Element | undefined;
};

export function buildContext(d: Data): Context {
  const index = new Map(
    (Object.entries(d) as [Resource, Element[]][]).map(([resource, list]) => [
      resource,
      new Map(list.map((e) => [e.id, e])),
    ]),
  );
  return { d, byId: (resource, id) => index.get(resource)?.get(Number(id)) };
}

/**
 * Un champ :
 *   nom          nom du champ dans l'API (ex. "application_id")
 *   libelle      ce qu'on affiche
 *   type         texte | nombre | booleen | liste (valeurs fixes) | reference (un autre objet) | references (plusieurs)
 *   obligatoire  le champ doit être rempli
 *   enumeration  pour « liste » : nom de la liste fermée dans l'API (ex. "ModuleType")
 *   ressource    pour « reference(s) » : l'objet visé (ex. "applications")
 *   filtre       pour « reference(s) » : vrai si l'élément est proposé, vu les autres valeurs du formulaire
 *   defaut       valeur par défaut à la création
 *   visible      vrai si le champ doit être affiché (ex. version_max seulement pour BETWEEN)
 *   aide         petite explication sous le champ
 *   majuscules   texte affiché en majuscules (saisie et tableau) ; l'API le garde en minuscules
 */
export type Field = {
  name: string;
  label: string;
  type: "text" | "count" | "boolean" | "list" | "reference" | "references";
  required?: boolean;
  enumeration?: string;
  resource?: Resource;
  filter?: (element: Element, values: Values, ctx: Context) => boolean;
  fallback?: Value;
  visible?: (values: Values) => boolean;
  help?: string;
  uppercase?: boolean;
};

export type Column = {
  title: string;
  value: (element: Element) => string; // texte de la cellule (sert aussi à la recherche)
  code?: boolean; // affiché en police « code »
  labels?: (element: Element) => string[]; // plusieurs valeurs : une étiquette chacune
};

// Valeurs des listes fermées, telles qu'on les affiche (l'API, elle, reçoit le code : « BUSINESS_PROJECT »).
const VALUE_LABELS: Record<string, string> = {
  CAPABILITY: "Capacité",
  BUSINESS_PROJECT: "Projet métier",
  RELEASE: "Release",
  SNAPSHOT: "Snapshot",
  TECHNICAL: "Technique",
  APPLICATION: "Applicatif",
  EXACT: "Exactement",
  AT_LEAST: "À partir de",
  BETWEEN: "Entre deux versions",
};

/** Valeur d'une liste fermée en clair ; une valeur inconnue ici reste telle quelle. */
export const valueLabel = (value: string): string => VALUE_LABELS[value] ?? value;

export type ResourceDescription = {
  key: Resource;
  title: string;
  group: string;
  newLabel: string;
  help: string;
  fields: Field[];
  extraColumns?: Column[];
  editable?: boolean; // false : pas de « Modifier » (l'API refuse PUT / PATCH)
  guidedForm?: boolean; // formulaire pas à pas (InstallationForm.tsx)
  // Création groupée : à la création, ces champs remplacent « champs » et le formulaire écrit
  // dans POST /api/<objet>/lot (plusieurs éléments d'un coup, tout ou rien). La modification
  // garde « champs » (un élément à la fois).
  batchCreationFields?: Field[];
  // Champs ajoutés au formulaire à la création seulement (ni en modification, ni dans le tableau).
  extraCreationFields?: Field[];
};

/** Libellé lisible d'un élément, pour les listes déroulantes et les tableaux. */
export function label(resource: Resource, element: Element | undefined, ctx: Context): string {
  if (!element) return "—";
  const e = element as never; // lu selon sa ressource ci-dessous
  switch (resource) {
    case "environments":
      return (e as Environment).code;
    case "clusters": {
      const c = e as { code: string; is_prod: boolean };
      return `${c.code} (${c.is_prod ? "prod" : "hors prod"})`;
    }
    case "network-zones":
      return toUppercase((e as { code: string }).code);
    case "applications":
      return (e as { identifier: string }).identifier;
    case "namespaces": {
      // Le même nom peut exister sur plusieurs clusters : le cluster le précise.
      const n = e as Namespace;
      return `${n.name} · ${(ctx.byId("clusters", n.cluster_id) as Cluster | undefined)?.code ?? "?"}`;
    }
    case "modules": {
      const m = e as Module;
      return `${m.code} · ${ctx.byId("applications", m.application_id)?.identifier}`;
    }
    case "module-versions": {
      const v = e as ModuleVersion;
      return `${ctx.byId("modules", v.module_id)?.code} ${v.number}`;
    }
    case "parameters": {
      const p = e as Parameter;
      return `${p.name} (${p.type.toLowerCase()}) · ${ctx.byId("modules", p.module_id)?.code}`;
    }
    case "slots": {
      const em = e as Slot;
      return `${em.release_name} · ${label("namespaces", ctx.byId("namespaces", em.namespace_id), ctx)}`;
    }
    case "dependencies": {
      const dep = e as Dependency;
      return `${ctx.byId("modules", dep.module_id)?.code} → ${ctx.byId("modules", dep.depends_on_id)?.code}`;
    }
    case "compatibilities": {
      const c = e as Compatibility;
      const version = label("module-versions", ctx.byId("module-versions", c.module_version_id), ctx);
      return `${version} → ${ctx.byId("modules", c.required_module_id)?.code}`;
    }
    case "installations": {
      const i = e as Installation;
      const version = ctx.byId("module-versions", i.module_version_id);
      return `${label("module-versions", version, ctx)} sur ${ctx.byId("slots", i.slot_id)?.release_name}`;
    }
    default:
      return `#${element.id}`;
  }
}

// Filtres réutilisés : ne proposer que ce qui a du sens avec les autres valeurs du formulaire.
const sameApplication = (element: Element, values: Values) =>
  !values.application_id || element.application_id === Number(values.application_id);

/** Namespaces de l'application du module choisi (paramètres). */
const moduleApplication = (namespace: Element, values: Values, ctx: Context) => {
  const module = ctx.byId("modules", values.module_id);
  return !module || namespace.application_id === module.application_id;
};

const clusterOfRightType = (cluster: Element, values: Values, ctx: Context) => {
  const environment = ctx.byId("environments", values.environment_id);
  return !environment || cluster.is_prod === environment.is_prod;
};

export const GROUPS = ["Listes", "Socle", "Déploiement"];

export const DESCRIPTIONS: ResourceDescription[] = [
  // ----- Listes -----
  {
    key: "environments",
    title: "Environnements",
    group: "Listes",
    newLabel: "Nouvel environnement",
    help: "La chaîne de promotion : int, rec, preprod, prod…",
    fields: [
      { name: "code", label: "Code", type: "text", required: true, help: "Lettres, chiffres et -. Ex. : int" },
      { name: "label", label: "Libellé", type: "text", required: true },
      { name: "is_prod", label: "Environnement de production", type: "boolean", fallback: false },
      { name: "promotion_order", label: "Ordre de promotion", type: "count", help: "Pour information et tri : 1 = premier." },
    ],
  },
  {
    key: "clusters",
    title: "Clusters",
    group: "Listes",
    newLabel: "Nouveau cluster",
    help: "Les clusters OpenShift, de prod ou de hors prod.",
    fields: [
      { name: "code", label: "Code", type: "text", required: true, help: "Ex. : cb01" },
      { name: "label", label: "Libellé", type: "text", required: true },
      { name: "is_prod", label: "Cluster de production", type: "boolean", fallback: false },
    ],
  },
  {
    key: "network-zones",
    title: "Zones réseau",
    group: "Listes",
    newLabel: "Nouvelle zone réseau",
    help: "Les zones réseau des namespaces : INTERNE, PARTENAIRES…",
    fields: [
      { name: "code", label: "Code", type: "text", required: true, uppercase: true, help: "Ex. : INTERNE" },
      { name: "label", label: "Libellé", type: "text", required: true },
    ],
  },

  // ----- Socle -----
  {
    key: "applications",
    title: "Applications",
    group: "Socle",
    newLabel: "Nouvelle application",
    help: "Identifiant unique ; le trigramme peut être partagé.",
    fields: [
      { name: "identifier", label: "Identifiant", type: "text", required: true, help: "Lettres, chiffres et -." },
      { name: "name", label: "Nom", type: "text", required: true },
      { name: "trigram", label: "Trigramme", type: "text", required: true, help: "3 lettres ou chiffres." },
    ],
  },
  {
    key: "namespaces",
    title: "Namespaces",
    group: "Socle",
    newLabel: "Nouveau namespace",
    help: "Le nom est calculé : trigramme-identifiant-environnement-suffixe.",
    extraColumns: [{ title: "Nom", value: (n) => asText(n.name), code: true }],
    fields: [
      { name: "application_id", label: "Application", type: "reference", resource: "applications", required: true },
      {
        name: "environment_id",
        label: "Environnement",
        type: "reference",
        resource: "environments",
        required: true,
      },
      {
        name: "cluster_id",
        label: "Cluster",
        type: "reference",
        resource: "clusters",
        required: true,
        filter: clusterOfRightType,
        help: "Seuls les clusters du même type (prod / hors prod) que l'environnement sont proposés.",
      },
      { name: "suffix", label: "Suffixe", type: "text", required: true, help: "Ex. : app, batch" },
      { name: "network_zone_id", label: "Zone réseau", type: "reference", resource: "network-zones", required: true },
    ],
    // À la création : plusieurs clusters d'un coup, et les emplacements des modules (POST /api/namespaces/batch).
    batchCreationFields: [
      { name: "application_id", label: "Application", type: "reference", resource: "applications", required: true },
      {
        name: "environment_id",
        label: "Environnement",
        type: "reference",
        resource: "environments",
        required: true,
      },
      {
        name: "cluster_ids",
        label: "Clusters",
        type: "references",
        resource: "clusters",
        required: true,
        fallback: [],
        filter: clusterOfRightType,
        help: "Un namespace est créé sur chaque cluster coché. Seuls les clusters du même type (prod / hors prod) que l'environnement sont proposés.",
      },
      { name: "suffix", label: "Suffixe", type: "text", required: true, help: "Ex. : app, batch" },
      { name: "network_zone_id", label: "Zone réseau", type: "reference", resource: "network-zones", required: true },
      {
        name: "with_slots",
        label: "Créer les emplacements des modules",
        type: "boolean",
        fallback: true,
        help: "Un emplacement par module de l'application dans chaque namespace (nom de release = code du module). Tout ou rien : au moindre refus, rien n'est créé.",
      },
    ],
  },
  {
    key: "modules",
    title: "Modules",
    group: "Socle",
    newLabel: "Nouveau module",
    help: "Les programmes d'une application : capacité (socle) ou projet métier.",
    fields: [
      { name: "application_id", label: "Application", type: "reference", resource: "applications", required: true },
      { name: "code", label: "Code", type: "text", required: true, help: "Unique dans l'application." },
      { name: "name", label: "Nom", type: "text", required: true },
      { name: "type", label: "Type", type: "list", enumeration: "ModuleType", required: true },
    ],
    extraCreationFields: [
      {
        name: "with_slots",
        label: "Lui créer un emplacement dans chaque namespace de l'application",
        type: "boolean",
        fallback: true,
        help: "Nom de release = code du module. Tout ou rien : si ce nom est déjà pris dans un namespace, rien n'est créé.",
      },
    ],
  },
  {
    key: "dependencies",
    title: "Dépendances",
    group: "Socle",
    newLabel: "Nouvelle dépendance",
    help: "« Le module A a besoin du module B », toutes applications confondues. Ne se modifie pas.",
    editable: false,
    fields: [
      { name: "module_id", label: "Le module…", type: "reference", resource: "modules", required: true },
      {
        name: "depends_on_id",
        label: "…a besoin de",
        type: "reference",
        resource: "modules",
        required: true,
        filter: (m, values) => m.id !== Number(values.module_id),
      },
    ],
  },

  // ----- Déploiement -----
  {
    key: "module-versions",
    title: "Versions de module",
    group: "Déploiement",
    newLabel: "Nouvelle version",
    help: "Snapshot par défaut. Numéro : 2.3.0, 3.0.0-SNAPSHOT…",
    fields: [
      { name: "module_id", label: "Module", type: "reference", resource: "modules", required: true },
      { name: "number", label: "Numéro", type: "text", required: true, help: "Ex. : 2.3.0" },
      { name: "type", label: "Type", type: "list", enumeration: "VersionType", fallback: "SNAPSHOT" },
    ],
  },
  {
    key: "compatibilities",
    title: "Compatibilités",
    group: "Déploiement",
    newLabel: "Nouvelle compatibilité",
    help: "Ce dont une version a besoin. Le module requis doit être déclaré en dépendance.",
    fields: [
      {
        name: "module_version_id",
        label: "La version…",
        type: "reference",
        resource: "module-versions",
        required: true,
      },
      {
        name: "required_module_id",
        label: "…a besoin du module",
        type: "reference",
        resource: "modules",
        required: true,
        // Seuls les modules déclarés en dépendance du module de la version.
        filter: (m, values, ctx) => {
          const version = ctx.byId("module-versions", values.module_version_id);
          return (
            !version || ctx.d.dependencies.some((dep) => dep.module_id === version.module_id && dep.depends_on_id === m.id)
          );
        },
        help: "Seuls les modules dont le module de la version dépend sont proposés.",
      },
      { name: "condition", label: "Condition", type: "list", enumeration: "ConditionType", required: true },
      { name: "version", label: "Version", type: "text", required: true, help: "Version exacte, ou borne basse." },
      {
        name: "version_max",
        label: "Version max",
        type: "text",
        required: true,
        visible: (values) => values.condition === "BETWEEN",
        help: "Borne haute (comprise).",
      },
    ],
  },
  {
    key: "parameters",
    title: "Paramètres",
    group: "Déploiement",
    newLabel: "Nouveau paramètre",
    help: "Technique ou applicatif, propre à un module ; son nom est libre (souvent une version), unique par module et par type.",
    fields: [
      { name: "module_id", label: "Module", type: "reference", resource: "modules", required: true },
      {
        name: "name",
        label: "Nom",
        type: "text",
        required: true,
        help: "Libre, par exemple une version : 2.3. Unique pour le module et le type.",
      },
      { name: "type", label: "Type", type: "list", enumeration: "ParameterType", required: true },
      {
        name: "namespace_ids",
        label: "Namespaces affectés",
        type: "references",
        resource: "namespaces",
        fallback: [],
        filter: moduleApplication,
        help: "Seuls les namespaces de l'application du module sont proposés.",
      },
    ],
  },
  {
    key: "slots",
    title: "Emplacements",
    group: "Déploiement",
    newLabel: "Nouvel emplacement",
    help: "Un namespace + un nom de release, réservé à un module.",
    fields: [
      { name: "namespace_id", label: "Namespace", type: "reference", resource: "namespaces", required: true },
      {
        name: "module_id",
        label: "Module réservé",
        type: "reference",
        resource: "modules",
        required: true,
        filter: (m, values, ctx) => {
          const namespace = ctx.byId("namespaces", values.namespace_id);
          return !namespace || m.application_id === namespace.application_id;
        },
        help: "Seuls les modules de l'application du namespace sont proposés.",
      },
      { name: "release_name", label: "Nom de release", type: "text", required: true, help: "Ex. : batch-paie" },
    ],
  },
  {
    key: "installations",
    title: "Installations",
    group: "Déploiement",
    newLabel: "Enregistrer une installation",
    help: "Une version posée sur un emplacement. Ne se modifie pas.",
    editable: false,
    guidedForm: true,
    fields: [
      { name: "slot_id", label: "Emplacement", type: "reference", resource: "slots" },
      { name: "module_version_id", label: "Version", type: "reference", resource: "module-versions" },
      {
        name: "technical_parameter_id",
        label: "Paramètre technique",
        type: "reference",
        resource: "parameters",
      },
      {
        name: "application_parameter_id",
        label: "Paramètre applicatif",
        type: "reference",
        resource: "parameters",
      },
    ],
    extraColumns: [
      {
        title: "Date",
        value: (i) => formatDate(asText(i.date)),
      },
    ],
  },
];
