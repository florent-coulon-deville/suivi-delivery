// Connexion impossible : le retour de la page de connexion n'a pas abouti (Keycloak ne répond pas,
// KEYCLOAK_URL fausse, demande trop ancienne). Le détail est dans les journaux du serveur, jamais
// dans la page.
import Link from "next/link";

export default function Unavailable() {
  return (
    <div className="login">
      <section className="login-card">
        <header className="login-header">
          <div className="login-logo" aria-hidden="true">
            ◆
          </div>
          <h1>Suivi de la delivery</h1>
          <p>Connexion impossible pour l'instant</p>
        </header>
        <div className="form-alert" role="alert">
          L'outil ne répond pas pour l'instant.
        </div>
        <p className="login-help">
          <Link href="/login">Réessayer</Link>
          <br />
          Si le problème persiste, adressez-vous à un administrateur de l'outil.
        </p>
      </section>
    </div>
  );
}
