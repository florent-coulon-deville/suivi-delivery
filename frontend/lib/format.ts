// Petites fonctions d'affichage partagées par les écrans (côté serveur comme côté navigateur).
import type { Module, ModuleVersion } from "./types";

// Fuseau fixe : la page est d'abord calculée sur le serveur (souvent en UTC), puis reprise
// par le navigateur. Avec un même fuseau des deux côtés, l'heure affichée est identique.
const TIMEZONE = "Europe/Paris";

/** Classe de la teinte pastel d'un environnement, d'après sa place dans l'ordre de promotion (8 teintes). */
export const environmentTint = (position: number): string => `env-tint-${position % 8}`;

/** Date courte : « 16/09/2026 20:00 ». */
export const formatDate = (iso: string): string =>
  new Date(iso).toLocaleString("fr-FR", { dateStyle: "short", timeStyle: "short", timeZone: TIMEZONE });

/** Date seule : « 16/09/2026 ». */
export const formatDay = (iso: string): string =>
  new Date(iso).toLocaleDateString("fr-FR", { dateStyle: "short", timeZone: TIMEZONE });

/** Ancienneté lisible : « aujourd'hui », « il y a 3 j », « il y a 2 mois ». */
export function ago(iso: string): string {
  const days = Math.floor((Date.now() - new Date(iso).getTime()) / 86_400_000);
  if (days <= 0) return "aujourd'hui";
  if (days === 1) return "yesterday";
  if (days < 31) return `il y a ${days} j`;
  const months = Math.floor(days / 30.5);
  if (months < 12) return `il y a ${months} mois`;
  const years = Math.floor(months / 12);
  return `il y a ${years} an${years > 1 ? "s" : ""}`;
}

/** Une valeur simple (texte, nombre, oui/non) en texte ; toute autre chose (objet, liste…) : "". */
export function asText(value: unknown): string {
  if (typeof value === "string") return value;
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  return "";
}

/** Un champ d'un formulaire envoyé, en texte ("" s'il manque ou si c'est un fichier). */
export const textField = (form: FormData, name: string): string => asText(form.get(name));

/** Classe CSS d'une version : « release » (vert) ou « snapshot » (orange). */
export const versionClass = (version: ModuleVersion): string => version.type.toLowerCase();

/** Libellé court du type de module. */
export const typeLabel = (module: Module): string => (module.type === "CAPABILITY" ? "capacité" : "métier");

/** Classe CSS de l'étiquette du type de module. */
export const typeClass = (module: Module): string => (module.type === "CAPABILITY" ? "capability" : "business");

/** Un code tel qu'on l'affiche, en majuscules (l'API le garde en minuscules : « interne » → « INTERNE »). */
export const toUppercase = (code: string): string => code.toUpperCase();
