"use client";
// Formulaire de l'import : choisir le fichier, « Vérifier » (aperçu : rien n'est enregistré), puis
// « Importer ». Composant « client » : il garde le fichier choisi et le rapport affiché entre les
// deux étapes. Le fichier part vers le serveur Next.js (Server Actions de app/import/actions.ts).
import { useState, useTransition } from "react";

import { importFile, type ImportResult, checkImport } from "@/app/import/actions";
import type { ImportReport } from "@/lib/types";

export default function ImportForm() {
  const [file, setFile] = useState<File | null>(null);
  const [result, setResult] = useState<ImportResult | null>(null);
  const [inProgress, start] = useTransition();

  const send = (action: typeof checkImport) => {
    if (!file) return;
    const data = new FormData();
    data.set("file", file);
    start(async () => setResult(await action(data)));
  };

  const report = result?.report;
  // « Importer » seulement après un aperçu sans problème, pour ce fichier-là.
  const ready = result?.ok === true && report?.dry_run === true && report.problems.length === 0;
  const imported = result?.ok === true && report?.applied === true;

  return (
    <div className="import">
      <div className="filters">
        <input
          type="file"
          accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
          aria-label="Fichier Excel à importer"
          onChange={(e) => {
            setFile(e.target.files?.[0] ?? null);
            setResult(null);
          }}
        />
        <button
          type="button"
          className="button-secondary"
          disabled={!file || inProgress}
          onClick={() => send(checkImport)}
        >
          {inProgress && !ready ? "Vérification…" : "Vérifier"}
        </button>
        <button
          type="button"
          className="button-primary"
          disabled={!ready || inProgress}
          onClick={() => send(importFile)}
        >
          {inProgress && ready ? "Import…" : "Importer"}
        </button>
      </div>

      {result && !result.ok && <output className="banner error">{result.message}</output>}
      {imported && <output className="banner success">Import terminé : {summarize(report)}.</output>}
      {ready && (
        <output className="banner success">
          Aucun problème : {summarize(report)}. Rien n'est encore enregistré : cliquez sur « Importer ».
        </output>
      )}
      {report && <Report report={report} />}
    </div>
  );
}

function summarize(report: ImportReport): string {
  const total = (field: "additions" | "updates") => report.sheets.reduce((sum, o) => sum + o[field], 0);
  const [additions, updates] = [total("additions"), total("updates")];
  if (additions + updates === 0) return "rien à changer, tout est déjà à jour";
  return `${additions} ajout(s), ${updates} modification(s)`;
}

function Report({ report }: Readonly<{ report: ImportReport }>) {
  return (
    <>
      {report.problems.length > 0 && (
        <div className="banner error">
          <strong>{report.problems.length} problème(s) : rien ne sera importé tant qu'il en reste.</strong>
          <ul className="import-problems">
            {report.problems.map((p) => (
              <li key={`${p.sheet}-${p.row}-${p.message}`}>
                {p.sheet ? `${p.sheet}, ligne ${p.row} : ` : "Ensemble du fichier : "}
                {p.message}
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="table-container">
        <table className="edit-table">
          <thead>
            <tr>
              <th>Onglet</th>
              <th>Ajouts</th>
              <th>Modifications</th>
              <th>Inchangés</th>
            </tr>
          </thead>
          <tbody>
            {report.sheets.map((o) => (
              <tr key={o.sheet}>
                <td>{o.sheet}</td>
                <td>{o.additions > 0 ? <span className="bullet audit-log-create">+{o.additions}</span> : "—"}</td>
                <td>
                  {o.updates > 0 ? <span className="bullet audit-log-update">{o.updates}</span> : "—"}
                </td>
                <td>{o.unchanged || "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {report.changes.length > 0 && (
        <details className="import-detail">
          <summary>Détail des {report.changes.length} changement(s)</summary>
          <table className="edit-table">
            <thead>
              <tr>
                <th>Onglet</th>
                <th>Ligne</th>
                <th>Action</th>
                <th>Objet</th>
                <th>Changé</th>
              </tr>
            </thead>
            <tbody>
              {report.changes.map((c) => (
                <tr key={`${c.sheet}-${c.row}`}>
                  <td>{c.sheet}</td>
                  <td>{c.row}</td>
                  <td>
                    <span className={`bullet ${c.action === "ADD" ? "audit-log-create" : "audit-log-update"}`}>
                      {c.action === "ADD" ? "Ajout" : "Modification"}
                    </span>
                  </td>
                  <td>
                    <code>{c.object}</code>
                  </td>
                  <td>{c.details.join(" ; ")}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </details>
      )}
    </>
  );
}
