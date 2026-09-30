/**
 * Bot logic used inside the Monte Carlo: how the other seven managers (and
 * my own later picks) finish out their rosters.
 *
 * Opponent picks now sample the §13 opponent model (src/opponents/pickModel.js)
 * when `opts.profiles` is supplied; otherwise they fall back to the legacy
 * botSamplePick heuristic (kept for compatibility).
 */

import { samplePick, defaultProfiles } from "../opponents/pickModel.js";

export const N_TEAMS = 8;
export const N_ROUNDS = 11;

export function teamForPick(pickIndex, nTeams = N_TEAMS) {
  const round = Math.floor(pickIndex / nTeams);
  const pos = pickIndex % nTeams;
  return round % 2 === 0 ? pos : nTeams - 1 - pos;
}

export function botNeedMul(posCounts, pos) {
  const c = posCounts;
  // Superflex: a second QB is a starter, not a backup.
  if (pos === "QB") return c.QB < 1 ? 2.8 : c.QB < 2 ? 2.3 : 0.5;
  if (pos === "RB") return c.RB < 2 ? 2.3 : c.RB < 4 ? 1.3 : 0.5;
  if (pos === "WR") return c.WR < 3 ? 2.3 : c.WR < 5 ? 1.3 : 0.5;
  if (pos === "TE") return c.TE < 1 ? 2.3 : c.TE < 2 ? 0.5 : 0.3;
  return 0.5;
}

export function upsideVor(p) {
  return p.p10_vor ?? p.ceiling_vor ?? p.p10 ?? p.ceiling ?? p.points ?? 0;
}

export function botPickScore(p, posCounts) {
  const rank = p.ranking ?? 999;
  const need = botNeedMul(posCounts, p.position);
  return (1000 / (rank + 2)) * need;
}

/**
 * User's future picks: VOR-weighted by need, with P10 VOR blending in over rounds.
 *
 * Round 0 (first overall pick): pure points_vor × need — maximize expected value.
 * Round 10 (last pick): equal weight on points_vor and p10_vor — maximize upside
 * for bench/late-round spots where ceiling matters most.
 *
 * alpha = round / (N_ROUNDS - 1), clamped to [0, 1].
 * score = (points_vor + alpha × p10_vor) × need
 */
export function userPickScore(p, posCounts, round = 0) {
  const vor    = p.points_vor ?? p.points ?? p.mean ?? 0;
  const p10vor = p.p10_vor ?? p.ceiling_vor ?? p.p95 ?? vor;
  const need   = botNeedMul(posCounts, p.position);
  const alpha  = Math.min(1, Math.max(0, round / (N_ROUNDS - 1)));
  return (vor + alpha * p10vor) * need;
}

/**
 * Fraction of the top score below which a player is excluded from the sample
 * pool.  0.15 means only players scoring ≥ 85 % of the leader are considered.
 * A dominant leader (e.g. score 200 vs 80 for everyone else) collapses the pool
 * to size 1 — effectively deterministic.  Clustered scores widen it naturally.
 */
const BOT_TEMP = 0.15;
const BOT_WIN_MIN = 2;
const BOT_WIN_MAX = 5;

/**
 * Sample one bot pick using a temperature window + score² weighting.
 */
function botSamplePick(pool, posCounts) {
  if (!pool.length) return null;

  // Pass 1: score everyone, track maximum.
  const scores = new Array(pool.length);
  let sMax = -Infinity;
  for (let k = 0; k < pool.length; k++) {
    const s = botPickScore(pool[k], posCounts);
    scores[k] = s;
    if (s > sMax) sMax = s;
  }
  if (sMax <= 0) return { p: pool[0], k: 0 }; // all scores ≤ 0, take first

  // Pass 2: collect temperature window.
  const threshold = sMax * (1 - BOT_TEMP);
  const window = [];
  for (let k = 0; k < pool.length; k++) {
    if (scores[k] >= threshold) window.push({ s: scores[k], p: pool[k], k });
  }

  // Clamp to [BOT_WIN_MIN, BOT_WIN_MAX].
  // Sort descending so we always keep the best players when truncating.
  if (window.length > 1) window.sort((a, b) => b.s - a.s);
  if (window.length > BOT_WIN_MAX) window.length = BOT_WIN_MAX;
  if (window.length < BOT_WIN_MIN) {
    // Add the next best players outside the temperature window until min is met.
    const outside = [];
    for (let k = 0; k < pool.length; k++) {
      if (scores[k] < threshold) outside.push({ s: scores[k], p: pool[k], k });
    }
    outside.sort((a, b) => b.s - a.s);
    for (const x of outside) {
      window.push(x);
      if (window.length >= BOT_WIN_MIN) break;
    }
  }

  if (window.length === 1) return window[0];

  // Weighted sample: probability ∝ score²
  let total = 0;
  for (const x of window) total += x.s * x.s;
  let r = Math.random() * total;
  for (const x of window) {
    r -= x.s * x.s;
    if (r <= 0) return x;
  }
  return window[window.length - 1]; // floating-point safety
}

