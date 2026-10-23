"use server";
// Déconnexion, exécutée sur le serveur Next.js. La connexion, elle, passe par la page de
// connexion (Keycloak, à l'allure de l'outil) : voir demarrer/ et retour/.
import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import { closeSessionKeycloak } from "@/lib/oauth";
import { ACCESS_COOKIE, REFRESH_COOKIE } from "@/lib/session";

/** Ferme la session (ici et chez Keycloak), puis renvoie vers la connexion. */
export async function logout(): Promise<void> {
  await closeSession();
  redirect("/login");
}

/** Efface les cookies et ferme la session chez Keycloak : la prochaine connexion redemandera le mot de passe. */
export async function closeSession(): Promise<void> {
  const store = await cookies();
  const refreshToken = store.get(REFRESH_COOKIE)?.value;
  if (refreshToken) await closeSessionKeycloak(refreshToken);
  store.delete(ACCESS_COOKIE);
  store.delete(REFRESH_COOKIE);
}
