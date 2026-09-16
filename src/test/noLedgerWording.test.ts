/**
 * PropShare is a NON-blockchain platform: ownership is evidenced by the central ownership
 * ledger, SPV documents and certificates. No investor-facing property page may describe units
 * as tokens or mention blockchain / smart contracts / on-chain settlement.
 * (The audit found "on-chain", "tokenized units" and a whole "Educational Demo" page doing so.)
 */
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join } from "node:path";
import { describe, it, expect } from "vitest";

const FORBIDDEN = /on-chain|tokeni[sz]ed|tokenization|blockchain|smart[- ]contract/i;
const ROOTS = ["src/pages", "src/components/property", "src/components/marketplace"];
// documentCategories.ts carries the legacy "audit" category label — handled in Step 3.
const ALLOW = new Set<string>([]);

function walk(dir: string, out: string[] = []): string[] {
  for (const name of readdirSync(dir)) {
    const p = join(dir, name);
    if (statSync(p).isDirectory()) walk(p, out);
    else if (/\.tsx?$/.test(name) && !/\.test\.tsx?$/.test(name)) out.push(p);
  }
  return out;
}

describe("investor-facing pages use ownership-ledger wording", () => {
  it("contain no token / blockchain / smart-contract / on-chain wording", () => {
    const offenders: string[] = [];
    for (const root of ROOTS) {
      for (const file of walk(root)) {
        if (ALLOW.has(file.replace(/\\/g, "/"))) continue;
        const src = readFileSync(file, "utf8");
        // "Pronova Token" is a payment-rail brand name, not ownership wording.
        const cleaned = src.replace(/Pronova Token/g, "");
        const m = cleaned.match(FORBIDDEN);
        if (m) offenders.push(`${file}: "${m[0]}"`);
      }
    }
    expect(offenders).toEqual([]);
  });
});
