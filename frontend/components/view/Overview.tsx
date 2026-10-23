// Tableau principal « Ce qui tourne » : modules en lignes, environnements en colonnes.
//
// Chaque case montre la version qui tourne et depuis quand. Le détail est caché :
//   - clic sur une application : replie / déplie ses modules ;
//   - clic sur un module ou sur une version : ouvre le panneau de détail à droite.
// Ce sont de vrais boutons (utilisables au clavier) : agir sur l'écran = bouton.
import { Fragment, useMemo, useState } from "react";

import { checkboxKey, type State, type Occupation } from "@/lib/state";
import { typeClass, versionClass, ago, typeLabel, environmentTint } from "@/lib/format";
import type { Module, ModuleType } from "@/lib/types";

import type { Selection } from "./selection";

type Props = { state: State; selection: Selection | null; open: (selection: Selection) => void };

const TYPES: [ModuleType | "", string][] = [
  ["", "Tous"],
  ["CAPABILITY", "Capacités"],
  ["BUSINESS_PROJECT", "Métier"],
];

export default function Overview({ state, selection, open }: Readonly<Props>) {
  const { environments, groups } = state;
  const occupations = (moduleId: number, environmentId: number): Occupation[] =>
    state.occupations[checkboxKey(moduleId, environmentId)] ?? [];

  // --- Filtres ---
  const [text, setText] = useState("");
  const [applicationId, setApplicationId] = useState("");
  const [type, setType] = useState<ModuleType | "">("");
  const [onlyInstalled, setOnlyInstalled] = useState(false);

  // --- Applications repliées, colonne survolée ---
  const [collapsedIds, setCollapsedIds] = useState<Set<number>>(new Set());
  const [hoveredColumn, setHoveredColumn] = useState<number | null>(null);

  const toggle = (id: number) => {
    const next = new Set(collapsedIds);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    setCollapsedIds(next);
  };

  const filteredGroups = useMemo(() => {
    const search = text.trim().toLowerCase();
    const isInstalled = (m: Module) =>
      environments.some((env) => (state.occupations[checkboxKey(m.id, env.id)] ?? []).some((o) => o.current));
    return groups
      .filter((g) => !applicationId || String(g.application.id) === applicationId)
      .map((g) => ({
        ...g,
        modules: g.modules.filter(
          (m) =>
            (!search || m.code.includes(search) || m.name.toLowerCase().includes(search)) &&
            (!type || m.type === type) &&
            (!onlyInstalled || isInstalled(m)),
        ),
      }))
      .filter((g) => g.modules.length > 0);
  }, [state, groups, environments, text, applicationId, type, onlyInstalled]);

  const allCollapsed = groups.length > 0 && groups.every((g) => collapsedIds.has(g.application.id));
  const activeFilters = Boolean(text || applicationId || type || onlyInstalled);
  const clearFilters = () => {
    setText("");
    setApplicationId("");
    setType("");
    setOnlyInstalled(false);
  };

  return (
    <section className="main-card">
      <div className="card-header">
        <div>
          <h2>Ce qui tourne</h2>
          <p className="subtitle">La version en service de chaque module, environnement par environnement.</p>
        </div>
        <div className="legend">
          <span className="badge release" /> release{" "}
          <span className="badge snapshot" /> snapshot{" "}
          <span className="badge empty" /> emplacement vide
        </div>
      </div>

      <div className="filters">
        <div className="field-search">
          <span aria-hidden="true">⌕</span>
          <input
            type="search"
            placeholder="Rechercher un module…"
            value={text}
            onChange={(e) => setText(e.target.value)}
          />
        </div>
        <select value={applicationId} onChange={(e) => setApplicationId(e.target.value)}>
          <option value="">Toutes les applications</option>
          {groups.map((g) => (
            <option key={g.application.id} value={g.application.id}>
              {g.application.identifier} — {g.application.name}
            </option>
          ))}
        </select>
        <div className="segments">
          {TYPES.map(([value, label]) => (
            <button
              type="button"
              key={value}
              className={type === value ? "segment active" : "segment"}
              onClick={() => setType(value)}
            >
              {label}
            </button>
          ))}
        </div>
        <label className="toggle">
          <input type="checkbox" checked={onlyInstalled} onChange={(e) => setOnlyInstalled(e.target.checked)} />
          <span className="slider" />{" "}
          Installés seulement
        </label>
        <span className="area" />
        {activeFilters && (
          <button type="button" className="button-secondary" onClick={clearFilters}>
            Effacer les filtres
          </button>
        )}
        {/* Un seul bouton : il replie tout, ou déplie tout quand tout est déjà replié. */}
        <button
          type="button"
          className="button-secondary"
          onClick={() => setCollapsedIds(allCollapsed ? new Set() : new Set(groups.map((g) => g.application.id)))}
        >
          {allCollapsed ? "Tout déplier" : "Tout replier"}
        </button>
      </div>

      {filteredGroups.length === 0 ? (
        <div className="empty-state">
          <div className="empty-state-icon">∅</div>
          Aucun module ne correspond.
          {activeFilters && (
            <button type="button" className="button-secondary" onClick={clearFilters}>
              Effacer les filtres
            </button>
          )}
        </div>
      ) : (
        <div className="table-container" onMouseLeave={() => setHoveredColumn(null)}>
          <table className="matrix">
            <thead>
              <tr>
                <th className="col-module">Module</th>
                {environments.map((env, position) => (
                  <th
                    key={env.id}
                    className={`${environmentTint(position)} ${hoveredColumn === env.id ? "hovered" : ""}`}
                    onMouseEnter={() => setHoveredColumn(env.id)}
                  >
                    <div className={`env-header ${env.is_prod ? "prod" : ""}`}>
                      <span className="env-code">{env.code}</span>
                      <span className="env-label">{env.label}</span>
                    </div>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {filteredGroups.map(({ application, modules }) => {
                const collapsed = collapsedIds.has(application.id);
                return (
                  <Fragment key={application.id}>
                    <tr className="group-row">
                      <td colSpan={environments.length + 1} className="cell-button">
                        <button type="button" aria-expanded={!collapsed} onClick={() => toggle(application.id)}>
                          <span className={`chevron ${collapsed ? "" : "open"}`}>▸</span>
                          <span className="group-name">{application.identifier}</span>
                          <span className="group-label">{application.name}</span>
                          <span className="bullet">trigramme {application.trigram}</span>
                          <span className="bullet">
                            {modules.length} module{modules.length > 1 ? "s" : ""}
                          </span>
                        </button>
                      </td>
                    </tr>
                    {!collapsed &&
                      modules.map((module) => (
                        <tr
                          key={module.id}
                          className={selection?.moduleId === module.id ? "module-row selected" : "module-row"}
                        >
                          <td className="col-module cell-button">
                            <button
                              type="button"
                              onClick={() => open({ moduleId: module.id, environmentId: null, tab: "card" })}
                            >
                              <span className="module-code">
                                {module.code}
                                <span className={`label ${typeClass(module)}`}>{typeLabel(module)}</span>
                              </span>
                              <span className="module-name">{module.name}</span>
                            </button>
                          </td>
                          {environments.map((env, position) => (
                            <Case
                              key={env.id}
                              tint={environmentTint(position)}
                              occupations={occupations(module.id, env.id)}
                              hovered={hoveredColumn === env.id}
                              selected={selection?.moduleId === module.id && selection?.environmentId === env.id}
                              onHover={() => setHoveredColumn(env.id)}
                              open={() => open({ moduleId: module.id, environmentId: env.id, tab: "service" })}
                            />
                          ))}
                        </tr>
                      ))}
                  </Fragment>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

type PropsCase = {
  tint: string; // classe de la teinte de l'environnement (liseré de la colonne)
  occupations: Occupation[];
  hovered: boolean;
  selected: boolean;
  onHover: () => void;
  open: () => void;
};

function Case({ tint, occupations, hovered, selected, onHover, open }: Readonly<PropsCase>) {
  const classes = ["checkbox", tint, hovered && "hovered", selected && "selected"].filter(Boolean).join(" ");
  return (
    <td className={classes} onMouseEnter={onHover}>
      {occupations.length === 0 && <span className="absent">·</span>}
      {/* Une pastille par ligne ; avec plusieurs (ex. le même namespace sur deux clusters), le cluster de chacune. */}
      <div className="checkbox-badges">
        {occupations.map((o) => (
          <div key={o.slot.id} className="checkbox-row">
            {occupations.length > 1 && <span className="checkbox-cluster">{o.cluster.code}</span>}
            <button
              type="button"
              className={`version ${o.current ? versionClass(o.current.version) : "empty"}`}
              title={`${o.slot.release_name} — ${o.namespace.name} (${o.cluster.code})`}
              onClick={open}
            >
              <span className="version-number">{o.current ? o.current.version.number : "empty"}</span>
              {o.current && <span className="version-date">{ago(o.current.date)}</span>}
            </button>
          </div>
        ))}
      </div>
    </td>
  );
}
