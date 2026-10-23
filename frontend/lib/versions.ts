// Numéros de version et conditions de compatibilité (même logique que backend/app/versions.py).
import type { Compatibility } from "./types";

/** Transforme un numéro de version en valeur comparable : 1.4 < 1.10 < 2.0, 2.3.0-SNAPSHOT < 2.3.0. */
function key(number: string): { numbers: number[]; suffix: string } {
  const [main = "", ...rest] = number.split("-");
  const numbers = main.split(".").map(Number);
  while (numbers.length > 1 && numbers.at(-1) === 0) numbers.pop();
  return { numbers, suffix: rest.join("-") };
}

/** Compare deux numéros de version : négatif si a < b, 0 si égaux, positif si a > b. */
export function compareVersions(a: string, b: string): number {
  const ca = key(a);
  const cb = key(b);
  for (let i = 0; i < Math.max(ca.numbers.length, cb.numbers.length); i++) {
    const gap = (ca.numbers[i] ?? -1) - (cb.numbers[i] ?? -1);
    if (gap !== 0) return gap;
  }
  if (ca.suffix === cb.suffix) return 0;
  if (!ca.suffix) return 1; // sans suffixe (release) après avec suffixe (snapshot)
  if (!cb.suffix) return -1;
  return ca.suffix < cb.suffix ? -1 : 1;
}

/** La condition d'une compatibilité, en français court. */
export function describeCondition(c: Compatibility): string {
  if (c.condition === "EXACT") return `= ${c.version}`;
  if (c.condition === "AT_LEAST") return `≥ ${c.version}`;
  return `${c.version} → ${c.version_max}`;
}
