"use server";
// Import de la configuration, exécuté SUR LE SERVEUR Next.js (Server Actions) : le fichier choisi
// dans le navigateur arrive ici, puis part vers l'API (PATCH /api/configuration), qui fait tout le
// travail. Le navigateur ne parle jamais à l'API.
//
// Une Server Action est joignable par quiconque atteint le site : on revérifie le fichier
// (présence, taille) ; l'API, elle, revérifie le contenu.
import { sendFile } from "@/lib/api";
import type { ImportReport } from "@/lib/types";

const TYPE_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet";
const MAX_SIZE = 10 * 1024 * 1024; // 10 Mo, comme l'API

export type ImportResult =
  { ok: true; report: ImportReport } | { ok: false; message: string; report?: ImportReport };

/** Aperçu : ce que l'import ferait, sans rien enregistrer. */
export async function checkImport(data: FormData): Promise<ImportResult> {
  return send(data, true);
}

/** Import pour de bon (tout ou rien). */
export async function importFile(data: FormData): Promise<ImportResult> {
  return send(data, false);
}

async function send(data: FormData, dryRun: boolean): Promise<ImportResult> {
  const file = data.get("file");
  if (!(file instanceof File) || file.size === 0) return { ok: false, message: "Choisissez un fichier Excel" };
  if (file.size > MAX_SIZE) return { ok: false, message: "Fichier trop gros (10 Mo au plus)" };

  const { status, content, message } = await sendFile(
    "PATCH",
    dryRun ? "configuration?dry_run=true" : "configuration",
    file,
    TYPE_XLSX,
  );
  if (status === 200) return { ok: true, report: content as ImportReport };
  // 409 : il reste des problèmes, le rapport est joint. Sinon (400, 422…) : le message de l'API.
  const report = (content as { report?: ImportReport } | null)?.report;
  return { ok: false, message, report };
}