/**
 * Finish every remaining pick of the snake. Returns 8 arrays of player .idx.
 *
 * opts.profiles : per-seat §13 opponent profiles (from opponents.json). When
 *                 present, opponents sample via pickModel.samplePick.
 * opts.rng      : () => [0,1) PRNG for reproducible fills (default Math.random).
 * Each roster row is expected to carry a `player` with `idx`, `position`,
 * `db_rank`, and `points`/`mean`.
 */
export function completeDraft(myRoster, otherRosters, available, pickIndex, myTeamIdx, opts = {}) {
  const profiles = opts.profiles ?? null;
  const rng = opts.rng ?? Math.random;

  const rosterIdxs = Array.from({ length: N_TEAMS }, () => []);
  const allCurrent = Array.from({ length: N_TEAMS }, (_, t) => {
    if (t === myTeamIdx) return myRoster;
    const oi = t < myTeamIdx ? t : t - 1;
    return otherRosters[oi] ?? [];
  });
  for (let t = 0; t < N_TEAMS; t++) {
    for (const row of allCurrent[t]) {
      if (row.player != null) rosterIdxs[t].push(row.player.idx);
    }
  }

  const slotsLeft = rosterIdxs.map((r) => N_ROUNDS - r.length);
  const posCounts = allCurrent.map((r) => {
    const c = { QB: 0, RB: 0, WR: 0, TE: 0 };
    for (const row of r) if (row.player) c[row.player.position] = (c[row.player.position] || 0) + 1;
    return c;
  });
  const recent = allCurrent.map((r) => r.filter((row) => row.player).map((row) => row.player.position));

  const pool = [...available];
  const totalPicks = N_TEAMS * N_ROUNDS;
  let pi = pickIndex;
  while (pi < totalPicks) {
    const team = teamForPick(pi);
    if (!pool.length || slotsLeft[team] <= 0) { pi++; continue; }
    let best = null;
    let bestAt = -1;
    if (team === myTeamIdx) {
      // My future picks: greedy by expected points, weighted by roster need.
      const round = Math.floor(pi / N_TEAMS);
      let bestScore = -Infinity;
      for (let k = 0; k < pool.length; k++) {
        const s = userPickScore(pool[k], posCounts[team], round);
        if (s > bestScore) { bestScore = s; best = pool[k]; bestAt = k; }
      }
    } else if (profiles) {
      // Opponent picks: §13 softmax model.
      const profile = profiles[team] ?? { weights: undefined, temperature: 0.8 };
      const k = samplePick(pool, posCounts[team], recent[team], profile, rng);
      best = pool[k]; bestAt = k;
    } else {
      // Legacy fallback: temperature-window heuristic.
      const chosen = botSamplePick(pool, posCounts[team]);
      if (chosen) { best = chosen.p; bestAt = chosen.k; }
    }
    if (!best) { pi++; continue; }
    rosterIdxs[team].push(best.idx);
    posCounts[team][best.position] = (posCounts[team][best.position] || 0) + 1;
    recent[team].push(best.position);
    slotsLeft[team]--;
    pool.splice(bestAt, 1);
    pi++;
  }
  return rosterIdxs;
}

/** Place a candidate into the first slot on my roster that legally accepts it. */
export function placeCandidate(myRoster, candidate) {
  const canSlot = (slot, pos) => {
    if (slot === pos) return true;
    if (slot === "SUPERFLEX") return ["QB", "RB", "WR", "TE"].includes(pos);
    if (slot === "FLEX") return ["RB", "WR", "TE"].includes(pos);
    if (slot === "BENCH") return true;
    return false;
  };
  const slotPri = (slot, pos) => {
    if (slot === pos) return 0;
    if (slot === "FLEX") return 1;
    if (slot === "SUPERFLEX") return 2;
    if (slot === "BENCH") return 3;
    return 4;
  };
  const next = myRoster.map((r) => ({ ...r }));
  const open = next
    .map((r, i) => ({ i, r }))
    .filter(({ r }) => !r.player && canSlot(r.slot, candidate.position));
  open.sort((a, b) => slotPri(a.r.slot, candidate.position) - slotPri(b.r.slot, candidate.position));
  if (open.length) next[open[0].i] = { ...next[open[0].i], player: candidate };
  return next;
}