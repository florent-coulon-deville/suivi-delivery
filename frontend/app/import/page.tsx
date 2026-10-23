// « Import » : recharger une configuration depuis le fichier Excel de l'export (mode fusion).
// Le formulaire (choix du fichier, aperçu, import) est dans ImportForm.
import ImportForm from "@/components/import/ImportForm";

export default function Import() {
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
