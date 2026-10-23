// Réglages de l'interface, lus dans les variables d'environnement AU LANCEMENT du serveur
// Next.js (jamais à la construction) : la même image Docker sert pour toutes les instances.
//
//   Variable         Rôle                                                Défaut
//   API_URL          adresse et port de l'API (sans / final)             http://127.0.0.1:8000
//   PORT             port du site (lu par « npm run dev / start »)        5173 en dev, 8080 déployé
//   INSTANCE_NAME    nom affiché dans le bandeau (vide = pas de bandeau)
//   INSTANCE_COLOR   couleur du bandeau                                   rouge si « prod », orange sinon
//
// Ce fichier n'est utilisé que côté serveur : le navigateur ne voit jamais API_URL.

const PROD_RED = "#c92a2a";
const ORANGE = "#c2410c";

// Couleurs acceptées : #rgb, #rrggbb (avec ou sans transparence), un nom (green), rgb(…) ou hsl(…).
// Trois motifs simples plutôt qu'un seul compliqué (rapides à vérifier, quelle que soit la valeur).
const COLORS = [/^#[0-9a-f]{3,8}$/i, /^[a-z]{1,30}$/i, /^(?:rgb|hsl)a?\([0-9., %/]{1,40}\)$/i];
const isColor = (text: string) => COLORS.some((pattern) => pattern.test(text));

function value(name: string): string {
  return (process.env[name] ?? "").trim();
}

/** L'adresse sans ses « / » finaux (retirés un par un : plus sûr qu'une expression régulière, toujours rapide). */
function withoutTrailingSlash(url: string): string {
  while (url.endsWith("/")) url = url.slice(0, -1);
  return url;
}

/** Adresse de l'API, sans « / » final. */
export function apiUrl(): string {
  return withoutTrailingSlash(value("API_URL") || "http://127.0.0.1:8000");
}

export type Instance = { name: string; color: string };

/** Nom et couleur de l'instance (recette, production…), ou null s'il n'y a pas de nom. */
export function readInstance(): Instance | null {
  const name = value("INSTANCE_NAME");
  if (!name) return null;
  const color = value("INSTANCE_COLOR");
  const byDefault = /^(prod|production)$/i.test(name) ? PROD_RED : ORANGE;
  return { name, color: isColor(color) ? color : byDefault };
}
