// GET /login/start : la connexion de l'interface (OAuth 2.1, authorization code + PKCE, par Keycloak).
// On y arrive toujours par une navigation complète, depuis la page /login (voir app/login/page.tsx).
//
//   1. un secret PKCE et un « state » sont préparés, et gardés dans un cookie protégé (10 minutes,
//      seulement pour /login) ;
//   2. la personne part sur la page de connexion de Keycloak (à l'allure de l'outil, sous l'adresse
//      de l'interface : voir lib/oauth.ts et proxy.ts) ;
//   3. Keycloak la renvoie sur /login/callback avec un code, échangé contre les jetons (retour/route.ts).
//
// ?action=mot-de-passe : changer son mot de passe (depuis « Mon compte ») ; Keycloak demande le
// nouveau, puis renvoie à la page d'où l'on vient. Sinon, déjà connecté : on va directement à la page demandée.
import { type NextRequest, NextResponse } from "next/server";

import { loginUrl, newState, secretPkce } from "@/lib/oauth";
import { sitePage } from "@/lib/settings";
import { COOKIE_OAUTH, destination, isHttps, readSession } from "@/lib/session";

export const dynamic = "force-dynamic";

export async function GET(request: NextRequest) {
  const parameters = request.nextUrl.searchParams;
  const next = destination(parameters.get("next"));
  const action = parameters.get("action") === "password" ? "password" : undefined;
  if (!action && (await readSession())) return NextResponse.redirect(sitePage(next));

  const { check, challenge } = secretPkce();
  const state = newState();
  const response = NextResponse.redirect(loginUrl(challenge, state, action));
  response.cookies.set(COOKIE_OAUTH, JSON.stringify({ check, state, next, action }), {
    httpOnly: true,
    sameSite: "lax",
    secure: isHttps(request),
    path: "/login",
    maxAge: 600,
  });
  return response;
}
