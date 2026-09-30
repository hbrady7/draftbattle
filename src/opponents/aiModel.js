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
export function pickScores(available, ai, round, adp = null) {
  const pbr = (ai?.pos_by_round && ai.pos_by_round[String(round)]) || null;
  return available.map((p) => {
    const nk = p.nk ?? nameKey(p.name);
    const posW = pbr ? (pbr[p.position] ?? 0) : 0.25;              // P(pos | AI, round)
    const prior = ai?.priors && ai.priors[nk];
    let playerW;
    if (prior) playerW = prior.share;                              // the AI's own target prior
    else if (adp && adp[nk]) playerW = 0.15 * (adp[nk].draft_pct ?? 0) + 1e-3;  // ADP baseline
    else playerW = 1e-3;                                           // unseen: tiny epsilon
    return Math.max(1e-9, posW) * Math.max(1e-3, playerW);
  });
}

/** Softmax-ish over weights with a temperature exponent (temp<1 sharpens). */
export function pickProbabilities(available, ai, round, { adp = null, temperature = 0.8 } = {}) {
  const s = pickScores(available, ai, round, adp);
  const w = s.map((x) => Math.pow(Math.max(1e-12, x), 1 / Math.max(1e-6, temperature)));
  const sum = w.reduce((a, b) => a + b, 0) || 1;
  return w.map((e) => e / sum);
}

export function samplePick(available, ai, round, rng = Math.random, opts = {}) {
  const pr = pickProbabilities(available, ai, round, opts);
  let r = rng();
  for (let i = 0; i < pr.length; i++) { r -= pr[i]; if (r <= 0) return i; }
  for (let i = pr.length - 1; i >= 0; i--) if (pr[i] > 0) return i;
  return 0;
}

/** Top-k most likely next picks for an AI (the "predicted next" strip). */
export function topPredicted(available, ai, round, k = 3, opts = {}) {
  const pr = pickProbabilities(available, ai, round, opts);
  return available.map((p, i) => ({ p, pr: pr[i] })).sort((a, b) => b.pr - a.pr).slice(0, k);
}
