// Connexion par Keycloak (OAuth 2.1 : authorization code + PKCE), côté serveur Next.js.
//
// L'interface est un client de Keycloak, « suivi-delivery-frontend » (public, protégé par PKCE) :
//   1. /login/start prépare un secret PKCE et un « state », et envoie la personne sur la
//      page de connexion de Keycloak ;
//   2. Keycloak la renvoie sur /login/callback avec un code, échangé ici contre les jetons.
//
// La personne ne voit jamais Keycloak : ses pages ont l'allure de l'outil (thème keycloak/themes)
// et sont servies sous l'adresse de l'interface (<APP_FRONTEND_URL>/auth/…), relayées par proxy.ts
// vers l'adresse interne de Keycloak (KEYCLOAK_URL). Les échanges de jetons, eux, vont directement
// à l'adresse interne, de serveur à serveur.
//
// Ce fichier n'est utilisé que par le serveur : le navigateur ne voit ni l'adresse interne, ni les secrets.
import { createHash, randomBytes } from "node:crypto";

import { ApiError } from "./api";
import { frontendUrl, keycloakUrl, keycloakRealm } from "./settings";
import type { Tokens } from "./session";

export const FRONTEND_CLIENT = "suivi-delivery-frontend";

/** Adresses OpenID Connect du domaine : vue du navigateur (publique) ou du serveur (interne). */
const oidcPublic = (): string => `${frontendUrl()}/auth/realms/${keycloakRealm()}/protocol/openid-connect`;
const internalOidc = (): string => `${keycloakUrl()}/realms/${keycloakRealm()}/protocol/openid-connect`;

/** Adresse de retour de l'interface, après la page de connexion. */
export const callbackUrl = (): string => `${frontendUrl()}/login/callback`;

/** Un secret PKCE (gardé par l'interface) et son empreinte (envoyée avec la demande). */
export function secretPkce(): { check: string; challenge: string } {
  const check = randomBytes(48).toString("base64url"); // 64 caractères
  const challenge = createHash("sha256").update(check).digest("base64url");
  return { check, challenge };
}

/** Un « state » imprévisible : relie le retour à la demande (protection contre les retours forgés). */
export const newState = (): string => randomBytes(24).toString("base64url");

/**
 * L'adresse de la page de connexion (publique). action « mot-de-passe » : Keycloak demande
 * d'abord le mot de passe actuel (si la connexion date un peu), puis le nouveau.
 */
export function loginUrl(challenge: string, state: string, action?: "password"): URL {
  const page = new URL(`${oidcPublic()}/auth`);
  page.search = new URLSearchParams({
    client_id: FRONTEND_CLIENT,
    redirect_uri: callbackUrl(),
    response_type: "code",
    scope: "openid",
    code_challenge: challenge,
    code_challenge_method: "S256",
    state: state,
    ui_locales: "fr",
    ...(action === "password" ? { kc_action: "UPDATE_PASSWORD" } : {}),
  }).toString();
  return page;
}

/** Envoie un formulaire à Keycloak (adresse interne) ; renvoie le code et le contenu JSON. */
async function send(path: string, fields: Record<string, string>): Promise<{ status: number; content: unknown }> {
  const url = `${internalOidc()}/${path}`;
  try {
    const response = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: new URLSearchParams(fields).toString(),
      cache: "no-store",
    });
    return { status: response.status, content: await response.json().catch(() => null) };
  } catch (cause) {
    // L'adresse interne ne va que dans les journaux du serveur, jamais dans la page.
    console.error(`Keycloak injoignable (${url}) :`, cause);
    throw new ApiError("Keycloak injoignable");
  }
}

async function askTokens(fields: Record<string, string>): Promise<Tokens> {
  const { status, content } = await send("token", { ...fields, client_id: FRONTEND_CLIENT });
  if (status !== 200) {
    const error = (content as { error_description?: string; error?: string } | null) ?? {};
    throw new ApiError(`jetons refusés par Keycloak : ${error.error_description ?? error.error ?? status}`, status);
  }
  return content as Tokens;
}

/** Échange le code reçu au retour contre les jetons de l'interface. */
export function exchangeCode(code: string, check: string): Promise<Tokens> {
  return askTokens({
    grant_type: "authorization_code",
    code,
    redirect_uri: callbackUrl(),
    code_verifier: check,
  });
}

/** Nouveaux jetons à partir du jeton de renouvellement ; null si Keycloak refuse ou ne répond pas. */
export async function refreshTokens(refreshToken: string): Promise<Tokens | null> {
  try {
    return await askTokens({ grant_type: "refresh_token", refresh_token: refreshToken });
  } catch {
    return null; // session finie (ou Keycloak injoignable) : il faudra se reconnecter
  }
}

/** Ferme la session chez Keycloak (erreurs ignorées) : la page de connexion redemandera le mot de passe. */
export async function closeSessionKeycloak(refreshToken: string): Promise<void> {
  await send("logout", { client_id: FRONTEND_CLIENT, refresh_token: refreshToken }).catch(() => undefined);
}
