// Passage obligé de chaque requête, AVANT la page (Next.js « proxy », côté serveur) :
//
//   - /auth/… : les pages de connexion de Keycloak, relayées vers son adresse interne
//     (KEYCLOAK_URL).
//       · Le navigateur reste sur l'adresse de l'outil : on ne voit pas qu'on passe par Keycloak
//         (ses pages ont aussi l'allure de l'outil, thème keycloak/themes).
//       · Seul le domaine de l'outil est relayé (et les fichiers de ses pages), jamais la console
//         d'administration de Keycloak.
//       · Le thème choisi (« Mon compte » → Apparence) est recopié dans un cookie lisible par ces
//         pages (sd_theme_auth, sous /auth seulement) ;

//   - pages publiques (/login et ses pages, /health) : rien à vérifier ;
//   - jeton d'accès encore valable plus d'une minute : on laisse passer ;
//   - sinon, s'il y a un jeton de renouvellement : on demande une nouvelle paire de jetons à
//     Keycloak, on la range dans les cookies, et on laisse passer — l'utilisateur ne voit rien ;
//   - sinon : connexion (/login, avec l'adresse demandée, pour y revenir ensuite).
//
// Les droits (rôle) sont vérifiés ensuite, par chaque page et chaque action, puis par l'API.
import { type NextRequest, NextResponse } from "next/server";

import { refreshTokens } from "@/lib/oauth";
import { keycloakUrl, keycloakRealm } from "@/lib/settings";
import { ACCESS_COOKIE, REFRESH_COOKIE, isHttps, readToken, optionsCookie } from "@/lib/session";
import { COOKIE_THEME, COOKIE_THEME_AUTH } from "@/lib/theme";

const PUBLIC = ["/login", "/health"];
const MARGIN = 60; // secondes : on renouvelle un peu avant l'expiration

/** Relaie une page de Keycloak, ou 404 pour tout ce qui n'est pas le domaine de l'outil. */
function relayKeycloak(request: NextRequest): NextResponse {
  const path = request.nextUrl.pathname;
  const allowed = [`/auth/realms/${keycloakRealm()}/`, "/auth/resources/"];
  if (!allowed.some((start) => path.startsWith(start))) return new NextResponse(null, { status: 404 });
  // L'adresse interne finit par /auth, comme le chemin commence par /auth : on ne le répète pas.
  const target = new URL(`${keycloakUrl()}${path.slice("/auth".length)}${request.nextUrl.search}`);
  const response = NextResponse.rewrite(target);
  // Le thème, pour que la page de connexion ait les mêmes couleurs que l'outil (keycloak/themes,
  // template.ftl). Rien de secret : lisible par le code de la page, envoyé seulement sous /auth.
  const theme = request.cookies.get(COOKIE_THEME)?.value;
  if (theme === "LIGHT" || theme === "DARK") {
    response.cookies.set(COOKIE_THEME_AUTH, theme, {
      httpOnly: false,
      sameSite: "lax",
      secure: isHttps(request),
      path: "/auth",
      maxAge: 365 * 24 * 3600,
    });
  } else if (request.cookies.has(COOKIE_THEME_AUTH)) {
    response.cookies.delete({ name: COOKIE_THEME_AUTH, path: "/auth" });
  }
  return response;
}

export async function proxy(request: NextRequest) {
  const path = request.nextUrl.pathname;
  if (path === "/auth" || path.startsWith("/auth/")) return relayKeycloak(request);
  if (PUBLIC.some((p) => path === p || path.startsWith(`${p}/`))) return NextResponse.next();

  const now = Date.now() / 1000;
  const access = request.cookies.get(ACCESS_COOKIE)?.value;
  const session = access ? readToken(access) : null;
  if (session && session.expire - now > MARGIN) return NextResponse.next();

  const refreshToken = request.cookies.get(REFRESH_COOKIE)?.value;
  const tokens = refreshToken ? await refreshTokens(refreshToken) : null;
  if (tokens) {
    // La page qui suit doit déjà voir le nouveau jeton : on met à jour les cookies de la requête…
    request.cookies.set(ACCESS_COOKIE, tokens.access_token);
    request.cookies.set(REFRESH_COOKIE, tokens.refresh_token);
    const headers = new Headers(request.headers);
    headers.set("cookie", request.cookies.toString());
    const response = NextResponse.next({ request: { headers: headers } });
    // … et ceux du navigateur, pour les requêtes suivantes.
    response.cookies.set(ACCESS_COOKIE, tokens.access_token, optionsCookie(tokens.expires_in, isHttps(request)));
    response.cookies.set(
      REFRESH_COOKIE,
      tokens.refresh_token,
      optionsCookie(tokens.refresh_expires_in, isHttps(request)),
    );
    return response;
  }
  // Renouvellement refusé, mais jeton d'accès encore valable (deux demandes en même temps) : on continue.
  if (session && session.expire > now) return NextResponse.next();

  // Sinon, une nouvelle connexion. Si la session Keycloak est encore ouverte, elle est immédiate
  // (sans redemander le mot de passe) : la personne ne voit qu'un aller-retour.
  const login = new URL("/login", request.url);
  if (path !== "/") login.searchParams.set("next", path);
  const response = NextResponse.redirect(login);
  response.cookies.delete(ACCESS_COOKIE);
  response.cookies.delete(REFRESH_COOKIE);
  return response;
}

export const config = {
  // Tout, sauf les fichiers fixes du site (JavaScript, CSS) : ils ne contiennent aucune donnée.
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"],
};
