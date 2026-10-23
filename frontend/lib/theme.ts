// Thème de couleurs de l'interface : AUTO (comme l'ordinateur), LIGHT ou DARK.
//
// Le choix est gardé DANS LE COMPTE (API : PATCH /api/me), pour suivre la personne sur tous ses
// postes. Le serveur Next.js en garde une copie dans le cookie sd_theme, posé à la connexion
// (connexion/retour/route.ts) et à chaque changement (« Mon compte » → Apparence) : il peut ainsi
// envoyer chaque page directement dans le bon thème, sans appeler l'API ni faire clignoter
// l'écran. La page de connexion (Keycloak), où l'on ne sait pas encore qui est là, garde le
// dernier thème choisi sur ce navigateur (copié par proxy.ts dans le cookie sd_theme_auth).
//
// Le thème est posé sur <html data-theme="light|dark"> (app/layout.tsx) ; les couleurs sont
// dans app/styles.css.

export const THEMES = ["AUTO", "LIGHT", "DARK"] as const;
export type Theme = (typeof THEMES)[number];

export const COOKIE_THEME = "sd_theme";
// Copie du thème pour les pages de connexion de Keycloak (proxy.ts) : lisible par leur code, sous /auth.
export const COOKIE_THEME_AUTH = "sd_theme_auth";

export const isTheme = (value: unknown): value is Theme => THEMES.includes(value as Theme);

/** Réglages du cookie du thème : un an, pour tout le site. Lisible par le serveur seulement. */
export function optionsCookieTheme(https: boolean) {
  return { httpOnly: true, sameSite: "lax" as const, secure: https, path: "/", maxAge: 365 * 24 * 3600 };
}

/** Valeur de l'attribut data-theme de <html> : rien pour AUTO (le réglage de l'ordinateur décide). */
export function themeAttribute(theme: string | undefined): "light" | "dark" | undefined {
  if (theme === "LIGHT") return "light";
  if (theme === "DARK") return "dark";
  return undefined;
}
