// Thème de couleurs de l'interface : AUTO (comme l'ordinateur), LIGHT ou DARK.
//
// Le choix est gardé dans un cookie de ce navigateur (sd_theme), posé à chaque changement (menu
// « Thème » de la barre du haut, app/theme.ts) : le serveur Next.js envoie ainsi chaque page
// directement dans le bon thème, sans faire clignoter l'écran. Pas de comptes : le choix vaut pour
// ce navigateur seulement.
//
// Le thème est posé sur <html data-theme="light|dark"> (app/layout.tsx) ; les couleurs sont
// dans app/styles.css.

export const THEMES = ["AUTO", "LIGHT", "DARK"] as const;
export type Theme = (typeof THEMES)[number];

export const COOKIE_THEME = "sd_theme";

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
