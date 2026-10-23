"use client";
// Espace « Saisie » : gérer tous les objets.
// Sans le rôle ADMIN (structure = false), seulement les livraisons : versions de
// module, paramètres, installations. Les autres objets restent lus (listes des formulaires).
//
//   à gauche   les objets, regroupés (Listes, Socle, Déploiement), avec leur nombre
//   au centre  la liste des éléments de l'objet choisi, avec recherche
//   à droite   le formulaire (création ou modification), dans un tiroir
//
// Les écritures passent par le serveur Next.js (app/edit/actions.ts). Après chaque
// enregistrement ou suppression, la page est redemandée au serveur (router.refresh) :
// les données affichées, ici comme dans « Ce qui tourne », sont donc toujours à jour.
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";

import { remove } from "@/app/edit/actions";
import Menu from "@/components/Menu";
import Drawer from "@/components/Drawer";
import { toUppercase, asText } from "@/lib/format";
import { type Data, type Enumerations, RESOURCES_STRUCTURE, type Resource } from "@/lib/types";

import Form from "./Form";
import InstallationForm from "./InstallationForm";
import {
  type Field,
  type Column,
  type Context,
  buildContext,
  DESCRIPTIONS,
  type Element,
  GROUPS,
  label,
  valueLabel,
} from "./resources";

/** Texte d'une cellule du tableau pour un champ donné. */
function cellValue(field: Field, element: Element, ctx: Context): string {
  const v = element[field.name];
  if (field.type === "boolean") return v ? "oui" : "non";
  if (field.uppercase && typeof v === "string") return toUppercase(v);
  if (field.type === "list" && typeof v === "string") return valueLabel(v);
  if (field.type === "reference" && field.resource) return label(field.resource, ctx.byId(field.resource, v), ctx);
  if (field.type === "references" && field.resource) {
    const resource = field.resource;
    return (v as number[]).map((id) => label(resource, ctx.byId(resource, id), ctx)).join(", ") || "—";
  }
  return v == null ? "—" : asText(v);
}

type Message = { text: string; error?: boolean };

function Cell({ column, element }: Readonly<{ column: Column; element: Element }>) {
  const labels = column.labels?.(element);
  if (labels) {
    if (labels.length === 0) return <span className="subtle">—</span>;
    return (
      <span className="label-list">
        {labels.map((text) => (
          <code key={text} className="bullet">
            {text}
          </code>
        ))}
      </span>
    );
  }
  return column.code ? <code>{column.value(element)}</code> : column.value(element);
}

type Properties = { data: Data; enumerations: Enumerations; structure: boolean };

