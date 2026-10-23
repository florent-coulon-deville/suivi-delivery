// Espace « Saisie » : gérer tous les objets (listes, socle, déploiement).
//
// Le serveur lit les données et les listes fermées dans l'API, puis envoie la page et la
// partie interactive (components/edit/). Les enregistrements repassent par le serveur
// (actions.ts).
import ApiAlert from "@/components/ApiAlert";
import EditArea from "@/components/edit/EditArea";
import { ApiError } from "@/lib/api";
import { loadEnumerations, loadAll } from "@/lib/data";

export default async function Edit() {
  let data;
  let enumerations;
  try {
    [data, enumerations] = await Promise.all([loadAll(), loadEnumerations()]);
  } catch (_error) {
    if (_error instanceof ApiError) return <ApiAlert message={_error.message} />;
    throw _error;
  }
  return <EditArea data={data} enumerations={enumerations} />;
}
