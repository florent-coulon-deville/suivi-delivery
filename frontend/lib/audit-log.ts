// Mise en forme du journal des actions (page /audit-log) : noms lisibles des objets et des actions,
// résumé de ce qui a changé. Sans affichage : utilisable par le serveur comme par le navigateur.
import type { AuditEntry } from "./types";

/** Les objets suivis par le journal, dans l'ordre des écrans. */
export const OBJECTS: { table: string; label: string }[] = [
  { table: "environments", label: "Environnement" },
  { table: "clusters", label: "Cluster" },
  { table: "network_zones", label: "Zone réseau" },
  { table: "applications", label: "Application" },
  { table: "namespaces", label: "Namespace" },
  { table: "modules", label: "Module" },
  { table: "dependencies", label: "Dépendance" },
  { table: "module_versions", label: "Version de module" },
  { table: "compatibilities", label: "Compatibilité" },
  { table: "parameters", label: "Paramètre" },
  { table: "slots", label: "Emplacement" },
  { table: "installations", label: "Installation" },
  { table: "accounts", label: "Compte" },
];

export const ACTIONS: Record<AuditEntry["action"], string> = {
  CREATE: "Création",
  UPDATE: "Modification",
  DELETE: "Suppression",
};

export const objectLabel = (table: string): string => OBJECTS.find((o) => o.table === table)?.label ?? table;

/** Une valeur du journal, en texte court. */
export function readableValue(value: unknown): string {
  if (value === null || value === undefined || value === "") return "—";
  if (typeof value === "boolean") return value ? "oui" : "non";
  if (Array.isArray(value)) return value.length ? value.map(readableValue).join(", ") : "—";
  if (typeof value === "string") return value;
  if (typeof value === "number" || typeof value === "bigint") return value.toString();
  return JSON.stringify(value) ?? "—"; // objet : son contenu, pas « [object Object] »
}

// Champs qui nomment un objet, du plus parlant au moins parlant.
const NAME_FIELDS = ["code", "identifier", "name", "release_name", "number", "suffix"];

/** Le nom de l'objet (son code, son identifiant…), pris avant ou après la saisie ; "" si aucun. */
export function objectName(row: AuditEntry): string {
  const content = row.after ?? row.before ?? {};
  const field = NAME_FIELDS.find((c) => typeof content[c] === "string" && content[c] !== "");
  return field ? String(content[field]) : "";
}

export type Change = { field: string; before: string; after: string };

/** Les champs modifiés par une UPDATE (rien pour une création ou une suppression). */
export function changes(row: AuditEntry): Change[] {
  if (row.action !== "UPDATE" || !row.before || !row.after) return [];
  const before = row.before;
  const after = row.after;
  return Object.keys(after)
    .filter((field) => JSON.stringify(before[field]) !== JSON.stringify(after[field]))
    .map((field) => ({ field, before: readableValue(before[field]), after: readableValue(after[field]) }));
}

/**
 * L'instant ISO qui correspond à ce jour (AAAA-MM-JJ) à cette heure, à Paris (heure d'été comprise) :
 * les dates de l'écran sont celles de Paris, celles de l'API sont en UTC.
 */
export function instantParis(day: string, time: string): string | null {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(day)) return null;
  const asUtc = new Date(`${day}T${time}Z`);
  if (Number.isNaN(asUtc.getTime())) return null;
  const view = (timezone: string) => new Date(asUtc.toLocaleString("en-US", { timeZone: timezone })).getTime();
  return new Date(asUtc.getTime() - (view("Europe/Paris") - view("UTC"))).toISOString();
}
