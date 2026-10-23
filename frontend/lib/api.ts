// Appels à l'API, faits PAR LE SERVEUR Next.js (jamais par le navigateur).
//
//   navigateur ──► serveur Next.js ──► API (API_URL)
//
// Le navigateur ne connaît ni l'adresse de l'API, ni ses routes.
import { apiUrl } from "./settings";

/** L'API n'a pas répondu, ou a répondu par une erreur. */
export class ApiError extends Error {
  constructor(
    message: string,
    readonly status?: number,
  ) {
    super(message);
  }
}

/** Envoie la requête ; si l'API est injoignable, lève ApiError sans révéler son adresse. */
async function send(path: string, options: RequestInit = {}): Promise<Response> {
  const url = `${apiUrl()}/api/${path}`;
  try {
    // no-store : toujours les données du moment, jamais une copie gardée en cache.
    return await fetch(url, { ...options, cache: "no-store" });
  } catch (cause) {
    // L'adresse de l'API ne va que dans les journaux du serveur, jamais dans la page.
    console.error(`API injoignable (${url}) :`, cause);
    throw new ApiError("connexion impossible");
  }
}

/** GET /api/<chemin> : renvoie le contenu JSON, ou lève ApiError. */
export async function read<T>(path: string): Promise<T> {
  const response = await send(path);
  if (!response.ok) {
    throw new ApiError(`GET /api/${path} : ${response.status}`, response.status);
  }
  return (await response.json()) as T;
}

/** GET /api/<chemin> d'un fichier (export) : renvoie la réponse de l'API telle quelle, ou lève ApiError. */
export async function download(path: string): Promise<Response> {
  const response = await send(path);
  if (!response.ok) {
    throw new ApiError(`GET /api/${path} : ${response.status}`, response.status);
  }
  return response;
}

/**
 * Envoie un fichier à l'API (import de la configuration). Renvoie le statut et le contenu JSON de la
 * réponse, sans lever d'erreur pour un refus (4xx) : l'appelant lit le message et le rapport joint.
 */
export async function sendFile(
  method: Method,
  path: string,
  file: Blob,
  type: string,
): Promise<{ status: number; content: unknown; message: string }> {
  const response = await send(path, { method: method, headers: { "Content-Type": type }, body: file });
  const content: unknown = await response.json().catch(() => null);
  return { status: response.status, content, message: errorMessage(response.status, content) };
}

type ValidationError = { loc: (string | number)[]; msg: string };

/** Transforme la réponse d'erreur de l'API en message lisible. */
function errorMessage(status: number, body: unknown): string {
  const detail = (body as { detail?: unknown } | null)?.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    // Erreurs de validation : [{ loc: ["body", "code"], msg: "…" }, …] → « code : … »
    return (detail as ValidationError[])
      .map((e) => `${e.loc.filter((l) => l !== "body").join(".") || "requête"} : ${e.msg}`)
      .join(" ; ");
  }
  return `Erreur ${status}`;
}

export type Method = "POST" | "PUT" | "PATCH" | "DELETE";

/**
 * Envoie une écriture à l'API. Renvoie le contenu (ou null pour un 204).
 * En cas de refus (4xx), lève ApiError avec le message de l'API, tel quel.
 */
export async function write(method: Method, path: string, body?: unknown): Promise<unknown> {
  const response = await send(path, {
    method: method,
    headers: body === undefined ? {} : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (response.status === 204) return null;
  const content: unknown = await response.json().catch(() => null);
  if (!response.ok) throw new ApiError(errorMessage(response.status, content), response.status);
  return content;
}
