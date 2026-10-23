"use client";
// « Mon compte » → Accès par script : comment appeler l'API depuis un script, et fermer d'un coup
// tous ses accès par script (jetons hors ligne de Keycloak), par exemple si l'un d'eux a fuité.
import { useState, useTransition } from "react";

import { closeAccessByScript } from "./actions";

export default function AccessByScript() {
  const [confirm, setConfirm] = useState(false);
  const [message, setMessage] = useState<{ text: string; error?: boolean } | null>(null);
  const [sending, start] = useTransition();

  const close = () =>
    start(async () => {
      setConfirm(false);
      const result = await closeAccessByScript();
      setMessage(
        result.ok
          ? { text: "Accès par script fermés : chaque script devra se reconnecter." }
          : { text: result.message, error: true },
      );
    });

  return (
    <section className="main-card">
      <div className="card-header">
        <div>
          <h2>Accès par script</h2>
          <p className="subtitle">
            Pour appeler l'API depuis un script, à votre nom et avec vos droits : un « jeton hors ligne », obtenu
            en vous connectant une fois dans le navigateur (client <code>suivi-delivery-tools</code>, voir la
            documentation de l'API). Il reste valable 30 jours sans servir, un an au plus.
          </p>
        </div>
        {confirm ? (
          <span className="confirmation button-group">
            <span>Fermer tous mes accès par script ?</span>
            <button type="button" className="button-danger" onClick={close} disabled={sending}>
              Oui
            </button>
            <button type="button" className="button-secondary" onClick={() => setConfirm(false)}>
              Non
            </button>
          </span>
        ) : (
          <button type="button" className="button-secondary" onClick={() => setConfirm(true)} disabled={sending}>
            Fermer mes accès par script
          </button>
        )}
      </div>
      {message && <output className={message.error ? "banner error" : "banner success"}>{message.text}</output>}
    </section>
  );
}
