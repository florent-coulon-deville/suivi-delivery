// Espace « Saisie » : gérer tous les objets (listes, socle, déploiement).
//
// Le serveur lit les données et les listes fermées dans l'API, puis envoie la page et la
// partie interactive (components/edit/). Les enregistrements repassent par le serveur
// (actions.ts). Réservée aux rôles EDITOR et ADMIN : pour les autres, ni les données
// ni le code de l'espace ne sont envoyés au navigateur. Un développeur (EDITOR) n'y voit que
// les livraisons (versions, paramètres, installations) ; la structure est à l'administrateur.
import AccessDenied from "@/components/AccessDenied";
import ApiAlert from "@/components/ApiAlert";
import EditArea from "@/components/edit/EditArea";
import { ApiError } from "@/lib/api";
import { loadEnumerations, loadAll } from "@/lib/data";
import { isAdmin, readSession, canEdit } from "@/lib/session";

export default async function Edit() {
  const role = (await readSession())?.role;
  if (!canEdit(role)) return <AccessDenied role="Saisie" />;
  let data;
  let enumerations;
  try {
    [data, enumerations] = await Promise.all([loadAll(), loadEnumerations()]);
  } catch (_error) {
    if (_error instanceof ApiError) return <ApiAlert message={_error.message} />;
    throw _error;
  }
  return <EditArea data={data} enumerations={enumerations} structure={isAdmin(role)} />;
}
