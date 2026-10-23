"use client";
// Barre du haut : onglets selon le rôle, bouton « ⟳ Actualiser », et le nom de la personne,
// qui ouvre un menu (Mon compte, Se déconnecter).
// Composant « client » : il a besoin de savoir, dans le navigateur, sur quelle page on se
// trouve pour souligner l'onglet actif.
//
// Masquer un onglet n'est qu'un confort : chaque page vérifie le rôle sur le serveur, puis l'API.
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useTransition } from "react";

import { logout } from "@/app/login/actions";
import Menu from "@/components/Menu";
import type { Role } from "@/lib/session";

type User = { name: string; role: Role | null; canEdit: boolean; isAdmin: boolean };

export default function Navigation({ user }: Readonly<{ user: User | null }>) {
  const page = usePathname();
  const router = useRouter();
  const [loading, start] = useTransition();
  if (!user) return <span className="area" />;

  const areas = [
    { path: "/", title: "Ce qui tourne" },
    ...(user.canEdit ? [{ path: "/edit", title: "Saisie" }] : []),
    ...(user.isAdmin
      ? [
          { path: "/import", title: "Import" },
          { path: "/audit-log", title: "Journal" },
          { path: "/accounts", title: "Comptes" },
        ]
      : []),
  ];

  return (
    <>
      <nav className="tabs">
        {areas.map(({ path, title }) => {
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
      {/* Le nom ouvre un menu : « Mon compte » et « Se déconnecter » regroupés. */}
      <Menu
        className={page.startsWith("/me") ? "button-secondary active" : "button-secondary"}
        title="Mon compte et déconnexion"
        label={
          <>
            <span className="user-name">{user.name}</span> <span aria-hidden="true">▾</span>
          </>
        }
      >
        <div className="menu-info">Rôle : {user.role?.toLowerCase() ?? "none"}</div>
        <Link href="/me" className="menu-element">
          Mon compte
        </Link>
        <div className="menu-separator" />
        <form action={logout}>
          <button type="submit" className="menu-element">
            Se déconnecter
          </button>
        </form>
      </Menu>
    </>
  );
}
