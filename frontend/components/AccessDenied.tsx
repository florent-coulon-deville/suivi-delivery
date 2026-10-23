// Message affiché à la place d'une page réservée à un autre rôle. Le code de la page n'est
// alors pas envoyé au navigateur.
export default function AccessDenied({ role }: Readonly<{ role: string }>) {
  return (
    <div className="alert">
      <strong>Accès réservé</strong>
      <div>Cette page demande le rôle « {role} ». Adressez-vous à un administrateur si vous en avez besoin.</div>
    </div>
  );
}
