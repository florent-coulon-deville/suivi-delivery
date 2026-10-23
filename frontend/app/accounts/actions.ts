"use server";
// Gestion des comptes, exécutée sur le serveur Next.js ; réservée à l'ADMIN
// (vérifié ici, puis par l'API).
import { ApiError, write } from "@/lib/api";
import { isAdmin, readSession } from "@/lib/session";

export type Result = { ok: true; key?: string } | { ok: false; message: string };

const ROLES = new Set(["VIEWER", "EDITOR", "ADMIN"]);
const KINDS = new Set(["PERSON", "PROGRAM"]);

async function execute(action: () => Promise<unknown>): Promise<Result> {
  if (!isAdmin((await readSession())?.role)) {
    return { ok: false, message: "Droits insuffisants : rôle ADMIN requis" };
  }
  try {
    const content = (await action()) as { key?: string | null } | null;
    return { ok: true, key: content?.key ?? undefined };
  } catch (_error) {
    if (_error instanceof ApiError) return { ok: false, message: _error.message };
    throw _error;
  }
}

/** Un identifiant de compte Keycloak (UUID) : rien d'autre n'entre dans l'adresse de l'API. */
function checkId(id: string) {
  if (!/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(id)) {
    throw new Error(`Identifiant invalide : ${id}`);
  }
}

export type NewAccount = { identifier: string; name: string; kind: string; role: string; password?: string };

/** Crée un compte (personne : mot de passe provisoire). Pour un programme, le résultat contient sa clé
(à afficher une seule fois). */
export async function createAccount(account: NewAccount) {
  if (!KINDS.has(account.kind) || !ROLES.has(account.role)) throw new Error("Sorte ou rôle inconnu");
  const body = {
    identifier: account.identifier,
    name: account.name,
    kind: account.kind,
    role: account.role,
    ...(account.kind === "PERSON" ? { password: account.password ?? "" } : {}),
  };
  return execute(() => write("POST", "accounts", body));
}

export type Changes = { name?: string; role?: string; active?: boolean; password?: string };

/** Modifie un compte (seuls les champs donnés). */
export async function updateAccount(id: string, changes: Changes) {
  checkId(id);
  if (changes.role !== undefined && !ROLES.has(changes.role)) throw new Error("Rôle inconnu");
  // Seuls les champs connus sont transmis.
  const body = Object.fromEntries(
    (["name", "role", "active", "password"] as const)
      .filter((field) => changes[field] !== undefined)
      .map((field) => [field, changes[field]]),
  );
  return execute(() => write("PATCH", `accounts/${id}`, body));
}

export async function deleteAccount(id: string) {
  checkId(id);
  return execute(() => write("DELETE", `accounts/${id}`));
}

/** Nouvelle clé d'un programme (l'ancienne ne marche plus) ; à afficher une seule fois. */
export async function newKey(id: string) {
  checkId(id);
  return execute(() => write("POST", `accounts/${id}/key`));
}
