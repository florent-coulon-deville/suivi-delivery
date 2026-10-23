// Cadre commun à toutes les pages : bandeau de l'instance, barre du haut, onglets.
// Composant « serveur » : il est calculé sur le serveur, le navigateur ne reçoit que le HTML.
import type { Metadata } from "next";
import { cookies } from "next/headers";
import type { ReactNode } from "react";

import Navigation from "@/components/Navigation";
import { readInstance } from "@/lib/settings";
import { isTheme, themeAttribute, COOKIE_THEME } from "@/lib/theme";

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
  // Thème choisi sur ce navigateur (menu « Thème »), gardé dans un cookie : voir lib/theme.ts.
  const chosen = (await cookies()).get(COOKIE_THEME)?.value;
  const theme = themeAttribute(chosen);
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
            <Navigation theme={isTheme(chosen) ? chosen : "AUTO"} />
          </div>
        </header>
        <main className="page">{children}</main>
      </body>
    </html>
  );
}
