/**
 * Data-driven AI opponent model — from public/data/ai_opponents.json (25 real
 * Draft Battle rooms, 2,200 picks). Each AI carries a position-by-round
 * distribution `pos_by_round[R][pos]` and player-targeting priors
 * `priors[name_key].share`. Pick weight = P(pos | AI, round) × player weight,
 * where player weight is the AI's own prior share, or a small global-ADP
 * baseline so current-week players the AI never faced still get
 * position-appropriate value. This replaces the synthetic pickModel when the
 * real data is present.
 */

const SUFFIXES = new Set(["jr", "sr", "ii", "iii", "iv", "v"]);

/** Exact JS port of ids.py name_key (strip trailing (POS), lower, alnum, drop suffixes). */
export function nameKey(name) {
  let n = String(name ?? "").replace(/\s*\([A-Z]{2,3}\)\s*$/, "").trim();
  n = n.toLowerCase().replace(/[^a-z0-9\s]/g, "");
  return n.split(/\s+/).filter((p) => p && !SUFFIXES.has(p)).join("");
}

/** Index the ais array by short name for seat assignment. */
export function aiByName(aiData) {
  const m = {};
  for (const a of aiData?.ais ?? []) m[a.name] = a;
  return m;
}

/**
 * Per-available-player pick weight for one AI at a 1-based round.
 * available: [{ nk?, name, position }]. adp: global name_key -> {draft_pct}.
 */
// The bots draft DETERMINISTICALLY: the highest-ranked available player (by the
// draft-page ranking = db_rank) at the position their observed script calls for.
// Given the ranking + each bot's script + your picks, the whole draft is exact.
const QB_CAP = 2;                                        // a 3rd QB can never score (SF)
function rankOf(p) { return (p && (p.db_rank ?? p.rank)) ?? 9999; }
function eligible(p, counts) {
  if (counts && p.position === "QB" && (counts.QB || 0) >= QB_CAP) return false;
  return true;
}

/** The position this AI drafts in a given 1-based round — its observed script. */
export function roundPos(ai, round) {
  const rs = ai?.round_script;
  if (rs && rs.length) return rs[Math.max(0, Math.min(rs.length - 1, round - 1))] || null;
  const pbr = ai?.pos_by_round && ai.pos_by_round[String(round)];
  if (pbr) return Object.keys(pbr).reduce((a, b) => ((pbr[b] ?? 0) > (pbr[a] ?? 0) ? b : a));
  return null;
}

/** Deterministic pick index: best-ranked available at the scripted position,
 *  fallback to best-ranked available among usable slots. -1 if none. */
export function deterministicPickIndex(available, ai, round, counts = null) {
  if (!available || !available.length) return -1;
  const pos = roundPos(ai, round);
  let bi = -1, br = Infinity;
  for (let i = 0; i < available.length; i++) {                 // 1) scripted position
    const p = available[i];
    if (p.position !== pos || !eligible(p, counts)) continue;
    const r = rankOf(p); if (r < br) { br = r; bi = i; }
  }
  if (bi >= 0) return bi;
  for (let i = 0; i < available.length; i++) {                 // 2) best-available usable
    if (!eligible(available[i], counts)) continue;
    const r = rankOf(available[i]); if (r < br) { br = r; bi = i; }
  }
  if (bi >= 0) return bi;
  return available.reduce((b, p, i) => (rankOf(p) < rankOf(available[b]) ? i : b), 0);  // all capped
}

/** One-hot deterministic "probabilities": the scripted pick is certain (1.0). */
export function pickProbabilities(available, ai, round, opts = {}) {
  const idx = deterministicPickIndex(available, ai, round, opts.counts ?? null);
  const pr = new Array(available.length).fill(0);
  if (idx >= 0) pr[idx] = 1;
  return pr;
}

/** Deterministic — rng ignored (the bots don't randomize). opts.counts enforces the QB cap. */
export function samplePick(available, ai, round, rng = Math.random, opts = {}) {
  const i = deterministicPickIndex(available, ai, round, opts.counts ?? null);
  return i >= 0 ? i : 0;
}

/** The certain next pick (100%) + the next-in-line at that position, for context. */
export function topPredicted(available, ai, round, k = 3, opts = {}) {
  const counts = opts.counts ?? null;
  const idx = deterministicPickIndex(available, ai, round, counts);
  const pos = roundPos(ai, round);
  const out = idx >= 0 ? [{ p: available[idx], pr: 1 }] : [];
  const rest = available.map((p, i) => ({ p, i }))
    .filter(({ p, i }) => i !== idx && p.position === pos && eligible(p, counts))
    .sort((a, b) => rankOf(a.p) - rankOf(b.p)).slice(0, Math.max(0, k - 1));
  for (const { p } of rest) out.push({ p, pr: 0 });
  return out.slice(0, k);
}
