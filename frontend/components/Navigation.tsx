"use client";
// Barre du haut : onglets, bouton « ⟳ Actualiser », « ⤓ Exporter », et le menu « Thème ».
// Composant « client » : il a besoin de savoir, dans le navigateur, sur quelle page on se
// trouve pour souligner l'onglet actif.
//
// Pas de connexion ni de rôles : tous les onglets sont visibles par tout le monde.
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useTransition } from "react";

import { changeTheme } from "@/app/theme";
import Menu from "@/components/Menu";
import type { Theme } from "@/lib/theme";

const AREAS = [
  { path: "/", title: "Ce qui tourne" },
  { path: "/edit", title: "Saisie" },
  { path: "/import", title: "Import" },
  { path: "/audit-log", title: "Journal" },
];

const THEMES: [Theme, string, string][] = [
  ["AUTO", "◐ Automatique", "comme le réglage de l'ordinateur"],
  ["LIGHT", "☀ Clair", "toujours clair"],
  ["DARK", "☾ Sombre", "toujours sombre"],
];

export default function Navigation({ theme }: Readonly<{ theme: Theme }>) {
  const page = usePathname();
  const router = useRouter();
  const [loading, start] = useTransition();

  // Le serveur range le choix dans un cookie, puis renvoie la page dans le nouveau thème.
  const choose = (chosen: Theme) =>
    start(async () => {
      if ((await changeTheme(chosen)).ok) router.refresh();
    });

  return (
    <>
      <nav className="tabs">
        {AREAS.map(({ path, title }) => {
          const active = path === "/" ? page === "/" : page.startsWith(path);
          return (
            <Link key={path} href={path} className={active ? "tab active" : "tab"}>
              {title}
            </Link>
          );
        })}
      </nav>
      {/* Redemande la page au serveur, qui relit les données de l'API ; l'état de l'écran est gardé. */}
      <button
        type="button"
        className="button-secondary"
        onClick={() => start(() => router.refresh())}
        disabled={loading}
        title="Relire les données"
      >
        <span className={loading ? "running" : ""}>⟳</span> {loading ? "Chargement…" : "Actualiser"}
      </button>
      {/* Toute la configuration en fichier Excel (app/configuration/route.ts) : une action, donc
          l'allure d'un bouton. Lien ordinaire, et non <Link> : c'est un fichier à télécharger, pas une page. */}
      <a className="button-secondary" href="/configuration" title="Toute la configuration dans un fichier Excel">
        ⤓ Exporter
      </a>
      {/* Thème de couleurs, retenu par ce navigateur (lib/theme.ts). */}
      <Menu title="Thème de couleurs" label={<>Thème <span aria-hidden="true">▾</span></>}>
        {THEMES.map(([value, label, help]) => (
          <button
            type="button"
            key={value}
            title={help}
            className="menu-element"
            aria-current={theme === value}
            onClick={() => choose(value)}
          >
            {label} {theme === value && "✓"}
          </button>
        ))}
      </Menu>
    </>
  );
}
