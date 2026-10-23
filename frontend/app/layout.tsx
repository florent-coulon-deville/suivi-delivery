// Cadre commun à toutes les pages : bandeau de l'instance, barre du haut, onglets selon le rôle.
// Composant « serveur » : il est calculé sur le serveur, le navigateur ne reçoit que le HTML.
import type { Metadata } from "next";
import { cookies } from "next/headers";
import type { ReactNode } from "react";

import Navigation from "@/components/Navigation";
import { readInstance } from "@/lib/settings";
import { isAdmin, readSession, canEdit } from "@/lib/session";
import { themeAttribute, COOKIE_THEME } from "@/lib/theme";

import "./styles.css";

// Toujours calculé à la demande : les réglages (variables d'environnement) sont lus au
// lancement du serveur, pas figés à la construction de l'image.
export const dynamic = "force-dynamic";

export function generateMetadata(): Metadata {
  const instance = readInstance();
  return { title: instance ? `Suivi de la delivery · ${instance.name}` : "Suivi de la delivery" };
}

export default async function Frame({ children }: Readonly<{ children: ReactNode }>) {
  const instance = readInstance();
  // Seuls le nom et le rôle vont au navigateur, pour les menus ; jamais le jeton.
  const session = await readSession();
  const user = session && {
    name: session.name,
    role: session.role,
    canEdit: canEdit(session.role),
    isAdmin: isAdmin(session.role),
  };
  // Thème choisi par la personne (« Mon compte » → Apparence), copié dans un cookie : voir lib/theme.ts.
  const theme = themeAttribute((await cookies()).get(COOKIE_THEME)?.value);
  return (
    <html lang="fr" data-theme={theme}>
      <body>
        <header className="top-bar">
          {instance && (
            <div className="instance-banner" style={{ background: instance.color }}>
              Instance : <strong>{instance.name}</strong>
            </div>
          )}
          <div className="top-bar-content">
            <div className="brand">
              <span className="logo" aria-hidden="true">
                ◆
              </span>{" "}
              Suivi de la delivery
            </div>
            <Navigation user={user} />
          </div>
        </header>
        <main className="page">{children}</main>
      </body>
    </html>
  );
}
