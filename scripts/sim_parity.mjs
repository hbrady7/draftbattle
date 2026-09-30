/**
 * Phase 3 parity driver (BRIEF §12): runs the SAME JS sim the browser Web Worker
 * uses (simCore.js) on the synthetic draft scored by scripts/sim.py, and compares
 * my win% (target: within 1 pt) and times a full 8x11 evaluation (target < 300ms).
 *
 *   node scripts/sim_parity.mjs
 */
import { readFileSync } from "node:fs";
import { performance } from "node:perf_hooks";
import {
  buildSimMatrix, bestBallTeamScores, setRngSeed, N_TEAMS,
} from "../src/sim/simCore.js";

const base = new URL("../", import.meta.url);
const sim = JSON.parse(readFileSync(new URL("public/data/sim.json", base)));
const draft = JSON.parse(readFileSync(new URL("build/_parity_draft.json", base)));
const { rosters, my_team, seed, python_win_pct } = draft;

// Subset to the rostered players; remap to a dense 0..N-1 index space.
const used = [...new Set(rosters.flat())].sort((a, b) => a - b);
const remap = new Map(used.map((g, i) => [g, i]));
const players = used.map((g, i) => ({ ...sim.players[g], idx: i }));
const correlations = sim.correlations
  .filter(([i, j]) => remap.has(i) && remap.has(j))
  .map(([i, j, r]) => [remap.get(i), remap.get(j), r]);
const N = players.length;
const positionsByIdx = players.map((p) => p.position);
const rosterIdxs = rosters.map((r) => r.map((g) => remap.get(g)));

const N_SIM = 20000; // §12 browser draws
setRngSeed(seed);

// Step 1-3 (§12): draw the correlated sample matrix — ONCE per session.
const tBuild = performance.now();
const { matrix, shrink } = buildSimMatrix(players, correlations, N_SIM);
const buildMs = performance.now() - tBuild;

// Step 4-5: a full 8x11 evaluation against the pre-built matrix — runs every pick.
const tEval = performance.now();
const teamScores = rosterIdxs.map((idxs) =>
  bestBallTeamScores(matrix, positionsByIdx, idxs, N, N_SIM));
let wins = 0;
const my = teamScores[my_team];
for (let s = 0; s < N_SIM; s++) {
  let won = true;
  for (let t = 0; t < N_TEAMS; t++) {
    if (t !== my_team && teamScores[t][s] > my[s]) { won = false; break; }
  }
  if (won) wins++;
}
const winPct = (wins / N_SIM) * 100;
const evalMs = performance.now() - tEval;

const diff = Math.abs(winPct - python_win_pct);
console.log(`JS sim:     my win%=${winPct.toFixed(2)}  (n_sim=${N_SIM}, shrink=${shrink.toFixed(3)})`);
console.log(`Python sim: my win%=${python_win_pct.toFixed(2)}  (n_sim=100000)`);
console.log(`parity |diff|=${diff.toFixed(2)}pt  ${diff < 1 ? "OK (<1pt)" : "FAIL"}`);
console.log(`sample matrix build (once/session): ${buildMs.toFixed(0)}ms`);
console.log(`full 8x11 evaluation (per pick):     ${evalMs.toFixed(0)}ms  ${evalMs < 300 ? "OK (<300ms)" : "SLOW (>300ms)"}`);
process.exit(diff < 1 && evalMs < 300 ? 0 : 1);
