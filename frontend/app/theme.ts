"use server";
// Changer le thème de couleurs (menu « Thème » de la barre du haut), sur le serveur Next.js :
// le choix est rangé dans le cookie sd_theme de ce navigateur (voir lib/theme.ts).
import { cookies, headers } from "next/headers";

import { COOKIE_THEME, isTheme, optionsCookieTheme } from "@/lib/theme";

export async function changeTheme(theme: string): Promise<{ ok: boolean }> {
  if (!isTheme(theme)) return { ok: false };
  const https = (await headers()).get("x-forwarded-proto") === "https";
  (await cookies()).set(COOKIE_THEME, theme, optionsCookieTheme(https));
  return { ok: true };
}
