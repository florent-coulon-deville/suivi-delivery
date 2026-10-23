"use client";
// Liste déroulante où l'on peut taper pour filtrer (une « combobox ») : remplace les <select> des
// écrans de saisie, utilisables même avec beaucoup de choix.
//
//   - on tape directement dans le champ : seuls restent les choix qui CONTIENNENT ce texte, sans
//     tenir compte des majuscules ni des accents (« integration » trouve « Intégration ») ;
//   - clavier : ↓ ↑ pour se déplacer, Entrée pour choisir, Échap pour annuler ; à la souris : clic ;
//   - en quittant le champ sans choisir, il reprend le choix précédent (jamais de texte libre) ;
//   - « ✕ » vide un champ facultatif ;
//   - accessible : rôles combobox / listbox / option (lecteurs d'écran).
import { type KeyboardEvent, useEffect, useId, useMemo, useRef, useState } from "react";

export type Option = { value: string; text: string };

type Props = {
  id?: string;
  options: Option[];
  value: string; // "" : rien de choisi
  change: (value: string) => void;
  required?: boolean;
  disabled?: boolean;
  prompt?: string; // texte quand rien n'est choisi
  ariaLabel?: string;
};

/** Texte sans majuscules ni accents, pour comparer. */
export const simplify = (text: string) =>
  text
    .normalize("NFD")
    .replaceAll(/\p{Diacritic}/gu, "")
    .toLowerCase();

export default function FilterableList({
  id,
  options,
  value,
  change,
  required = false,
  disabled = false,
  prompt = "— choisir —",
  ariaLabel,
}: Readonly<Props>) {
  const listId = useId();
  const field = useRef<HTMLInputElement>(null);
  const chosen = options.find((o) => o.value === value);
  const [query, setQuery] = useState<string | null>(null); // null : on n'est pas en train de taper
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);

  const proposed = useMemo(() => {
    if (!query) return options;
    const search = simplify(query);
    return options.filter((o) => simplify(o.text).includes(search));
  }, [options, query]);

  // Champ obligatoire sans choix : le navigateur bloque l'envoi du formulaire, avec ce message.
  useEffect(() => {
    field.current?.setCustomValidity(required && !chosen ? "Choisissez dans la liste" : "");
  }, [required, chosen]);

  const choose = (option: Option) => {
    change(option.value);
    setQuery(null);
    setOpen(false);
  };
  const cancel = () => {
    setQuery(null);
    setOpen(false);
  };

  const key = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      if (!open) {
        setOpen(true);
        return;
      }
      const not = e.key === "ArrowDown" ? 1 : -1;
      setActive((a) => Math.min(Math.max(a + not, 0), Math.max(proposed.length - 1, 0)));
    } else if (e.key === "Enter" && open) {
      e.preventDefault(); // ne pas envoyer le formulaire : on choisit
      const option = proposed[active];
      if (option) choose(option);
    } else if (e.key === "Escape" && open) {
      // Échap ferme la liste seulement, pas le tiroir du formulaire autour (components/Drawer.tsx).
      e.preventDefault();
      e.stopPropagation();
      cancel();
    }
  };

  // En quittant le champ : un texte qui correspond exactement à un choix le choisit ; sinon, on
  // revient au choix précédent.
  const leave = () => {
    if (query !== null) {
      const exact = options.find((o) => simplify(o.text) === simplify(query));
      if (exact) change(exact.value);
    }
    cancel();
  };

  const idOption = (index: number) => `${listId}-${index}`;
  return (
    <div className={`filterable-list ${disabled ? "disabled" : ""}`}>
      <input
        ref={field}
        id={id}
        role="combobox"
        aria-label={ariaLabel}
        aria-expanded={open}
        aria-controls={listId}
        aria-autocomplete="list"
        aria-activedescendant={open && proposed[active] ? idOption(active) : undefined}
        autoComplete="off"
        disabled={disabled}
        required={required}
        placeholder={prompt}
        value={query ?? chosen?.text ?? ""}
        onFocus={(e) => {
          e.target.select();
          setOpen(true);
          setActive(Math.max(proposed.indexOf(chosen as Option), 0));
        }}
        onClick={() => setOpen(true)}
        onChange={(e) => {
          setQuery(e.target.value);
          setOpen(true);
          setActive(0);
        }}
        onKeyDown={key}
        onBlur={leave}
      />
      {!required && value && !disabled && (
        <button
          type="button"
          className="filterable-list-clear"
          aria-label="Vider"
          onMouseDown={(e) => e.preventDefault()}
          onClick={() => change("")}
        >
          ✕
        </button>
      )}
      <span className="filterable-list-arrow" aria-hidden="true">
        ▾
      </span>
      {open && !disabled && (
        <ul id={listId} role="listbox" className="filterable-list-option">
          {proposed.length === 0 && <li className="filterable-list-nothing">Aucun choix ne contient « {query} »</li>}
          {proposed.map((o, index) => (
            <li
              key={o.value}
              id={idOption(index)}
              role="option"
              aria-selected={o.value === value}
              className={index === active ? "active" : undefined}
              onMouseDown={(e) => e.preventDefault()} // garder le champ actif
              onMouseEnter={() => setActive(index)}
              onClick={() => choose(o)}
              // Le clavier passe d'abord par le champ (flèches, Entrée) ; ceci couvre le cas où l'élément a le focus.
              onKeyDown={(e) => {
                if (e.key === "Enter" || e.key === " ") choose(o);
              }}
            >
              {o.text}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
