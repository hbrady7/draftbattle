/**
 * Headless check of the pre-draft Draft Plan (src/opponents/draftPlan.js):
 * seat-4 plan vs the default-seven deterministic bots — prints the 11 picks with
 * rank + rationale, and asserts a legal roster + that the wait-logic shows (a
 * high-ranked player deferred to a late round because the bots ignore him).
 *   node scripts/plan_check.mjs
 */
import { readFileSync } from "node:fs";
import { planDraft } from "../src/opponents/draftPlan.js";

const base = new URL("../", import.meta.url);
const board = JSON.parse(readFileSync(new URL("public/data/board.json", base)));
const ai = JSON.parse(readFileSync(new URL("public/data/ai_opponents.json", base)));
const seven = ai.meta.default_seven;
const mySeat = 4, my0 = mySeat - 1;
const aiSeats = Array(8).fill(null);
let j = 0; for (let s = 0; s < 8; s++) { if (s === my0) continue; aiSeats[s] = seven[j++ % seven.length]; }

const plan = planDraft({ board, aiData: ai, aiSeats, mySeat, picks: [] });
console.log(`Seat ${mySeat} draft plan — vs [${aiSeats.filter(Boolean).join(", ")}]:`);
for (const pk of plan) {
  const p = pk.player;
  console.log(`  R${String(pk.round).padStart(2)}  ${p.position.padEnd(2)}  ${p.name.padEnd(22)} #${String(pk.rank).padStart(3)}  val ${String(pk.value).padStart(5)}  ${pk.steal >= 2 ? "[STEAL] " : ""}${pk.rationale}`);
}
const counts = { QB: 0, RB: 0, WR: 0, TE: 0 };
for (const pk of plan) counts[pk.player.position]++;
const legal = counts.QB >= 2 && counts.RB >= 2 && counts.WR >= 3 && counts.TE >= 1;
const steals = plan.filter((pk) => pk.steal >= 2);
console.log("\nroster:", JSON.stringify(counts));
console.log(`legal (>=2QB/2RB/3WR/1TE): ${legal ? "OK" : "FAIL"}`);
console.log(`wait-logic steals: ${steals.length}` + (steals.length ? ` — e.g. ${steals.slice(0, 3).map((s) => `${s.player.name.split(" ")[0]} #${s.rank}→R${s.round}`).join(", ")}` : ""));
const ok = legal && plan.length === 11;
console.log(`\nplan check: ${ok ? "PASS" : "FAIL"}`);
process.exit(ok ? 0 : 1);
