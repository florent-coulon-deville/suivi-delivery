// /login : point d'entrée de la connexion (proxy.ts, déconnexion, changement de mot de passe…).
//
// Une simple page, qui relance une navigation complète vers /login/start (la route qui
// prépare PKCE et envoie sur la page de connexion), avec les mêmes paramètres (?suite, ?action…). Voir components/FullNavigation.tsx pour le pourquoi.
import FullNavigation from "@/components/FullNavigation";

type Props = { searchParams: Promise<Record<string, string | string[] | undefined>> };

export default async function Login({ searchParams }: Readonly<Props>) {
  const parameters = new URLSearchParams();
  for (const [name, value] of Object.entries(await searchParams)) {
    if (typeof value === "string") parameters.set(name, value);
  }
  const request = parameters.toString();
  const url = request ? `/login/start?${request}` : "/login/start";
  return <FullNavigation url={url} />;
}
