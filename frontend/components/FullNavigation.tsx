"use client";
// Envoie le navigateur vers une adresse par une VRAIE navigation (window.location), et non par la
// navigation interne de Next.js.
//
// Pourquoi : la connexion passe par des routes serveur (/login/start, /login/end/clear,
// /login/callback) qui posent des cookies et redirigent. La navigation interne de Next.js ne sait
// pas les suivre proprement : elle affichait la page de connexion sous une mauvaise adresse, et
// l'envoi du formulaire échouait (« This page couldn't load »). Les pages /login et
// /login/end n'affichent donc que ce composant, qui relance une navigation complète.
import { useEffect } from "react";

export default function FullNavigation({ url }: Readonly<{ url: string }>) {
  useEffect(() => {
    globalThis.location.replace(url);
  }, [url]);
  return (
    <p className="login-help">
      Redirection… <a href={url}>continuer</a>
    </p>
  );
}
