// Message affiché quand l'API ne répond pas (le détail technique reste dans les journaux du serveur).
// L'aide pour démarrer l'API n'est montrée qu'en développement, pas aux utilisateurs.
export default function ApiAlert({ message }: Readonly<{ message: string }>) {
  return (
    <div className="alert">
      <strong>Les données sont momentanément indisponibles</strong> ({message})
      <div>Réessayez dans un instant avec « Actualiser ». Si le problème continue, prévenez l'équipe qui gère l'outil.</div>
      {process.env.NODE_ENV === "development" && (
        <div className="subtle">
          En développement : démarrer l'API depuis <code>backend/</code> avec <code>uv run python -m app --reload</code>
        </div>
      )}
    </div>
  );
}
