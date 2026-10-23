// Réglages de l'interface, lus dans les variables d'environnement AU LANCEMENT du serveur
// Next.js (jamais à la construction) : la même image Docker sert pour toutes les instances.
//
//   Variable         Rôle                                                Défaut
//   API_URL          adresse et port de l'API (sans / final)             http://127.0.0.1:8000
//   PORT             port du site (lu par « npm run dev / start »)        5173 en dev, 8080 déployé
//   INSTANCE_NAME    nom affiché dans le bandeau (vide = pas de bandeau)
//   INSTANCE_COLOR   couleur du bandeau                                   rouge si « prod », orange sinon
//   APP_FRONTEND_URL adresse publique de l'interface, telle que la tape    http://localhost:<PORT>
//                    le navigateur (sans / final) : adresse de retour de
//                    la connexion (<adresse>/login/callback), et de
//                    Keycloak vu du navigateur (<adresse>/auth)
//   KEYCLOAK_URL     adresse INTERNE de Keycloak, avec /auth (sans /      http://127.0.0.1:8081/auth
//                    final) : l'interface y échange les codes contre les
//                    jetons, et y relaie les pages de connexion (/auth)
//   KEYCLOAK_REALM   domaine Keycloak de l'outil                          suivi-delivery
//
// Ce fichier n'est utilisé que côté serveur : le navigateur ne voit jamais API_URL ni KEYCLOAK_URL.

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

/** Adresse publique de l'interface (celle du navigateur), sans « / » final. */
export function frontendUrl(): string {
  return withoutTrailingSlash(value("APP_FRONTEND_URL") || `http://localhost:${value("PORT") || "5173"}`);
}

/**
 * Une page du site, à l'adresse publique. Dans un conteneur, l'adresse vue par une route du serveur
 * est l'adresse interne (http://0.0.0.0:8080) : une redirection vers elle échouerait dans le navigateur.
 */
export const sitePage = (path: string): URL => new URL(path, `${frontendUrl()}/`);

/** Adresse interne de Keycloak (avec /auth), sans « / » final : vue du serveur seulement. */
export function keycloakUrl(): string {
  return withoutTrailingSlash(value("KEYCLOAK_URL") || "http://127.0.0.1:8081/auth");
}

/** Le domaine Keycloak de l'outil (lettres, chiffres, - et _ ; sinon celui par défaut). */
export function keycloakRealm(): string {
  const realm = value("KEYCLOAK_REALM");
  return /^[A-Za-z0-9_-]{1,100}$/.test(realm) ? realm : "suivi-delivery";
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
