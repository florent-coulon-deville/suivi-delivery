// « Ce qui tourne » : chiffres clés, tableau modules × environnements, activité récente.
//
// La page est calculée sur le serveur : il lit l'API et fait les rapprochements (lib/state.ts).
// Le navigateur reçoit la page prête, plus la partie interactive (components/view/).
import ApiAlert from "@/components/ApiAlert";
import View from "@/components/view/View";
import Summary from "@/components/view/Summary";
import { ApiError } from "@/lib/api";
import { loadAll } from "@/lib/data";
import { buildState } from "@/lib/state";

export default async function WhatIsRunning() {
  let state;
  try {
    state = buildState(await loadAll());
  } catch (_error) {
    if (_error instanceof ApiError) return <ApiAlert message={_error.message} />;
    throw _error;
  }
  return (
    <>
      <Summary summary={state.summary} />
      <View state={state} />
    </>
  );
}
