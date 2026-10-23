// Probe Kubernetes / OpenShift du serveur de l'interface : GET /health → 200 « ok ».
// Ne dépend pas de l'API : si l'API est arrêtée, l'interface reste vivante et l'affiche.
export const dynamic = "force-dynamic";

export function GET() {
  return new Response("ok\n", { headers: { "Content-Type": "text/plain; charset=utf-8" } });
}
