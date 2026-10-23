"use server";
// « Mon compte », sur le serveur Next.js : changer son thème de couleurs, et fermer ses accès par
// script. Le mot de passe, lui, se change sur la page de connexion (voir page.tsx).
import { cookies, headers } from "next/headers";

import { ApiError, write } from "@/lib/api";
import { COOKIE_THEME, isTheme, optionsCookieTheme } from "@/lib/theme";

type Result = { ok: true } | { ok: false; message: string };

async function execute(action: () => Promise<unknown>): Promise<Result> {
  try {
    await action();
    return { ok: true };
  } catch (_error) {
    if (_error instanceof ApiError) return { ok: false, message: _error.message };
    throw _error;
  }
}

/** Mes jetons hors ligne (scripts) ne marchent plus ; ma connexion à l'interface continue. */
export async function closeAccessByScript(): Promise<Result> {
  return execute(() => write("DELETE", "me/offline-access"));
}

// --- Apparence : le thème de couleurs -----------------------------------------------

/** Change le thème (il suit la personne partout), puis dans le cookie de ce navigateur. */
export async function changeTheme(theme: string): Promise<Result> {
  if (!isTheme(theme)) return { ok: false, message: "Thème inconnu" };
  const result = await execute(() => write("PATCH", "me", { theme }));
  if (!result.ok) return result;
  const https = (await headers()).get("x-forwarded-proto") === "https";
  (await cookies()).set(COOKIE_THEME, theme, optionsCookieTheme(https));
  return { ok: true };
}
