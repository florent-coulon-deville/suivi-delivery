// Formulaire générique de création / modification, construit à partir de la description
// d'un objet (ressources.ts).
//
// Création     → save(objet, null, corps)  → POST /api/<objet>
// Modification → save(objet, id, corps)    → PUT  /api/<objet>/<id> (l'objet complet)
// Création groupée (batchCreationFields, ex. namespaces) → createBatch(objet, corps) → POST /api/<objet>/lot
// En cas de refus, le message de l'API s'affiche en haut du formulaire.
import { type FormEvent, useState } from "react";

import { createBatch, save } from "@/app/edit/actions";
import FilterableList, { simplify } from "@/components/FilterableList";
import { asText } from "@/lib/format";
import type { Enumerations } from "@/lib/types";

import {
  type Field as FieldDescription,
  type Context,
  type ResourceDescription,
  type Element,
  label,
  type Value,
  valueLabel,
  type Values,
} from "./resources";

/** Valeurs de départ : celles de l'élément modifié, ou les valeurs par défaut. */
function initialValues(fields: FieldDescription[], element: Element | null): Values {
  return Object.fromEntries(
    fields.map((c) => {
      const value = element ? element[c.name] : c.fallback;
      if (c.type === "references") return [c.name, (value as number[] | undefined) ?? []];
      if (c.type === "boolean") return [c.name, Boolean(value)];
      return [c.name, asText(value)];
    }),
  );
}

/** Transforme les valeurs du formulaire (du texte) en corps JSON pour l'API. */
function buildBody(fields: FieldDescription[], values: Values): Record<string, unknown> {
  const body: Record<string, unknown> = {};
  for (const c of fields) {
    const v = values[c.name];
    if (c.visible && !c.visible(values)) continue; // champ masqué : pas envoyé (ex. version_max hors BETWEEN)
    if (c.type === "boolean" || c.type === "references") body[c.name] = v;
    // Un champ facultatif vide n'est pas envoyé : il prend sa valeur par défaut.
    else if (v === "" || v === undefined) continue;
    else if (c.type === "reference" || c.type === "count") body[c.name] = Number(v);
    else body[c.name] = v;
  }
  return body;
}

type FieldProps = {
  field: FieldDescription;
  values: Values;
  change: (name: string, value: Value) => void;
  ctx: Context;
  enumerations: Enumerations;
};

export function Field({ field, values, change, ctx, enumerations }: Readonly<FieldProps>) {
  const value = values[field.name];
  const id = `field-${field.name}`;
  const proposed = (): Element[] =>
    field.resource
      ? (ctx.d[field.resource] as Element[]).filter((e) => !field.filter || field.filter(e, values, ctx))
      : [];

  let edit;
  switch (field.type) {
    case "boolean":
      return (
        <label className="field checkbox-field">
          <input type="checkbox" checked={Boolean(value)} onChange={(e) => change(field.name, e.target.checked)} />
          <span>{field.label}</span>
        </label>
      );
    case "list":
      edit = (
        <FilterableList
          id={id}
          value={asText(value)}
          required={field.required}
          change={(v) => change(field.name, v)}
          options={(enumerations[field.enumeration ?? ""] ?? []).map((v) => ({ value: v, text: valueLabel(v) }))}
        />
      );
      break;
    case "reference":
      edit = (
        <FilterableList
          id={id}
          value={asText(value)}
          required={field.required}
          change={(v) => change(field.name, v)}
          options={proposed().map((e) => ({
            value: String(e.id),
            text: field.resource ? label(field.resource, e, ctx) : String(e.id),
          }))}
        />
      );
      break;
    case "references":
      edit = (
        <FilterableCheckboxes
          list={proposed()}
          chosen={value as number[]}
          text={(e) => (field.resource ? label(field.resource, e, ctx) : String(e.id))}
          change={(chosen) => change(field.name, chosen)}
        />
      );
      break;
    default:
      edit = (
        <input
          id={id}
          type={field.type === "count" ? "number" : "text"}
          className={field.uppercase ? "uppercase" : undefined}
          value={asText(value)}
          required={field.required}
          onChange={(e) => change(field.name, e.target.value)}
        />
      );
  }
  return (
    <div className="field">
      <label htmlFor={id}>
        {field.label}
        {field.required && <span className="required"> *</span>}
      </label>
      {edit}
      {field.help && <div className="field-help">{field.help}</div>}
    </div>
  );
}

