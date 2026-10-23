"use client";
// Partie interactive de « Ce qui tourne » : le tableau (filtres, repli), l'activité récente
// et le panneau de détail. Elle reçoit l'état déjà calculé par le serveur (lib/state.ts).
import { useState } from "react";

import type { State } from "@/lib/state";

import Activity from "./Activity";
import Panel from "./Panel";
import type { Selection } from "./selection";
import Overview from "./Overview";

export default function View({ state }: Readonly<{ state: State }>) {
  // Panneau de détail : null = fermé.
  const [selection, setSelection] = useState<Selection | null>(null);

  return (
    <>
      <Overview state={state} selection={selection} open={setSelection} />
      <Activity activity={state.activity} open={setSelection} />
      {selection && (
        <Panel state={state} selection={selection} change={setSelection} close={() => setSelection(null)} />
      )}
    </>
  );
}
