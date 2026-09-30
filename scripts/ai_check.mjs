/**
 * Check the data-driven AI opponent model (public/data/ai_opponents.json):
 *  1. board↔AI name_key join rate
 *  2. each default-seven AI's round-1 top predicted position == its empirical modal R1 position
 *  3. per-candidate win% / P(available) under the real AI models are finite + separated,
 *     and the baseline win% is in a sane (non-broken) range.
 *   node scripts/ai_check.mjs
 */
import { readFileSync } from "node:fs";
import { nameKey, aiByName, pickProbabilities, topPredicted } from "../src/opponents/aiModel.js";
import { buildSimMatrix, bestBallTeamScores, setRngSeed, N_TEAMS } from "../src/sim/simCore.js";
import { completeDraft, teamForPick } from "../src/sim/draftSim.js";

const base = new URL("../", import.meta.url);
const ai = JSON.parse(readFileSync(new URL("public/data/ai_opponents.json", base)));
const board = JSON.parse(readFileSync(new URL("public/data/board.json", base)));
const sim = JSON.parse(readFileSync(new URL("public/data/sim.json", base)));

const pool = board.filter((p) => p.db_rank != null).sort((a, b) => a.db_rank - b.db_rank).slice(0, 200)
  .map((p, i) => ({ idx: i, id: p.id, name: p.name, nk: nameKey(p.name), position: p.position,
                    points: p.mean, sd_pts: p.sd, min: p.min, max: p.max, knots: p.knots, db_rank: p.db_rank }));

// 1. join rate
const known = new Set(Object.keys(ai.adp));
for (const a of ai.ais) for (const k of Object.keys(a.priors)) known.add(k);
const joined = pool.filter((p) => known.has(p.nk)).length;
const joinRate = joined / pool.length;
console.log(`1. name_key join rate (board top-${pool.length} ↔ AI data): ${(joinRate * 100).toFixed(1)}% (${joined}/${pool.length})`);

// 2. archetype / modal-R1 match for default seven
const map = aiByName(ai);
let archOk = 0;
console.log("2. default-seven round-1 top predicted position vs empirical modal R1:");
for (const name of ai.meta.default_seven) {
  const a = map[name];
  const pr = pickProbabilities(pool, a, 1, { adp: ai.adp });
  const top = pool[pr.indexOf(Math.max(...pr))];
  const r1 = a.pos_by_round["1"] || {};
  const modal = Object.keys(r1).reduce((b, k) => (r1[k] > (r1[b] ?? -1) ? k : b), "QB");
  const ok = top.position === modal;
  archOk += ok ? 1 : 0;
  console.log(`   ${name.padEnd(12)} pred top: ${top.position} (${top.name.split(" ").slice(-1)[0]})  modal R1: ${modal}  ${ok ? "✓" : "✗"}  [${a.archetype}]`);
}

// 3. win% separation under the real AI models (seat 4 first pick)
const corr = sim.correlations
  .filter(([a, b]) => a < pool.length && b < pool.length);
const N = pool.length, posBy = pool.map((p) => p.position), nSim = 8000;
setRngSeed(12345);
const { matrix } = buildSimMatrix(pool, corr, nSim);
const winPct = (rosters, my) => {
  const ts = rosters.map((idxs) => bestBallTeamScores(matrix, posBy, idxs, N, nSim));
  const m = ts[my]; let w = 0;
  for (let s = 0; s < nSim; s++) { let won = true; for (let t = 0; t < N_TEAMS; t++) if (t !== my && ts[t][s] > m[s]) { won = false; break; } if (won) w++; }
  return (w / nSim) * 100;
};
const my0 = 3;
const seven = ai.meta.default_seven;
const aiBySeat = Array(N_TEAMS).fill(null);
{ let j = 0; for (let s = 0; s < N_TEAMS; s++) { if (s === my0) continue; aiBySeat[s] = map[seven[j % seven.length]]; j++; } }
// opponents pick 0..2
const taken = new Set(), rosters = Array.from({ length: 8 }, () => []);
const avail = () => pool.filter((p) => !taken.has(p.idx));
for (let pk = 0; pk < my0; pk++) {
  const team = teamForPick(pk), a = avail();
  const pr = pickProbabilities(a, aiBySeat[team], Math.floor(pk / 8) + 1, { adp: ai.adp });
  const pick = a[pr.indexOf(Math.max(...pr))];
  taken.add(pick.idx); rosters[team].push(pick.idx);
}
const rows = (idxs) => idxs.map((li) => ({ player: pool[li] }));
const others = rosters.filter((_, t) => t !== my0).map(rows);
const meanFill = (myRoster, available, fromPick) => {
  let s = 0; for (let f = 0; f < 12; f++) s += winPct(completeDraft(myRoster, others, available, fromPick, my0, { aiBySeat, adp: ai.adp, rng: Math.random }), my0);
  return s / 12;
};
const baseline = meanFill(rows(rosters[my0]), avail(), my0);
const cands = avail().sort((a, b) => (b.points || 0) - (a.points || 0)).slice(0, 8);
const res = cands.map((c) => {
  const w = meanFill([...rows(rosters[my0]), { player: pool[c.idx] }], avail().filter((p) => p.idx !== c.idx), my0 + 1);
  return { name: c.name, pos: c.position, win: w, d: w - baseline };
}).sort((a, b) => b.win - a.win);
console.log(`3. win% under real AI models — baseline (auto-pick) ${baseline.toFixed(1)}%:`);
for (const r of res) console.log(`   ${r.pos} ${r.name.padEnd(22)} win%=${r.win.toFixed(1).padStart(5)}  Δ=${r.d >= 0 ? "+" : ""}${r.d.toFixed(1)}`);
const spread = Math.max(...res.map((r) => r.win)) - Math.min(...res.map((r) => r.win));
const finite = res.every((r) => Number.isFinite(r.win)) && Number.isFinite(baseline);

// baseline < 95 distinguishes legitimate (exploitable-archetype) win% from the old
// broken "opponents draft randomly → every stud falls to me → ~97%" regression.
const pass = joinRate >= 0.5 && archOk >= 5 && finite && spread > 0.3 && baseline < 95;
console.log(`\njoin≥50%: ${joinRate >= 0.5 ? "OK" : "FAIL"} · archetype-match ${archOk}/7 (≥5): ${archOk >= 5 ? "OK" : "FAIL"} · win% finite+separated (${spread.toFixed(1)}pt): ${finite && spread > 0.3 ? "OK" : "FAIL"} · baseline not-broken (<95): ${baseline < 95 ? "OK" : "FAIL"}`);
console.log(`NOTE: ${baseline.toFixed(0)}% baseline is optimistic — greedy auto-fill vs rigid/suboptimal real AIs. The per-candidate ranking + Δ (WPA) and the floor are the grounded signals.`);
console.log(`AI opponent model: ${pass ? "PASS" : "FAIL"}`);
process.exit(pass ? 0 : 1);