type Props = {
  resource: ResourceDescription;
  element: Element | null; // null : création
  ctx: Context;
  enumerations: Enumerations;
  afterSave: () => void;
  cancel: () => void;
};

export default function Form({ resource, element, ctx, enumerations, afterSave, cancel }: Readonly<Props>) {
  // Création groupée possible : ses champs à elle (ex. plusieurs clusters pour un namespace).
  const byBatch = element === null && resource.batchCreationFields !== undefined;
  // À la création, des champs en plus éventuels (ex. créer aussi les emplacements d'un module).
  const fields =
    (byBatch ? resource.batchCreationFields : undefined) ??
    (element === null ? [...resource.fields, ...(resource.extraCreationFields ?? [])] : resource.fields);
  const [values, setValues] = useState<Values>(() => initialValues(fields, element));
  const [error, setError] = useState<string | null>(null);
  const [sending, setSending] = useState(false);

  const change = (name: string, value: Value) => setValues((v) => ({ ...v, [name]: value }));
  const buttonLabel = element ? "Enregistrer" : "Créer";

  const validate = async (e: FormEvent) => {
    e.preventDefault();
    setSending(true);
    setError(null);
    const body = buildBody(fields, values);
    const result = byBatch
      ? await createBatch(resource.key, body)
      : await save(resource.key, element?.id ?? null, body);
    setSending(false);
    if (result.ok) afterSave();
    else setError(result.message);
  };

  return (
    <form className="form" onSubmit={validate}>
      {error && (
        <div className="form-alert" role="alert">
          <strong>Refusé :</strong> {error}
        </div>
      )}
      {fields
        .filter((c) => !c.visible || c.visible(values))
        .map((c) => (
          <Field key={c.name} field={c} values={values} change={change} ctx={ctx} enumerations={enumerations} />
        ))}
      <div className="form-actions">
        <button type="button" className="button-secondary" onClick={cancel}>
          Annuler
        </button>
        <button type="submit" className="button-primary" disabled={sending}>
          {sending ? "Enregistrement…" : buttonLabel}
        </button>
      </div>
    </form>
  );
}

type PropsCases = {
  list: Element[];
  chosen: number[];
  text: (element: Element) => string;
  change: (chosen: number[]) => void;
};

/** Choix multiples : des cases à cocher, avec un filtre au-dessus dès qu'il y a de quoi filtrer. */
function FilterableCheckboxes({ list, chosen, text, change }: Readonly<PropsCases>) {
  const [filter, setFilter] = useState("");
  const search = simplify(filter);
  // Les éléments cochés restent toujours visibles, même s'ils ne correspondent pas au filtre.
  const visibleItems = list.filter((e) => chosen.includes(e.id) || simplify(text(e)).includes(search));
  return (
    <div className="multiple-checkboxes">
      {list.length === 0 && <span className="subtle">Rien à proposer pour l'instant.</span>}
      {list.length > 5 && (
        <input
          className="checkbox-filter"
          placeholder="Filtrer…"
          aria-label="Filtrer la liste"
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
        />
      )}
      {visibleItems.map((e) => (
        <label key={e.id} className="checkbox-field">
          <input
            type="checkbox"
            checked={chosen.includes(e.id)}
            onChange={(ev) => change(ev.target.checked ? [...chosen, e.id] : chosen.filter((x) => x !== e.id))}
          />
          <code>{text(e)}</code>
        </label>
      ))}
      {list.length > 0 && visibleItems.length === 0 && <span className="subtle">Aucun choix ne contient « {filter} ».</span>}
    </div>
  );
}
