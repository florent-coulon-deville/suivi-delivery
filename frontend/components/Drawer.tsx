"use client";
// Tiroir : panneau qui glisse depuis la droite, par-dessus un voile sombre.
//
// Il se ferme avec la touche Échap ou un clic sur le voile (le bouton ✕ est dans le contenu).
// Le voile est un vrai bouton, placé à côté du panneau et non autour : un clic dans le panneau
// ne le ferme donc pas, et le clavier est géré sans code en plus.
import { type ReactNode, useEffect } from "react";

type Props = { close: () => void; title: string; children: ReactNode };

export default function Drawer({ close, title, children }: Readonly<Props>) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      // Déjà traitée (ex. Échap qui ferme une liste filtrable ouverte) : le tiroir reste ouvert.
      if (e.key === "Escape" && !e.defaultPrevented) close();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [close]);

  return (
    <div className="overlay">
      <button type="button" className="overlay-background" aria-label="Fermer" tabIndex={-1} onClick={close} />
      <aside className="panel" aria-label={title}>
        {children}
      </aside>
    </div>
  );
}
