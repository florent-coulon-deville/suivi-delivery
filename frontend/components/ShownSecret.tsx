"use client";
// Un secret montré UNE SEULE FOIS (la clé d'un programme) : l'outil n'en garde que
// l'empreinte, il ne pourra plus jamais l'afficher. Bouton pour le copier, puis pour le masquer.
type Props = { title: string; secret: string; hide: () => void };

export default function ShownSecret({ title, secret, hide }: Readonly<Props>) {
  return (
    <output className="shown-key">
      <div>
        <strong>{title}</strong> : notez-le maintenant, il ne sera plus jamais affiché.
      </div>
      <code>{secret}</code>
      <div className="key-actions">
        <button type="button" className="button-secondary" onClick={() => navigator.clipboard?.writeText(secret)}>
          Copier
        </button>
        <button type="button" className="button-secondary" onClick={hide}>
          C'est noté, masquer
        </button>
      </div>
    </output>
  );
}
