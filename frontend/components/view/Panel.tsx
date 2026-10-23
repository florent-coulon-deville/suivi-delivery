// Panneau de détail, qui glisse depuis la droite.
//
// Il s'ouvre au clic sur un module ou une version, et se ferme avec ✕, la touche Échap ou un
// clic à côté. Trois onglets :
//   « Ce qui tourne »  pour l'environnement choisi : emplacement, namespace, cluster, paramètres
//   « Historique »     les installations successives sur ses emplacements
//   « Fiche »          dépendances, utilisateurs, versions et compatibilités du module
import type { ReactNode } from "react";

import Drawer from "@/components/Drawer";
import { checkboxKey, type State, type Card, type Occupation } from "@/lib/state";
import {
  typeClass,
  versionClass,
  toUppercase,
  formatDate,
  ago,
  typeLabel,
  environmentTint,
} from "@/lib/format";
import type { Module } from "@/lib/types";
import { describeCondition } from "@/lib/versions";

import type { Tab, Selection } from "./selection";

const TABS: [Tab, string][] = [
  ["service", "Ce qui tourne"],
  ["history", "Historique"],
  ["card", "Fiche"],
];

type Props = { state: State; selection: Selection; change: (selection: Selection) => void; close: () => void };

export default function Panel({ state, selection, change, close }: Readonly<Props>) {
  const { environments } = state;
  const occupations = (environmentId: number): Occupation[] =>
    state.occupations[checkboxKey(selection.moduleId, environmentId)] ?? [];
  const group = state.groups.find((g) => g.modules.some((m) => m.id === selection.moduleId));
  const module = group?.modules.find((m) => m.id === selection.moduleId);
  const card = state.cards[selection.moduleId];
  // Le module a pu disparaître (supprimé puis « Actualiser ») : on ferme simplement.
  if (!group || !module || !card) return null;
  const { application } = group;

  // Sans environnement choisi, on prend le premier où le module a sa place.
  const environmentId =
    selection.environmentId ?? environments.find((env) => occupations(env.id).length)?.id ?? null;
  const here = environmentId === null ? [] : occupations(environmentId);

  const go = (changes: Partial<Selection>) => change({ ...selection, environmentId, ...changes });

  return (
    <Drawer close={close} title={`Détail du module ${module.code}`}>
      <header className="panel-header">
        <div>
          <div className="panel-overline">
            Application {application.identifier} · trigramme {application.trigram}
          </div>
          <h2>
            {module.code}
            <span className={`label ${typeClass(module)}`}>{typeLabel(module)}</span>
          </h2>
          <div className="panel-subtitle">{module.name}</div>
        </div>
        <button type="button" className="close" onClick={close} aria-label="Fermer">
          ✕
        </button>
      </header>

      <nav className="panel-tabs">
        {TABS.map(([key, label]) => (
          <button
            type="button"
            key={key}
            className={selection.tab === key ? "active" : ""}
            onClick={() => go({ tab: key })}
          >
            {label}
          </button>
        ))}
      </nav>

      {selection.tab !== "card" && (
        <div className="choice-env">
          {environments.map((env, position) => {
            const list = occupations(env.id);
            const current = list.find((o) => o.current)?.current;
            return (
              <button
                type="button"
                key={env.id}
                disabled={list.length === 0}
                className={`${environmentTint(position)} ${env.id === environmentId ? "active" : ""}`}
                onClick={() => go({ environmentId: env.id })}
                title={list.length === 0 ? "Pas d'emplacement dans cet environnement" : env.label}
              >
                <span className={env.is_prod ? "env-prod" : ""}>{env.code}</span>
                {current && <span className={`point ${versionClass(current.version)}`} />}
              </button>
            );
          })}
        </div>
      )}

      <div className="panel-body">
        {selection.tab === "service" && <ServiceTab occupations={here} />}
        {selection.tab === "history" && <HistoryTab occupations={here} />}
        {selection.tab === "card" && <CardTab card={card} />}
      </div>
    </Drawer>
  );
}

function Field({ label, children }: Readonly<{ label: string; children: ReactNode }>) {
  return (
    <>
      <dt>{label}</dt>
      <dd>{children}</dd>
    </>
  );
}

