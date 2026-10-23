// GET /login/end/clear : efface une session que l'API ne reconnaît plus (jeton refusé : mot de
// passe changé, compte désactivé…), puis affiche la page de connexion.
//
// Une page ne peut pas effacer de cookie ; cette « route » le peut. lib/api.ts y renvoie dès que
// l'API répond 401 (par la page /login/end, voir app/login/end/page.tsx). Sans elle, la page de connexion, voyant encore un jeton, renverrait
// vers l'accueil, qui renverrait ici… en boucle.
import { type NextRequest, NextResponse } from "next/server";

import { sitePage } from "@/lib/settings";
import { ACCESS_COOKIE, REFRESH_COOKIE } from "@/lib/session";

export const dynamic = "force-dynamic";

export function GET(request: NextRequest) {
  const reason = request.nextUrl.searchParams.get("reason") === "password" ? "password" : "expired";
  const response = NextResponse.redirect(sitePage(`/login?${reason}=1`));
  response.cookies.delete(ACCESS_COOKIE);
  response.cookies.delete(REFRESH_COOKIE);
  return response;
}
