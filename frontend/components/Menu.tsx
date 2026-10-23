"use client";
// Menu déroulant : un bouton qui ouvre une petite liste d'actions (ou de liens).
//
// Sert à regrouper les actions pour ne pas multiplier les boutons : « ⋯ » au bout de chaque ligne
// d'un tableau (Modifier, Supprimer…), nom de la personne dans la barre du haut (Mon compte,
// Se déconnecter). Les éléments sont passés tels quels (boutons, liens, formulaires) avec la
// classe « menu-element ». Le menu se ferme après un choix, avec Échap ou par un clic à côté.
//
// La liste est placée par rapport à la fenêtre (position fixe), sous le bouton : un tableau qui
// défile ne la coupe donc pas. Elle se ferme quand la page défile, pour ne pas rester en l'air.
import { type CSSProperties, type ReactNode, useEffect, useRef, useState } from "react";

type Props = {
  label: ReactNode; // contenu du bouton : « ⋯ », un nom…
  title: string; // nom lu par les lecteurs d'écran et bulle d'aide
  className?: string; // allure du bouton (bouton-secondaire par défaut)
  children: ReactNode;
};

export default function Menu({ label, title, className = "button-secondary", children }: Readonly<Props>) {
  // null = fermé ; sinon, la place de la liste dans la fenêtre.
  const [place, setPlace] = useState<CSSProperties | null>(null);
  const open = place !== null;
  const frame = useRef<HTMLDivElement>(null);
  const close = () => setPlace(null);

  const toggle = (button: HTMLElement) => {
    if (open) return close();
    const r = button.getBoundingClientRect();
    setPlace({ top: r.bottom + 4, right: document.documentElement.clientWidth - r.right });
  };

  useEffect(() => {
    if (!open) return;
    // Un clic à côté ferme le menu ; un choix dans le menu aussi, une fois son action lancée.
    // Sauf un bouton qui envoie un formulaire (Se déconnecter) : fermer le menu retirerait le
    // formulaire de la page avant son envoi ; la page change de toute façon.
    const onClick = (e: MouseEvent) => {
      const target = e.target as Element;
      if (!frame.current?.contains(target) || target.closest(".menu-element:not([type=submit])")) close();
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.preventDefault(); // un tiroir ouvert derrière reste ouvert
        close();
      }
    };
    document.addEventListener("click", onClick);
    window.addEventListener("keydown", onKey);
    window.addEventListener("scroll", close, true);
    window.addEventListener("resize", close);
    return () => {
      document.removeEventListener("click", onClick);
      window.removeEventListener("keydown", onKey);
      window.removeEventListener("scroll", close, true);
      window.removeEventListener("resize", close);
    };
  }, [open]);

  return (
    <div className="menu" ref={frame}>
      <button
        type="button"
        className={className}
        aria-haspopup="true"
        aria-expanded={open}
        aria-label={title}
        title={title}
        onClick={(e) => toggle(e.currentTarget)}
      >
        {label}
      </button>
      {place && (
        <div className="menu-list" style={place}>
          {children}
        </div>
      )}
    </div>
  );
}
