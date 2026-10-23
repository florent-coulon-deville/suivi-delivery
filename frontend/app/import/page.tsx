// « Import » : recharger une configuration depuis le fichier Excel de l'export (mode fusion).
// Réservé à l'ADMIN : pour les autres, ni la page ni son code ne partent vers le navigateur
// (et l'API refuse, 403). Le formulaire (choix du fichier, aperçu, import) est dans ImportForm.
import AccessDenied from "@/components/AccessDenied";
import ImportForm from "@/components/import/ImportForm";
import { isAdmin, readSession } from "@/lib/session";

export default async function Import() {
  const session = await readSession();
  if (!session || !isAdmin(session.role)) return <AccessDenied role="Administration" />;
  return (
    <section className="main-card">
      <div className="card-header">
        <div>
          <h2>Import de la configuration</h2>
          <p className="subtitle">
            Le fichier Excel de l'export (bouton « Exporter »), éventuellement modifié ou partiel. Ce qui manque est
            ajouté, ce qui a changé est mis à jour, rien n'est retiré. Tout ou rien : s'il reste un problème, rien n'est
            importé.
          </p>
        </div>
      </div>
      <ImportForm />
    </section>
  );
}