export default function EditArea({ data, enumerations, structure }: Readonly<Properties>) {
  const router = useRouter();
  // Les objets que ce compte peut modifier (la structure : administrateur seulement).
  const descriptions = useMemo(
    () => DESCRIPTIONS.filter((r) => structure || !RESOURCES_STRUCTURE.has(r.key)),
    [structure],
  );
  const [key, setKey] = useState<Resource>(descriptions[0]?.key ?? "module-versions");
  const [search, setSearch] = useState("");
  const [form, setForm] = useState<{ element: Element | null } | null>(null); // element null : création
  const [toDelete, setToDelete] = useState<number | null>(null); // id en attente de confirmation
  const [message, setMessage] = useState<Message | null>(null);

  const ctx = useMemo(() => buildContext(data), [data]);
  const resource = descriptions.find((r) => r.key === key) ?? (descriptions[0] as (typeof DESCRIPTIONS)[number]);
  const editable = resource.editable !== false;

  // Le message de confirmation disparaît tout seul après quelques secondes.
  useEffect(() => {
    if (!message) return undefined;
    const timer = setTimeout(() => setMessage(null), message.error ? 8000 : 3500);
    return () => clearTimeout(timer);
  }, [message]);

  const closeForm = useCallback(() => setForm(null), []);

  const changeResource = (newKind: Resource) => {
    setKey(newKind);
    setSearch("");
    setForm(null);
    setToDelete(null);
  };

  const elements = useMemo(() => {
    const text = search.trim().toLowerCase();
    const all = data[key] as Element[];
    if (!text) return all;
    return all.filter((e) =>
      [label(key, e, ctx), ...resource.fields.map((c) => cellValue(c, e, ctx))]
        .join(" ")
        .toLowerCase()
        .includes(text),
    );
  }, [data, key, search, ctx, resource]);

  const afterSave = () => {
    setForm(null);
    router.refresh();
    setMessage({ text: "Enregistré." });
  };

  const confirmDeletion = async (element: Element) => {
    setToDelete(null);
    const result = await remove(key, element.id);
    if (result.ok) {
      router.refresh();
      setMessage({ text: "Supprimé." });
    } else {
      setMessage({ text: result.message, error: true });
    }
  };

  const columns: Column[] = [
    ...(resource.extraColumns ?? []),
    ...resource.fields.map((c) => ({
      title: c.label,
      value: (e: Element) => cellValue(c, e, ctx),
      // Plusieurs éléments (ex. namespaces affectés) : une étiquette chacun, jamais coupée.
      labels:
        c.type === "references" && c.resource
          ? (e: Element) => {
              const targetResource = c.resource as Resource;
              return (e[c.name] as number[]).map((id) => label(targetResource, ctx.byId(targetResource, id), ctx));
            }
          : undefined,
    })),
  ];

  return (
    <div className="edit">
      <nav className="edit-menu">
        {GROUPS.filter((group) => descriptions.some((r) => r.group === group)).map((group) => (
          <div key={group} className="menu-group">
            <div className="menu-group-title">{group}</div>
            {descriptions.filter((r) => r.group === group).map((r) => (
              <button
                type="button"
                key={r.key}
                className={r.key === key ? "menu-link active" : "menu-link"}
                onClick={() => changeResource(r.key)}
              >
                <span>{r.title}</span>
                <span className="account-menu">{data[r.key].length}</span>
              </button>
            ))}
          </div>
        ))}
      </nav>

      <section className="main-card edit-content">
        <div className="card-header">
          <div>
            <h2>{resource.title}</h2>
            <p className="subtitle">{resource.help}</p>
          </div>
          <button type="button" className="button-primary" onClick={() => setForm({ element: null })}>
            + {resource.newLabel}
          </button>
        </div>

        <div className="filters">
          <div className="field-search">
            <span aria-hidden="true">⌕</span>
            <input type="search" placeholder="Rechercher…" value={search} onChange={(e) => setSearch(e.target.value)} />
          </div>
          <span className="subtle">
            {elements.length} élément{elements.length > 1 ? "s" : ""}
          </span>
        </div>

        {message && (
          <output className={message.error ? "banner error" : "banner success"}>
            {message.error && <strong>Refusé : </strong>}
            {message.text}
          </output>
        )}

        {elements.length === 0 ? (
          <div className="empty-state">
            <div className="empty-state-icon">∅</div>
            {search ? "Aucun élément ne correspond." : "Rien pour l'instant."}
          </div>
        ) : (
          <div className="table-container">
            <table className="edit-table">
              <thead>
                <tr>
                  {columns.map((c) => (
                    <th key={c.title}>{c.title}</th>
                  ))}
                  <th className="col-actions" />
                </tr>
              </thead>
              <tbody>
                {elements.map((e) => (
                  <tr key={e.id}>
                    {columns.map((c) => (
                      <td key={c.title}>
                        <Cell column={c} element={e} />
                      </td>
                    ))}
                    <td className="col-actions">
                      {/* Actions de la ligne regroupées dans un menu « ⋯ » ; la suppression demande confirmation. */}
                      {toDelete === e.id ? (
                        <span className="confirmation button-group">
                          <span>Supprimer ?</span>
                          <button type="button" className="button-danger" onClick={() => confirmDeletion(e)}>
                            Oui
                          </button>
                          <button type="button" className="button-secondary" onClick={() => setToDelete(null)}>
                            Non
                          </button>
                        </span>
                      ) : (
                        <Menu label="⋯" title="Actions sur cette ligne" className="button-secondary button-icon">
                          {editable && (
                            <>
                              <button type="button" className="menu-element" onClick={() => setForm({ element: e })}>
                                Modifier
                              </button>
                              <div className="menu-separator" />
                            </>
                          )}
                          <button type="button" className="menu-element danger" onClick={() => setToDelete(e.id)}>
                            Supprimer
                          </button>
                        </Menu>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {form && (
        <Drawer close={closeForm} title={resource.title}>
          <header className="panel-header">
            <div>
              <div className="panel-overline">{resource.title}</div>
              <h2>{form.element ? `Modifier ${label(key, form.element, ctx)}` : resource.newLabel}</h2>
            </div>
            <button type="button" className="close" onClick={closeForm} aria-label="Fermer">
              ✕
            </button>
          </header>
          <div className="panel-body">
            {resource.guidedForm ? (
              <InstallationForm ctx={ctx} afterSave={afterSave} cancel={closeForm} />
            ) : (
              <Form
                key={form.element?.id ?? "new"}
                resource={resource}
                element={form.element}
                ctx={ctx}
                enumerations={enumerations}
                afterSave={afterSave}
                cancel={closeForm}
              />
            )}
          </div>
        </Drawer>
      )}
    </div>
  );
}
