// Bandeau de chiffres clés, en haut de l'écran. Calculé sur le serveur (aucune interaction).
import type { Summary as Digits } from "@/lib/state";
import { ago } from "@/lib/format";

type TileProps = { label: string; value: string | number; detail?: string; accent?: string; text?: boolean };

function Tile({ label, value, detail, accent, text }: Readonly<TileProps>) {
  return (
    <div className={`tile ${accent ?? ""}`}>
      <div className="tile-label">{label}</div>
      <div className={text ? "tile-value text" : "tile-value"}>{value}</div>
      {detail && <div className="tile-detail">{detail}</div>}
    </div>
  );
}

export default function Summary({ summary }: Readonly<{ summary: Digits }>) {
  const { applications, modules, inService, snapshots, installations, lastProd } = summary;
  return (
    <section className="summary">
      <Tile label="Applications" value={applications} />
      <Tile label="Modules" value={modules} />
      <Tile label="Déploiements en service" value={inService} detail={`${installations} installations au total`} />
      <Tile
        label="Snapshots en service"
        value={snapshots}
        detail="versions de travail, hors prod"
        accent={snapshots > 0 ? "accent-snapshot" : ""}
      />
      <Tile
        label="Dernière mise en prod"
        value={lastProd ? `${lastProd.module.code} ${lastProd.version.number}` : "—"}
        detail={lastProd ? ago(lastProd.date) : "none"}
        accent="accent-prod"
        text
      />
    </section>
  );
}
