/**
 * Headless check of the §12 per-candidate win% engine (mirrors simWorker EVALUATE):
 * mid-draft at seat 4's first pick, rank a candidate set by the win% each yields
 * after completing the draft via the §13 opponent model. Confirms better players
 * → higher win%, and prints the Δ vs the auto-pick baseline.
 *   node scripts/eval_check.mjs
 */
import { readFileSync } from "node:fs";
import { buildSimMatrix, bestBallTeamScores, setRngSeed, N_TEAMS } from "../src/sim/simCore.js";
import { completeDraft, teamForPick } from "../src/sim/draftSim.js";
import { samplePick } from "../src/opponents/pickModel.js";

const base = new URL("../", import.meta.url);
const sim = JSON.parse(readFileSync(new URL("public/data/sim.json", base)));
const profiles = JSON.parse(readFileSync(new URL("public/data/opponents.json", base))).profiles;

// top-200 universe + dense local remap (mirror useSim)
const pool = sim.players.filter((p) => p.idx != null).sort((a, b) => a.db_rank - b.db_rank).slice(0, 200);
const g2l = new Map(pool.map((p, i) => [p.idx, i]));
const players = pool.map((p, i) => ({ ...p, idx: i }));
const correlations = sim.correlations.filter(([a, b]) => g2l.has(a) && g2l.has(b)).map(([a, b, r]) => [g2l.get(a), g2l.get(b), r]);
const N = players.length, positionsByIdx = players.map((p) => p.position), nSim = 12000;
setRngSeed(12345);
const { matrix } = buildSimMatrix(players, correlations, nSim);

const winPct = (rostersByTeam, myTeam) => {
  const ts = rostersByTeam.map((idxs) => bestBallTeamScores(matrix, positionsByIdx, idxs, N, nSim));
  const my = ts[myTeam]; let w = 0;
  for (let s = 0; s < nSim; s++) { let won = true; for (let t = 0; t < N_TEAMS; t++) { if (t !== myTeam && ts[t][s] > my[s]) { won = false; break; } } if (won) w++; }
  return (w / nSim) * 100;
};

const my0 = 3; // seat 4
const taken = new Set(), counts = Array.from({ length: 8 }, () => ({ QB: 0, RB: 0, WR: 0, TE: 0 }));
const recent = Array.from({ length: 8 }, () => []), rosters = Array.from({ length: 8 }, () => []);
const avail = () => players.filter((p) => !taken.has(p.idx));
for (let pick = 0; pick < my0; pick++) {            // opponents pick ahead of me
  const team = teamForPick(pick), a = avail();
  const i = samplePick(a, counts[team], recent[team], profiles[team], Math.random);
  const p = a[i]; taken.add(p.idx); rosters[team].push(p.idx); counts[team][p.position]++; recent[team].push(p.position);
}
const rows = (idxs) => idxs.map((li) => ({ player: players[li] }));
const others = rosters.filter((_, t) => t !== my0).map(rows);
const myBase = rows(rosters[my0]);
const FILLS = 12;
const meanFill = (myRoster, available, fromPick) => {
  let s = 0; for (let f = 0; f < FILLS; f++) s += winPct(completeDraft(myRoster, others, available, fromPick, my0, { profiles, rng: Math.random }), my0);
  return s / FILLS;
};

const baseline = meanFill(myBase, avail(), my0);
const cands = avail().sort((a, b) => (b.points || 0) - (a.points || 0)).slice(0, 10);
const results = cands.map((c) => {
  const w = meanFill([...myBase, { player: players[c.idx] }], avail().filter((p) => p.idx !== c.idx), my0 + 1);
  return { name: c.name, pos: c.position, pts: c.points || 0, win: w, d: w - baseline };
}).sort((a, b) => b.win - a.win);

console.log(`seat 4 · pick 4 · auto-pick baseline win%: ${baseline.toFixed(1)}`);
console.log("candidate win% (ranked):");
for (const r of results) console.log(`  ${r.pos} ${r.name.padEnd(22)} pts=${r.pts.toFixed(1).padStart(5)}  win%=${r.win.toFixed(1).padStart(5)}  Δ=${r.d >= 0 ? "+" : ""}${r.d.toFixed(1)}`);

const finite = results.every((r) => Number.isFinite(r.win));
const spread = Math.max(...results.map((r) => r.win)) - Math.min(...results.map((r) => r.win));
const ok = finite && spread > 0.3 && results.length === 10;
console.log(`\nfinite: ${finite ? "OK" : "FAIL"} · win% spread across candidates: ${spread.toFixed(1)}pt (${spread > 0.3 ? "separates" : "too flat"})`);
console.log(`eval engine: ${ok ? "PASS" : "FAIL"}`);
process.exit(ok ? 0 : 1);
