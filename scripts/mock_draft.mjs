/**
 * Phase 5 headless check (BRIEF §17 Phase 5): a scripted seat-4 mock draft that
 * updates my win% after every one of my picks and exports a valid results JSON.
 *
 *   node scripts/mock_draft.mjs
 *
 * Opponents pick via the §13 pickModel (seeded); my seat takes best-available by
 * projected points. After each of my picks we score the CURRENT partial rosters
 * with simCore (buildSimMatrix over the drafted-player union + best-ball totals,
 * win = my >= max of 8). Prints the per-pick win% and PASS/FAIL.
 */
import { readFileSync, writeFileSync, mkdirSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import { buildSimMatrix, bestBallTeamScores, setRngSeed, N_TEAMS } from "../src/sim/simCore.js";
import { samplePick, defaultProfiles } from "../src/opponents/pickModel.js";

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..");
const readJson = (p) => JSON.parse(readFileSync(join(ROOT, p)));

const sim = readJson("public/data/sim.json");
const board = readJson("public/data/board.json");
const opp = readJson("public/data/opponents.json");

// Join db_rank onto the sim players by id (sim order == board order, but join to be safe).
const rankById = new Map(board.map((p) => [p.id, p.db_rank]));
const players = sim.players.map((p) => ({ ...p, db_rank: rankById.get(p.id) ?? 999 }));
const N_ROUNDS = sim.meta.n_rounds ?? 11;
const SEED = sim.meta.seed ?? 12345;

// Deterministic mulberry32 for the draft (separate from the sim's own PRNG).
function mulberry32(a) {
  return function () {
    a |= 0; a = (a + 0x6D2B79F5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}
const draftRng = mulberry32(SEED);

const MY_SEAT = 3; // 0-based seat 4
const profiles = opp.profiles;
const teamForPick = (pi) => {
  const round = Math.floor(pi / N_TEAMS);
  const pos = pi % N_TEAMS;
  return round % 2 === 0 ? pos : N_TEAMS - 1 - pos;
};

// Draft state
const pool = players.slice().sort((a, b) => a.db_rank - b.db_rank); // draftable order
const taken = new Set();
const rosters = Array.from({ length: N_TEAMS }, () => []);
const counts = Array.from({ length: N_TEAMS }, () => ({ QB: 0, RB: 0, WR: 0, TE: 0 }));
const recent = Array.from({ length: N_TEAMS }, () => []);
const predictions = [];

function scoreCurrentWinPct() {
  // Score the current partial rosters (union of drafted players) with a small sim.
  const used = [...new Set(rosters.flat().map((p) => p.idx))].sort((a, b) => a - b);
  if (rosters[MY_SEAT].length === 0) return 0;
  const remap = new Map(used.map((g, i) => [g, i]));
  const subPlayers = used.map((g, i) => ({ ...players.find((p) => p.idx === g), idx: i }));
  const correlations = sim.correlations
    .filter(([i, j]) => remap.has(i) && remap.has(j))
    .map(([i, j, r]) => [remap.get(i), remap.get(j), r]);
  setRngSeed(SEED);
  const N = subPlayers.length;
  const { matrix } = buildSimMatrix(subPlayers, correlations, 8000);
  const positionsByIdx = subPlayers.map((p) => p.position);
  const teamScores = rosters.map((r) =>
    bestBallTeamScores(matrix, positionsByIdx, r.map((p) => remap.get(p.idx)), N, 8000));
  let wins = 0;
  const my = teamScores[MY_SEAT];
  for (let s = 0; s < 8000; s++) {
    let won = true;
    for (let t = 0; t < N_TEAMS; t++) {
      if (t !== MY_SEAT && teamScores[t][s] > my[s]) { won = false; break; }
    }
    if (won) wins++;
  }
  return (wins / 8000) * 100;
}

const winSeq = [];
const totalPicks = N_TEAMS * N_ROUNDS;
for (let pi = 0; pi < totalPicks; pi++) {
  const team = teamForPick(pi);
  const avail = pool.filter((p) => !taken.has(p.idx));
  if (!avail.length) break;
  let choice;
  if (team === MY_SEAT) {
    choice = avail[0]; // best available by DB order ~ points; simple greedy
    // prefer positions we still need to keep the roster legal
    const need = ["QB", "RB", "WR", "TE"].find(
      (ps) => counts[team][ps] < { QB: 2, RB: 2, WR: 3, TE: 1 }[ps]
        && avail.some((p) => p.position === ps));
    if (need) choice = avail.find((p) => p.position === need) ?? avail[0];
  } else {
    const k = samplePick(avail, counts[team], recent[team], profiles[team], draftRng);
    choice = avail[k];
    predictions.push({ pick: pi + 1, team, player: choice.name, position: choice.position });
  }
  taken.add(choice.idx);
  rosters[team].push(choice);
  counts[team][choice.position]++;
  recent[team].push(choice.position);
  if (team === MY_SEAT) {
    const w = scoreCurrentWinPct();
    winSeq.push(w);
    console.log(`  my pick ${winSeq.length.toString().padStart(2)} (overall ${pi + 1}): `
      + `${choice.name} (${choice.position}) → win% ${w.toFixed(2)}`);
  }
}

// Export a valid results JSON (skeleton shape + predictions log)
const out = {
  meta: { seed: SEED, my_seat: MY_SEAT + 1, week: 4, n_teams: N_TEAMS, n_rounds: N_ROUNDS },
  teams: rosters.map((r, t) => ({
    seat: t + 1, is_me: t === MY_SEAT,
    players: r.map((p) => ({ id: p.id, name: p.name, position: p.position, team: p.team })),
  })),
  predictions,
};
mkdirSync(join(ROOT, "results"), { recursive: true });
const outPath = join(ROOT, "results", "mock_draft_seat4.json");
writeFileSync(outPath, JSON.stringify(out, null, 1));

// Validate: re-parse, 11 picks, win% finite and changing.
const reparsed = JSON.parse(readFileSync(outPath));
const okCount = winSeq.length === N_ROUNDS;
const okFinite = winSeq.every((w) => Number.isFinite(w));
const okChanging = new Set(winSeq.map((w) => w.toFixed(1))).size > 1;
const okJson = reparsed.teams.length === N_TEAMS
  && reparsed.teams[MY_SEAT].players.length === N_ROUNDS
  && Array.isArray(reparsed.predictions);

console.log(`\n  picks tracked: ${winSeq.length}/${N_ROUNDS}  ${okCount ? "OK" : "FAIL"}`);
console.log(`  win% finite:   ${okFinite ? "OK" : "FAIL"}`);
console.log(`  win% updates:  ${okChanging ? "OK" : "FAIL"} (range ${Math.min(...winSeq).toFixed(1)}–${Math.max(...winSeq).toFixed(1)})`);
console.log(`  JSON export:   ${okJson ? "OK" : "FAIL"} → results/mock_draft_seat4.json`);
const pass = okCount && okFinite && okChanging && okJson;
console.log(`\nPhase 5 mock draft: ${pass ? "PASS" : "FAIL"}`);
process.exit(pass ? 0 : 1);
