// « Journal » : qui a créé, modifié ou supprimé quoi, et quand (GET /api/audit-log).
// Réservé à l'ADMIN : pour les autres, ni les données ni le code de la page ne sont
// envoyés au navigateur (et l'API refuse, 403). Page calculée sur le serveur : les filtres sont un simple formulaire
// (méthode GET), qui recharge la page avec les critères dans l'adresse.
import Link from "next/link";

import AccessDenied from "@/components/AccessDenied";
import ApiAlert from "@/components/ApiAlert";
import { ApiError, read } from "@/lib/api";
import { formatDate } from "@/lib/format";
import { ACTIONS, changes, instantParis, objectLabel, objectName, OBJECTS } from "@/lib/audit-log";
import { isAdmin, readSession } from "@/lib/session";
import type { AuditEntry } from "@/lib/types";

const LIMITS = ["50", "200", "1000"];

type Props = { searchParams: Promise<Record<string, string | string[] | undefined>> };

export default async function AuditLog({ searchParams }: Readonly<Props>) {
  const session = await readSession();
  if (!session || !isAdmin(session.role)) return <AccessDenied role="Administration" />;
  const parameters = await searchParams;
  const text = (name: string) => (typeof parameters[name] === "string" ? (parameters[name] as string).trim() : "");
  const filters = {
    author: text("author"),
    object: text("object"),
    action: text("action") in ACTIONS ? text("action") : "",
    from: text("from"),
    to: text("to"),
    limit: LIMITS.includes(text("limit")) ? text("limit") : "200",
  };

  // Les dates de l'écran sont des jours, à Paris : du début du premier à la fin du dernier.
  const request = new URLSearchParams({ limit: filters.limit });
  if (filters.author) request.set("author", filters.author);
  if (filters.object) request.set("object", filters.object);
  if (filters.action) request.set("action", filters.action);
  const since = instantParis(filters.from, "00:00:00");
  const until = instantParis(filters.to, "23:59:59");
  if (since) request.set("since", since);
  if (until) request.set("until", until);

  let rows: AuditEntry[];
  try {
    rows = await read<AuditEntry[]>(`audit-log?${request.toString()}`);
  } catch (_error) {
    if (_error instanceof ApiError) return <ApiAlert message={_error.message} />;
    throw _error;
  }

  return (
    <section className="main-card">
      <div className="card-header">
        <div>
          <h2>Journal</h2>
          <p className="subtitle">
            Qui a créé, modifié ou supprimé quoi, et quand. Le journal ne se modifie ni ne s'efface.
          </p>
        </div>
      </div>

      <form className="filters" method="get" action="/audit-log">
        <input
          className="field-filter"
          name="author"
          placeholder="Auteur (identifiant)"
          defaultValue={filters.author}
          aria-label="Auteur"
        />
        <select name="object" defaultValue={filters.object} aria-label="Objet">
          <option value="">Tous les objets</option>
          {OBJECTS.map((o) => (
            <option key={o.table} value={o.table}>
              {o.label}
            </option>
          ))}
        </select>
        <select name="action" defaultValue={filters.action} aria-label="Action">
          <option value="">Toutes les actions</option>
          {Object.entries(ACTIONS).map(([value, label]) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </select>
        <label className="filter-date">
          Du <input type="date" name="from" defaultValue={filters.from} />
        </label>
        <label className="filter-date">
          au <input type="date" name="to" defaultValue={filters.to} />
        </label>
        <select name="limit" defaultValue={filters.limit} aria-label="Nombre de lignes">
          {LIMITS.map((l) => (
            <option key={l} value={l}>
              {l} dernières
            </option>
          ))}
        </select>
        <button type="submit" className="button-secondary">
          Filtrer
        </button>
        <Link href="/audit-log" className="button-secondary">
          Tout effacer
        </Link>
      </form>

      {rows.length === 0 ? (
        <div className="empty-state">
          <div className="empty-state-icon">∅</div>
          Aucune action ne correspond.
        </div>
      ) : (
        <div className="table-container">
          <table className="edit-table audit-log-table">
            <thead>
              <tr>
                <th>Date</th>
                <th>Auteur</th>
                <th>Action</th>
                <th>Objet</th>
                <th>Détail</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <AuditEntryRow key={row.id} row={row} />
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

function AuditEntryRow({ row }: Readonly<{ row: AuditEntry }>) {
  const updated = changes(row);
  const name = objectName(row);
  return (
    <tr>
      <td className="audit-log-date">{formatDate(row.date)}</td>
      <td>
        <code>{row.author}</code>
        {row.author_kind === "PROGRAM" && <span className="bullet">programme</span>}
      </td>
      <td>
        <span className={`bullet audit-log-${row.action.toLowerCase()}`}>{ACTIONS[row.action]}</span>
      </td>
      <td>
        {objectLabel(row.object)} {name && <code>{name}</code>}{" "}
        {/^\d+$/.test(row.object_id) && <span className="subtle-text">n° {row.object_id}</span>}
      </td>
      <td>
        {updated.length > 0 && (
          <ul className="audit-log-changes">
            {updated.map((c) => (
              <li key={c.field}>
                <strong>{c.field}</strong> : {c.before} → {c.after}
              </li>
            ))}
          </ul>
        )}
        <details>
          <summary className="subtle-text">{row.action === "UPDATE" ? "Avant / après" : "Contenu"}</summary>
          <pre className="audit-log-content">
            {JSON.stringify(row.action === "DELETE" ? row.before : (row.after ?? row.before), null, 2)}
            {row.action === "UPDATE" && `\n\nAvant :\n${JSON.stringify(row.before, null, 2)}`}
          </pre>
        </details>
      </td>
    </tr>
  );
}
