// « Mon compte » : qui je suis, changer mon mot de passe, l'apparence (thème), et mes accès par script.
//
// Le mot de passe se change sur la page de connexion (Keycloak, à l'allure de l'outil) : le lien
// passe par /login/start?action=mot-de-passe, qui revient ici avec le résultat.
import ApiAlert from "@/components/ApiAlert";
import { ApiError, read } from "@/lib/api";
import type { Me } from "@/lib/types";

import AccessByScript from "./AccessByScript";
import Appearance from "./Appearance";

const MESSAGES: Record<string, { text: string; error?: boolean }> = {
  change: { text: "Mot de passe changé." },
  cancelled: { text: "Changement de mot de passe annulé : l'ancien reste valable." },
  error: { text: "Le changement de mot de passe n'a pas abouti : recommencez.", error: true },
};

type Props = { searchParams: Promise<Record<string, string | string[] | undefined>> };

export default async function MyAccount({ searchParams }: Readonly<Props>) {
  let me;
  try {
    me = await read<Me>("me");
  } catch (_error) {
    if (_error instanceof ApiError) return <ApiAlert message={_error.message} />;
    throw _error;
  }
  const result = (await searchParams)["password"];
  const message = typeof result === "string" ? MESSAGES[result] : undefined;
  return (
    <div className="account-page">
      <section className="main-card">
        <div className="card-header">
          <div>
            <h2>Mon compte</h2>
            <p className="subtitle">
              {me.name} · <code>{me.identifier}</code> ·{" "}
              {me.role ? `rôle ${me.role.toLowerCase()}` : "aucun rôle : demandez-en un à un administrateur"}
            </p>
          </div>
          {me.kind === "PERSON" && (
            // Vraie navigation (et non <Link>) : la page de connexion n'est pas une page de l'interface.
            <a className="button-secondary" href="/login/start?action=password&next=/me">
              Changer mon mot de passe
            </a>
          )}
        </div>
        {message && (
          <output className={message.error ? "banner error" : "banner success"}>{message.text}</output>
        )}
        {me.kind !== "PERSON" && (
          <p className="subtle account-page-form">
            Un programme n'a pas de mot de passe : sa clé se renouvelle dans « Comptes ».
          </p>
        )}
      </section>
      <Appearance theme={me.theme ?? "AUTO"} />
      {me.kind === "PERSON" && <AccessByScript />}
    </div>
  );
}
