// Rapprochement des données, fait SUR LE SERVEUR : on part des listes brutes de l'API
// (reliées par identifiants) et on construit ce que l'écran « Ce qui tourne » affiche.
//
// Le résultat (Etat) ne contient que des données simples : il est envoyé tel quel aux
// parties interactives de l'écran (filtres, panneau de détail), dans le navigateur.
//
// « Ce qui tourne » sur un emplacement = sa dernière installation (date la plus récente),
// exactement comme côté API (backend/app/consistency.py).
import type {
  Application,
  Cluster,
  Compatibility,
  Data,
  Slot,
  Environment,
  Installation,
  Module,
  Namespace,
  Parameter,
  ModuleVersion,
  NetworkZone,
} from "./types";
import { compareVersions } from "./versions";

export type DetailedInstallation = Installation & {
  version: ModuleVersion;
  technical: Parameter; // un paramètre a un nom libre (souvent une version)
  application: Parameter;
};
/** Un emplacement, son contexte et ce qui y tourne (actuelle null : emplacement vide). */
export type Occupation = {
  slot: Slot;
  namespace: Namespace;
  cluster: Cluster;
  zone: NetworkZone;
  current: DetailedInstallation | null;
  previous: DetailedInstallation[];
};
export type Card = {
  needs: Module[];
  users: Module[];
  versions: {
    version: ModuleVersion;
    compatibilities: (Compatibility & { required: Module })[];
    inService: Environment[];
  }[];
};
export type ActivityRow = Installation & {
  version: ModuleVersion;
  module: Module;
  slot: Slot;
  environment: Environment;
};
export type Summary = {
  applications: number;
  modules: number;
  installations: number;
  inService: number;
  snapshots: number;
  lastProd: ActivityRow | null;
};
export type State = {
  environments: Environment[]; // triés par ordre de promotion, puis par code
  groups: { application: Application; modules: Module[] }[]; // triés par identifiant, puis par code
  occupations: Record<string, Occupation[]>; // clé « moduleId:environmentId » (voir checkboxKey)
  cards: Record<number, Card>; // par identifiant de module
  summary: Summary;
  activity: ActivityRow[]; // les dernières installations, la plus récente en premier
};

/** Nombre d'installations montrées dans « Activité récente ». */
const SHOWN_ACTIVITY = 10;

export const checkboxKey = (moduleId: number, environmentId: number): string => `${moduleId}:${environmentId}`;

/** Accès par identifiant ; une référence absente veut dire des données incohérentes : erreur nette. */
function index<T extends { id: number }>(list: T[], name: string): (id: number) => T {
  const byId = new Map(list.map((element) => [element.id, element]));
  return (id) => {
    const element = byId.get(id);
    if (!element) throw new Error(`${name} ${id} introuvable`);
    return element;
  };
}

/** Plus récente en premier ; à date égale, la dernière saisie en premier. */
function mostRecentFirst(a: Installation, b: Installation): number {
  if (a.date === b.date) return b.id - a.id;
  return a.date < b.date ? 1 : -1;
}

export function buildState(d: Data): State {
  const application = index(d.applications, "Application");
  const environment = index(d.environments, "Environnement");
  const cluster = index(d.clusters, "Cluster");
  const zone = index(d["network-zones"], "Zone réseau");
  const namespace = index(d.namespaces, "Namespace");
  const module = index(d.modules, "Module");
  const version = index(d["module-versions"], "Version de module");
  const parameter = index(d.parameters, "Paramètre");
  const slot = index(d.slots, "Emplacement");

  // Installations détaillées, regroupées par emplacement, la plus récente en premier.
  const histories = new Map<number, DetailedInstallation[]>();
  for (const installation of [...d.installations].sort(mostRecentFirst)) {
    const detailed: DetailedInstallation = {
      ...installation,
      version: version(installation.module_version_id),
      technical: parameter(installation.technical_parameter_id),
      application: parameter(installation.application_parameter_id),
    };
    const list = histories.get(installation.slot_id) ?? [];
    list.push(detailed);
    histories.set(installation.slot_id, list);
  }

  // Chaque emplacement, avec son contexte et ce qui y tourne.
  const occupations: Record<string, Occupation[]> = {};
  for (const e of d.slots) {
    const ns = namespace(e.namespace_id);
    const [current = null, ...previous] = histories.get(e.id) ?? [];
    const key = checkboxKey(e.module_id, ns.environment_id);
    const list = occupations[key] ?? [];
    list.push({
      slot: e,
      namespace: ns,
      cluster: cluster(ns.cluster_id),
      zone: zone(ns.network_zone_id),
      current,
      previous,
    });
    occupations[key] = list;
  }
  const occupationsOf = (moduleId: number, environmentId: number) => occupations[checkboxKey(moduleId, environmentId)] ?? [];

  const environments = [...d.environments].sort(
    (a, b) => (a.promotion_order ?? Infinity) - (b.promotion_order ?? Infinity) || a.code.localeCompare(b.code),
  );

  const groups = [...d.applications]
    .sort((a, b) => a.identifier.localeCompare(b.identifier))
    .map((app) => ({
      application: app,
      modules: d.modules.filter((m) => m.application_id === app.id).sort((a, b) => a.code.localeCompare(b.code)),
    }));

  const cards: Record<number, Card> = {};
  for (const m of d.modules) {
    cards[m.id] = {
      needs: d.dependencies.filter((x) => x.module_id === m.id).map((x) => module(x.depends_on_id)),
      users: d.dependencies.filter((x) => x.depends_on_id === m.id).map((x) => module(x.module_id)),
      versions: d["module-versions"]
        .filter((v) => v.module_id === m.id)
        .sort((a, b) => compareVersions(b.number, a.number))
        .map((v) => ({
          version: v,
          compatibilities: d.compatibilities
            .filter((c) => c.module_version_id === v.id)
            .map((c) => ({ ...c, required: module(c.required_module_id) })),
          inService: environments.filter((env) =>
            occupationsOf(m.id, env.id).some((o) => o.current?.version.id === v.id),
          ),
        })),
    };
  }

  // Activité : chaque installation avec son module, son environnement et son emplacement.
  const activity: ActivityRow[] = [...d.installations].sort(mostRecentFirst).map((installation) => {
    const e = slot(installation.slot_id);
    const v = version(installation.module_version_id);
    return {
      ...installation,
      version: v,
      module: module(v.module_id),
      slot: e,
      environment: environment(namespace(e.namespace_id).environment_id),
    };
  });

  const inService = Object.values(occupations)
    .flat()
    .filter((o) => o.current);
  const summary: Summary = {
    applications: d.applications.length,
    modules: d.modules.length,
    installations: d.installations.length,
    inService: inService.length,
    snapshots: inService.filter((o) => o.current?.version.type === "SNAPSHOT").length,
    lastProd: activity.find((i) => i.environment.is_prod) ?? null,
  };

  // Vérifie au passage que chaque module a bien son application.
  for (const m of d.modules) application(m.application_id);

  return { environments, groups, occupations, cards, summary, activity: activity.slice(0, SHOWN_ACTIVITY) };
}
