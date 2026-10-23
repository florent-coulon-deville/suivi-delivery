// /login/end : la session n'est plus reconnue par l'API (lib/api.ts y envoie dès un 401).
//
// Une simple page, qui relance une navigation complète vers /login/end/clear (la route qui
// efface les cookies de session, puis renvoie à la connexion). Voir components/FullNavigation.tsx.
import FullNavigation from "@/components/FullNavigation";

type Props = { searchParams: Promise<Record<string, string | string[] | undefined>> };

export default async function End({ searchParams }: Readonly<Props>) {
  const reason = (await searchParams).reason === "password" ? "password" : "expired";
  return <FullNavigation url={`/login/end/clear?reason=${reason}`} />;
}