function ServiceTab({ occupations }: Readonly<{ occupations: Occupation[] }>) {
  if (occupations.length === 0) return <p className="subtle">Ce module n'a pas d'emplacement ici.</p>;
  return occupations.map(({ slot, namespace, cluster, zone, current }) => (
    <article key={slot.id} className="block">
      {current ? (
        <div className="block-version">
          <span className={`version large ${versionClass(current.version)}`}>
            <span className="version-number">{current.version.number}</span>
          </span>
          <div>
            <div className="block-title">{current.version.type === "RELEASE" ? "Release" : "Snapshot"}</div>
            <div className="subtle">
              installée le {formatDate(current.date)} · {ago(current.date)}
            </div>
          </div>
        </div>
      ) : (
        <div className="block-version">
          <span className="version large empty">
            <span className="version-number">vide</span>
          </span>
          <div className="subtle">Emplacement réservé, rien n'y est encore installé.</div>
        </div>
      )}
      <dl className="grid">
        <Field label="Emplacement">
          <code>{slot.release_name}</code>
        </Field>
        <Field label="Namespace">
          <code>{namespace.name}</code>
        </Field>
        <Field label="Cluster">
          {cluster.code} <span className="subtle">({cluster.is_prod ? "prod" : "hors prod"})</span>
        </Field>
        <Field label="Zone réseau">{toUppercase(zone.code)}</Field>
        {current && (
          <>
            <Field label="Paramètre technique">
              <span className="bullet">{current.technical.name}</span>
            </Field>
            <Field label="Paramètre applicatif">
              <span className="bullet">{current.application.name}</span>
            </Field>
          </>
        )}
      </dl>
    </article>
  ));
}

function HistoryTab({ occupations }: Readonly<{ occupations: Occupation[] }>) {
  const installations = occupations
    .flatMap((o) =>
      [o.current, ...o.previous].flatMap((i) => (i ? [{ ...i, slot: o.slot }] : [])),
    )
    .sort((a, b) => (a.date < b.date ? 1 : -1));
  if (installations.length === 0) return <p className="subtle">Aucune installation ici pour l'instant.</p>;
  return (
    <ol className="timeline">
      {installations.map((i, position) => (
        <li key={i.id} className={position === 0 ? "current" : ""}>
          <span className={`timeline-point ${versionClass(i.version)}`} />
          <div className="timeline-content">
            <div>
              <span className={`version ${versionClass(i.version)}`}>
                <span className="version-number">{i.version.number}</span>
              </span>
              {position === 0 && <span className="label current">en service</span>}
            </div>
            <div className="subtle">
              {formatDate(i.date)} · <code>{i.slot.release_name}</code>
            </div>
            <div className="subtle">
              paramètres : technique {i.technical.name} · applicatif {i.application.name}
            </div>
          </div>
        </li>
      ))}
    </ol>
  );
}

function ModuleList({ modules, empty }: Readonly<{ modules: Module[]; empty: string }>) {
  if (modules.length === 0) return <span className="subtle">{empty}</span>;
  return (
    <div className="label-list">
      {modules.map((m) => (
        <span key={m.id} className={`label ${typeClass(m)}`}>
          {m.code}
        </span>
      ))}
    </div>
  );
}

function CardTab({ card }: Readonly<{ card: Card }>) {
  return (
    <>
      <article className="block">
        <dl className="grid">
          <Field label="A besoin de">
            <ModuleList modules={card.needs} empty="aucun module" />
          </Field>
          <Field label="Utilisé par">
            <ModuleList modules={card.users} empty="aucun module" />
          </Field>
        </dl>
      </article>

      <h3 className="section-title">Versions ({card.versions.length})</h3>
      {card.versions.length === 0 ? (
        <p className="subtle">Aucune version déclarée.</p>
      ) : (
        card.versions.map(({ version, inService, compatibilities }) => (
          <article key={version.id} className="block block-row">
            <span className={`version ${versionClass(version)}`}>
              <span className="version-number">{version.number}</span>
            </span>
            <div className="block-row-text">
              <div>
                {inService.length ? (
                  <>
                    tourne en{" "}
                    {inService.map((env) => (
                      <span key={env.id} className={`bullet ${env.is_prod ? "bullet-prod" : ""}`}>
                        {env.code}
                      </span>
                    ))}
                  </>
                ) : (
                  <span className="subtle">ne tourne nulle part</span>
                )}
              </div>
              {compatibilities.length > 0 && (
                <div className="subtle">
                  requiert{" "}
                  {compatibilities.map((c) => (
                    <code key={c.id} className="condition">
                      {c.required.code} {describeCondition(c)}
                    </code>
                  ))}
                </div>
              )}
            </div>
          </article>
        ))
      )}
    </>
  );
}
