// Réglages de Next.js (fixés à la construction, identiques pour toutes les instances).
// Ce qui change d'une instance à l'autre (adresse de l'API, nom de l'instance…) est lu
// au lancement, dans les variables d'environnement : voir lib/settings.ts.
import type { NextConfig } from "next";

const config: NextConfig = {
  // Construit un dossier autonome (.next/standalone) avec seulement ce qu'il faut pour tourner :
  // l'image Docker reste petite, sans node_modules complet.
  output: "standalone",
  // Sans « sharp », le module de Next.js qui retaille les images (l'interface n'en affiche pas) :
  // c'est le seul à contenir du code propre à un système et un processeur. Sans lui, le dossier
  // autonome est du JavaScript seul : construit n'importe où (Mac, PC, CI), il tourne tel quel
  // dans l'image Docker, en amd64 comme en arm64 (voir docs/frontend.md).
  images: { unoptimized: true },
  outputFileTracingExcludes: { "*": ["node_modules/sharp/**", "node_modules/@img/**"] },
  // N'annonce pas « X-Powered-By: Next.js » : inutile de dire aux curieux ce qui tourne.
  poweredByHeader: false,
  // En-têtes de sécurité ajoutés à toutes les réponses (pas besoin de nginx devant Next.js).
  // Next.js attend une promesse ; la liste est fixe, rien à attendre : d'où Promise.resolve.
  headers: () => Promise.resolve([{ source: "/:path*", headers: SECURITY_HEADERS }]),
  experimental: {
    // Import de la configuration (/import) : le fichier Excel passe par une Server Action, puis par
    // proxy.ts. L'API en accepte 10 Mo ; un peu plus ici pour l'enveloppe de l'envoi (multipart).
    serverActions: { bodySizeLimit: "11mb" },
    proxyClientMaxBodySize: "11mb",
  },
};

const SECURITY_HEADERS = [
  // Le site ne peut pas être affiché dans un cadre d'un autre site (protection contre le « clickjacking »).
  { key: "Content-Security-Policy", value: "frame-ancestors 'none'" },
  { key: "X-Frame-Options", value: "DENY" },
  // Le navigateur ne devine pas le type d'un fichier : il suit celui annoncé par le serveur.
  { key: "X-Content-Type-Options", value: "nosniff" },
  // L'adresse complète des pages n'est pas transmise aux autres sites.
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  // Une fois venu en HTTPS, le navigateur n'utilise plus que le HTTPS pendant un an (ignoré en HTTP).
  { key: "Strict-Transport-Security", value: "max-age=31536000" },
  // L'interface n'utilise ni caméra, ni micro, ni position.
  { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=()" },
];

export default config;
