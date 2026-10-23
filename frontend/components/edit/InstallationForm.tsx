// Enregistrement guidé d'une installation, étape par étape.
//
//   1. l'environnement   2. le namespace (de cet environnement)   3. l'emplacement (de ce namespace)
//   4. la version (du module réservé à l'emplacement)   5. les paramètres (affectés au namespace)
//
// À chaque étape, seuls les choix cohérents avec les précédentes sont proposés. L'API fait
// ensuite les contrôles d'ensemble (compatibilités, pas de snapshot en prod…) et répond par
// un message clair si quelque chose ne va pas.
import { type FormEvent, type ReactNode, useState } from "react";

import { save } from "@/app/edit/actions";
import FilterableList from "@/components/FilterableList";
import type { Resource, ParameterType } from "@/lib/types";
import { compareVersions } from "@/lib/versions";

import { type Context, type Element, label } from "./resources";

/** Date et heure locales au format attendu par <input type="datetime-local"> : 2026-10-09T14:30. */
function localNow(): string {
  const d = new Date();
  d.setMinutes(d.getMinutes() - d.getTimezoneOffset());
  return d.toISOString().slice(0, 16);
}

function Step({ number, title, children, inactive }: Readonly<{ number: string; title: string; children: ReactNode; inactive?: boolean }>) {
  return (
    <div className={`step ${inactive ? "inactive" : ""}`}>
      <div className="step-number">{number}</div>
      <div className="step-content">
        <div className="step-title">{title}</div>
        {children}
      </div>
    </div>
  );
}

type Choice = "environment" | "namespace" | "slot" | "version" | "technical" | "application";

// Changer une étape vide les choix qui en dépendent, devenus peut-être incohérents.
const DEPENDS_ON: Partial<Record<Choice, Choice[]>> = {
  environment: ["namespace", "slot", "version", "technical", "application"],
  namespace: ["slot", "version", "technical", "application"],
  slot: ["version"],
};

type Props = { ctx: Context; afterSave: () => void; cancel: () => void };

export default function InstallationForm({ ctx, afterSave, cancel }: Readonly<Props>) {
  const { d } = ctx;
  const [v, setV] = useState<Record<Choice, string>>({
    environment: "",
    namespace: "",
    slot: "",
    version: "",
    technical: "",
    application: "",
  });
  const [date, setDate] = useState(localNow);
  const [error, setError] = useState<string | null>(null);
  const [sending, setSending] = useState(false);

  const choose = (name: Choice, value: string) => {
    const empty = Object.fromEntries((DEPENDS_ON[name] ?? []).map((n) => [n, ""]));
    setV((x) => ({ ...x, ...empty, [name]: value }));
  };

  const namespaces = d.namespaces.filter((n) => n.environment_id === Number(v.environment));
  const slots = d.slots.filter((e) => e.namespace_id === Number(v.namespace));
  const slot = d.slots.find((e) => e.id === Number(v.slot));
  const versions = slot
    ? d["module-versions"]
        .filter((x) => x.module_id === slot.module_id)
        .sort((a, b) => compareVersions(b.number, a.number))
    : [];
  // Paramètres du module de l'emplacement, du bon type, affectés à son namespace (règles vérifiées aussi par l'API).
  const possibleParameters = (type: ParameterType) =>
    d.parameters.filter(
      (p) => p.type === type && p.module_id === slot?.module_id && p.namespace_ids.includes(Number(v.namespace)),
    );
  const current = slot
    ? d.installations.filter((i) => i.slot_id === slot.id).sort((a, b) => (a.date < b.date ? 1 : -1))[0]
    : undefined;

  const validate = async (e: FormEvent) => {
    e.preventDefault();
    setSending(true);
    setError(null);
    const result = await save("installations", null, {
      slot_id: Number(v.slot),
      module_version_id: Number(v.version),
      technical_parameter_id: Number(v.technical),
      application_parameter_id: Number(v.application),
      date: new Date(date).toISOString(),
    });
    setSending(false);
    if (result.ok) afterSave();
    else setError(result.message);
  };

  const text = (resource: Resource, x: Element): string => {
    if (resource === "slots") return `${x.release_name} (module ${ctx.byId("modules", x.module_id)?.code})`;
    if (resource === "module-versions") return `${x.number} (${String(x.type).toLowerCase()})`;
    return label(resource, x, ctx);
  };

  const list = (name: Choice, title: string, elements: Element[], resource: Resource, empty: string) => (
    <FilterableList
      ariaLabel={title}
      value={v[name]}
      required
      disabled={elements.length === 0}
      prompt={elements.length ? "— choisir —" : empty}
      change={(value) => choose(name, value)}
      options={elements.map((x) => ({ value: String(x.id), text: text(resource, x) }))}
    />
  );

  return (
    <form className="form" onSubmit={validate}>
      {error && (
        <div className="form-alert" role="alert">
          <strong>Refusé :</strong> {error}
        </div>
      )}
      <Step number="1" title="Environnement">
        {list("environment", "Environnement", d.environments, "environments", "aucun environnement")}
      </Step>
      <Step number="2" title="Namespace" inactive={!v.environment}>
        {list("namespace", "Namespace", namespaces, "namespaces", "aucun namespace dans cet environnement")}
      </Step>
      <Step number="3" title="Emplacement" inactive={!v.namespace}>
        {list("slot", "Emplacement", slots, "slots", "aucun emplacement dans ce namespace")}
        {slot && (
          <div className="field-help">
            Tourne actuellement :{" "}
            {current ? (
              <strong>{ctx.byId("module-versions", current.module_version_id)?.number as string}</strong>
            ) : (
              "rien (emplacement vide)"
            )}
          </div>
        )}
      </Step>
      <Step number="4" title="Version à installer" inactive={!v.slot}>
        {list("version", "Version à installer", versions, "module-versions", "aucune version pour ce module")}
      </Step>
      <Step number="5" title="Paramètres" inactive={!v.version}>
        <div className="two-columns">
          <div>
            <div className="sub-label">Technique</div>
            {list(
              "technical",
              "Paramètre technique",
              possibleParameters("TECHNICAL"),
              "parameters",
              "aucun paramètre technique",
            )}
          </div>
          <div>
            <div className="sub-label">Applicatif</div>
            {list(
              "application",
              "Paramètre applicatif",
              possibleParameters("APPLICATION"),
              "parameters",
              "aucun paramètre applicatif",
            )}
          </div>
        </div>
      </Step>
      <Step number="6" title="Date de l'installation" inactive={!v.version}>
        <input
          aria-label="Date de l'installation"
          type="datetime-local"
          value={date}
          required
          onChange={(e) => setDate(e.target.value)}
        />
      </Step>
      <div className="form-actions">
        <button type="button" className="button-secondary" onClick={cancel}>
          Annuler
        </button>
        <button type="submit" className="button-primary" disabled={sending || !v.application || !v.technical}>
          {sending ? "Enregistrement…" : "Enregistrer l'installation"}
        </button>
      </div>
    </form>
  );
}
