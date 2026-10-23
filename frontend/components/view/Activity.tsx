// Activité récente : les dernières installations, dans une zone repliable sous le tableau.
import type { ActivityRow } from "@/lib/state";
import { versionClass, formatDate, ago } from "@/lib/format";

import type { Selection } from "./selection";

type Props = { activity: ActivityRow[]; open: (selection: Selection) => void };

export default function Activity({ activity, open }: Readonly<Props>) {
  if (activity.length === 0) return null;
  return (
    <details className="main-card activity">
      <summary>
        <h2>Activité récente</h2>
        <span className="subtitle">les {activity.length} dernières installations</span>
      </summary>
      <ul className="activity-list">
        {activity.map((i) => (
          <li key={i.id}>
            <button
              type="button"
              onClick={() => open({ moduleId: i.module.id, environmentId: i.environment.id, tab: "history" })}
            >
              <span className="activity-date" title={formatDate(i.date)}>
                {ago(i.date)}
              </span>
              <span className="activity-module">{i.module.code}</span>
              <span className="activity-version">
                <span className={`version ${versionClass(i.version)}`}>
                  <span className="version-number">{i.version.number}</span>
                </span>
              </span>
              <span className="activity-arrow">→</span>
              <span className={`bullet ${i.environment.is_prod ? "bullet-prod" : ""}`}>{i.environment.code}</span>
              <code className="subtle">{i.slot.release_name}</code>
            </button>
          </li>
        ))}
      </ul>
    </details>
  );
}
