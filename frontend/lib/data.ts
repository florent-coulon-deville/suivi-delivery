// Chargement des données, côté serveur.
//
// Les écrans ont besoin de presque tout : on charge chaque liste une fois, en parallèle,
// puis on fait les rapprochements (voir etat.ts).
import { read } from "./api";
import { type Data, type Enumerations, RESOURCES } from "./types";

/** Charge toutes les listes. Renvoie { environnements: [...], clusters: [...], ... }. */
export async function loadAll(): Promise<Data> {
  const lists = await Promise.all(RESOURCES.map((resource) => read<unknown[]>(resource)));
  return Object.fromEntries(RESOURCES.map((resource, i) => [resource, lists[i]])) as Data;
}

/** Valeurs des listes fermées (types de module, de version…), données par l'API. */
export function loadEnumerations(): Promise<Enumerations> {
  return read<Enumerations>("enumerations");
}
