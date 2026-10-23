"use server";
// Écritures de l'espace « Saisie », exécutées SUR LE SERVEUR Next.js (« Server Actions »).
//
// Le formulaire, dans le navigateur, appelle ces fonctions comme des fonctions ordinaires ;
// Next.js transmet l'appel au serveur, qui écrit dans l'API. Le navigateur ne parle donc
// jamais à l'API directement.
//
// Attention : une Server Action est joignable par quiconque atteint le site. On vérifie donc
// tout ce qui arrive (rôle de l'utilisateur, ressource connue, identifiant entier) ; l'API,
// elle, revérifie le jeton et le rôle, puis le contenu.
import { ApiError, write } from "@/lib/api";
import { readSession, canUpdate } from "@/lib/session";
import { RESOURCES, RESOURCES_STRUCTURE, type Resource } from "@/lib/types";

export type Result = { ok: true } | { ok: false; message: string };

function check(resource: string, id: number | null): asserts resource is Resource {
  if (!RESOURCES.includes(resource as Resource)) throw new Error(`Ressource inconnue : ${resource}`);
  if (id !== null && !(Number.isInteger(id) && id > 0)) throw new Error(`Identifiant invalide : ${id}`);
}

async function execute(resource: Resource, action: () => Promise<unknown>): Promise<Result> {
  if (!canUpdate((await readSession())?.role, resource)) {
    const role = RESOURCES_STRUCTURE.has(resource) ? "ADMIN" : "EDITOR";
    return { ok: false, message: `Droits insuffisants : rôle ${role} requis` };
  }
  try {
    await action();
    return { ok: true };
  } catch (_error) {
    // Refus de l'API (409, 422…) : son message est affiché tel quel dans le formulaire.
    if (_error instanceof ApiError) return { ok: false, message: _error.message };
    throw _error;
  }
}

/** Crée (id null → POST) ou remplace (id → PUT) un élément. */
export async function save(resource: string, id: number | null, body: Record<string, unknown>) {
  check(resource, id);
  return execute(resource, () =>
    id === null ? write("POST", resource, body) : write("PUT", `${resource}/${id}`, body),
  );
}

// Objets qui ont une création groupée (POST /api/<objet>/lot ; batchCreationFields de ressources.ts).
const BATCH_CREATIONS: ReadonlySet<string> = new Set(["namespaces"]);

/** Crée plusieurs éléments d'un coup (POST /api/<objet>/lot), tout ou rien. Ex. : un namespace sur plusieurs clusters. */
export async function createBatch(resource: string, body: Record<string, unknown>) {
  check(resource, null);
  if (!BATCH_CREATIONS.has(resource)) throw new Error(`Pas de création groupée pour : ${resource}`);
  return execute(resource, () => write("POST", `${resource}/batch`, body));
}

/** Supprime un élément (DELETE). */
export async function remove(resource: string, id: number) {
  check(resource, id);
  return execute(resource, () => write("DELETE", `${resource}/${id}`));
}
