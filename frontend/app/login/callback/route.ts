// GET /login/callback : Keycloak y renvoie la personne, avec un code (OAuth 2.1).
//
// On vérifie que le retour correspond bien à la demande lancée par /login (même « state »,
// gardé dans le cookie sd_oauth), puis on échange le code contre les jetons, avec le secret PKCE.
// Les jetons sont rangés dans les cookies de session, avec le thème de la personne (cookie
// sd_theme) ; elle arrive sur la page demandée.
//
// Retour d'un changement de mot de passe (action demandée depuis « Mon compte ») : Keycloak dit
// s'il a été fait (kc_action_status : success, cancelled) ; la page demandée affiche le résultat.
// Tout autre échec mène à /login/unavailable (avec « Réessayer ») : relancer la connexion
// tout seul pourrait tourner en rond, la session Keycloak étant encore ouverte.
import { type NextRequest, NextResponse } from "next/server";

import { readWithToken } from "@/lib/api";
import { exchangeCode } from "@/lib/oauth";
import { sitePage } from "@/lib/settings";
import { ACCESS_COOKIE, COOKIE_OAUTH, REFRESH_COOKIE, destination, isHttps, optionsCookie } from "@/lib/session";
import { COOKIE_THEME, isTheme, optionsCookieTheme } from "@/lib/theme";
import type { Me } from "@/lib/types";

export const dynamic = "force-dynamic";

type InProgress = { check: string; state: string; next: string; action?: string };

function readInProgress(text: string | undefined): InProgress | null {
  try {
    const { check, state, next, action } = JSON.parse(text ?? "") as Partial<InProgress>;
    if (typeof check !== "string" || typeof state !== "string") return null;
    return { check, state, next: destination(next), action: typeof action === "string" ? action : undefined };
  } catch {
    return null;
  }
}

export async function GET(request: NextRequest) {
  const parameters = request.nextUrl.searchParams;
  const inProgress = readInProgress(request.cookies.get(COOKIE_OAUTH)?.value);
  const code = parameters.get("code");
  const failure = () => {
    const response = NextResponse.redirect(sitePage("/login/unavailable"));
    response.cookies.delete({ name: COOKIE_OAUTH, path: "/login" });
    return response;
  };
  // Retour sans demande en cours, ou qui ne correspond pas à notre demande (state) : refusé.
  if (!inProgress || parameters.get("state") !== inProgress.state) return failure();
  // Changement de mot de passe annulé : la session en cours continue, rien à échanger.
  if (inProgress.action === "password" && !code) {
    const page = sitePage(inProgress.next);
    page.searchParams.set("password", parameters.get("kc_action_status") === "cancelled" ? "cancelled" : "error");
    const response = NextResponse.redirect(page);
    response.cookies.delete({ name: COOKIE_OAUTH, path: "/login" });
    return response;
  }
  if (!code) return failure();

  let tokens;
  try {
    tokens = await exchangeCode(code, inProgress.check);
  } catch (_error) {
    console.error("Connexion : échange du code refusé :", _error);
    return failure();
  }
  const https = isHttps(request);
  const page = sitePage(inProgress.next);
  if (inProgress.action === "password") {
    const status = parameters.get("kc_action_status");
    const results: Record<string, string> = { success: "change", cancelled: "cancelled" };
    page.searchParams.set("password", results[status ?? ""] ?? "error");
  }
  const response = NextResponse.redirect(page);
  response.cookies.set(ACCESS_COOKIE, tokens.access_token, optionsCookie(tokens.expires_in, https));
  response.cookies.set(REFRESH_COOKIE, tokens.refresh_token, optionsCookie(tokens.refresh_expires_in, https));
  response.cookies.delete({ name: COOKIE_OAUTH, path: "/login" });
  // Le thème choisi par la personne (« Mon compte » → Apparence), pour afficher les pages dans ce thème.
  try {
    const { theme } = await readWithToken<Me>("me", tokens.access_token);
    if (isTheme(theme)) response.cookies.set(COOKIE_THEME, theme, optionsCookieTheme(https));
  } catch (_error) {
    console.error("Connexion : thème illisible (le thème actuel est gardé) :", _error);
  }
  return response;
}
