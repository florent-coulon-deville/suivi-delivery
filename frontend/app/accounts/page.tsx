// « Comptes » : qui peut se connecter, et avec quel rôle (comptes gardés par Keycloak, gérés ici
// par l'API). Réservée à l'ADMIN : pour les autres, ni les données ni le code de la page
// ne sont envoyés au navigateur.
import AccessDenied from "@/components/AccessDenied";
import ApiAlert from "@/components/ApiAlert";
import AccountManagement from "@/components/accounts/AccountManagement";
import { ApiError, read } from "@/lib/api";
import { isAdmin, readSession } from "@/lib/session";
import type { Account } from "@/lib/types";

export default async function Accounts() {
  const session = await readSession();
  if (!session || !isAdmin(session.role)) return <AccessDenied role="Administration" />;
  let accounts;
  try {
    accounts = await read<Account[]>("accounts");
  } catch (_error) {
    if (_error instanceof ApiError) return <ApiAlert message={_error.message} />;
    throw _error;
  }
  return <AccountManagement accounts={accounts} me={session.identifier} />;
}
