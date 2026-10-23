// Export de toute la configuration : GET /configuration → fichier Excel à télécharger.
//
// Le serveur Next.js demande le fichier à l'API (GET /api/configuration, avec le jeton de la
// session) et le transmet au navigateur, qui ne parle jamais à l'API. Le nom du fichier porte celui
// de l'instance (INSTANCE_NAME), pour ne pas confondre les exports de la recette et de la prod.
// Ouvert à tout rôle (VIEWER) : on n'exporte que ce qu'on peut déjà lire. Sans session,
// proxy.ts renvoie vers la page de connexion.
import { ApiError, download } from "@/lib/api";
import { readInstance } from "@/lib/settings";

export const dynamic = "force-dynamic";

export async function GET() {
  let response: Response;
  try {
    response = await download("configuration");
  } catch (error) {
    if (!(error instanceof ApiError)) throw error; // dont la redirection vers la connexion
    const message =
      error.status === 403 ? "Droits insuffisants pour exporter" : "Export impossible : l'API ne répond pas";
    return new Response(`${message}\n`, {
      status: error.status === 403 ? 403 : 502,
      headers: { "Content-Type": "text/plain; charset=utf-8" },
    });
  }
  return new Response(response.body, {
    headers: {
      "Content-Type": response.headers.get("Content-Type") ?? "application/octet-stream",
      "Content-Disposition": `attachment; filename="${fileName()}"`,
      "Cache-Control": "no-store",
    },
  });
}

/** Ex. suivi-delivery-recette-2026-10-14.xlsx (sans nom d'instance : suivi-delivery-2026-10-14.xlsx). */
function fileName(): string {
  const instance = (readInstance()?.name ?? "")
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "") // sans accents
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-|-$/g, "");
  const date = new Date().toISOString().slice(0, 10);
  return ["suivi-delivery", instance, date].filter(Boolean).join("-") + ".xlsx";
}
