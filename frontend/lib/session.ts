// La session de l'utilisateur, gardée dans deux cookies protégés (HttpOnly : le code de la
// page ne peut pas les lire, seul le serveur les voit) :
//   sd_access           le jeton d'accès de Keycloak (JWT, 5 min) : le serveur l'envoie à l'API à
//                      chaque appel ;
//   sd_refresh  le jeton de renouvellement de Keycloak (24 h sans servir) : proxy.ts s'en
//                      sert pour obtenir un nouveau jeton d'accès avant que l'ancien n'expire.
// Les jetons sont obtenus par la page de connexion (Keycloak, à l'allure de l'outil : voir
// lib/oauth.ts et app/login/).
//
// Le contenu du jeton d'accès (nom, rôle) est lu ici SANS vérifier sa signature : il sert
// seulement à adapter l'affichage (menus). C'est l'API qui vérifie tout, à chaque appel.

import { RESOURCES_STRUCTURE, type Resource } from "./types";

export const ACCESS_COOKIE = "sd_access";
export const REFRESH_COOKIE = "sd_refresh";
// Connexion en cours (10 min, seulement sous /login) : secret PKCE, « state » et page à rouvrir.
export const COOKIE_OAUTH = "sd_oauth";

export type Role = "VIEWER" | "EDITOR" | "ADMIN";
export type Session = { identifier: string; name: string; role: Role | null; expire: number };

const POSITION: Record<Role, number> = { VIEWER: 1, EDITOR: 2, ADMIN: 3 };

/** Le plus fort des rôles de l'outil dans la liste des rôles du jeton (les autres sont ignorés). */
export function strongestRole(roles: unknown): Role | null {
  if (!Array.isArray(roles)) return null;
  const known = roles.filter((r): r is Role => typeof r === "string" && r in POSITION);
  return known.reduce<Role | null>((strong, r) => (strong === null || POSITION[r] > POSITION[strong] ? r : strong), null);
}

/** Contenu du jeton d'accès de Keycloak, ou null s'il est illisible. expire : en secondes depuis 1970. */
export function readToken(token: string): Session | null {
  try {
    const part = token.split(".")[1] ?? "";
    const content = JSON.parse(Buffer.from(part, "base64url").toString("utf8")) as Record<string, unknown>;
    const identifier = content.preferred_username;
    if (typeof identifier !== "string" || typeof content.exp !== "number") return null;
    const access = content.realm_access as { roles?: unknown } | undefined;
    return {
      identifier,
      name: typeof content.name === "string" && content.name ? content.name : identifier,
      role: strongestRole(access?.roles),
      expire: content.exp,
    };
  } catch {
    return null;
  }
}

/** La session en cours (lue dans les cookies de la requête), ou null. */
export async function readSession(): Promise<Session | null> {
  const { cookies } = await import("next/headers");
  const token = (await cookies()).get(ACCESS_COOKIE)?.value;
  const session = token ? readToken(token) : null;
  return session && session.expire > Date.now() / 1000 ? session : null;
}

export const canEdit = (role: Role | null | undefined): boolean => role === "EDITOR" || role === "ADMIN";
export const isAdmin = (role: Role | null | undefined): boolean => role === "ADMIN";
/** Peut modifier cet objet : la structure demande ADMIN, les livraisons EDITOR. */
export const canUpdate = (role: Role | null | undefined, resource: Resource): boolean =>
  RESOURCES_STRUCTURE.has(resource) ? isAdmin(role) : canEdit(role);

/** Réglages des cookies : invisibles du code de la page, envoyés seulement à notre site. */
export function optionsCookie(durationSeconds: number, https: boolean) {
  return {
    httpOnly: true,
    sameSite: "lax" as const, // pas envoyés par les formulaires d'autres sites
    secure: https, // en HTTPS (OpenShift), seulement sur une connexion chiffrée
    path: "/",
    maxAge: durationSeconds,
  };
}

/** Réponse de l'adresse des jetons de Keycloak (norme OAuth2). */
export type Tokens = {
  access_token: string;
  expires_in: number;
  refresh_token: string;
  refresh_expires_in: number;
};

/** Adresse où revenir après la connexion : seulement une page de notre site. */
export function destination(next: unknown): string {
  const text = typeof next === "string" ? next : "";
  return text.startsWith("/") && !text.startsWith("//") && !text.startsWith("/\\") ? text : "/";
}

/** La requête est-elle arrivée en HTTPS (directement, ou derrière le relais d'OpenShift) ? */
export const isHttps = (request: { headers: Headers; nextUrl: URL }): boolean =>
  request.headers.get("x-forwarded-proto") === "https" || request.nextUrl.protocol === "https:";
