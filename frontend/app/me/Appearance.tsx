"use client";
// « Mon compte » → Apparence : le thème de couleurs (automatique, clair, sombre). Le choix est
// gardé dans le compte (il suit la personne sur tous ses postes) : voir lib/theme.ts.
import { useRouter } from "next/navigation";
import { useState, useTransition } from "react";

import type { Theme } from "@/lib/theme";

import { changeTheme } from "./actions";

const CHOICE: [Theme, string, string][] = [
  ["AUTO", "◐ Automatique", "comme le réglage de l'ordinateur"],
  ["LIGHT", "☀ Clair", "toujours clair"],
  ["DARK", "☾ Sombre", "toujours sombre"],
];

export default function Appearance({ theme }: Readonly<{ theme: Theme }>) {
  const router = useRouter();
  const [chosen, setChosen] = useState<Theme>(theme);
  const [error, setError] = useState<string | null>(null);
  const [sending, start] = useTransition();

  const choose = (theme: Theme) =>
    start(async () => {
      setError(null);
      const result = await changeTheme(theme);
      if (!result.ok) {
        setError(result.message);
        return;
      }
      setChosen(theme);
      router.refresh(); // le serveur renvoie la page dans le nouveau thème
    });

  return (
    <section className="main-card">
      <div className="card-header">
        <div>
          <h2>Apparence</h2>
          <p className="subtitle">Thème de couleurs de l'interface, retenu dans votre compte (sur tous vos postes).</p>
        </div>
      </div>
      <div className="account-page-form">
        <div className="segments" role="radiogroup" aria-label="Thème de couleurs">
          {CHOICE.map(([value, label, help]) => (
            <button
              type="button"
              role="radio"
              aria-checked={chosen === value}
              key={value}
              title={help}
              disabled={sending}
              className={chosen === value ? "segment active" : "segment"}
              onClick={() => choose(value)}
            >
              {label}
            </button>
          ))}
        </div>
        {error && (
          <div className="form-alert" role="alert">
            <strong>Refusé :</strong> {error}
          </div>
        )}
      </div>
    </section>
  );
}
