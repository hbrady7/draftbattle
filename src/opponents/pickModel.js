/**
 * BRIEF §13 AI opponent pick model (browser side; mirrors scripts/opponents.py).
 *
 * Pick probability = softmax over available players of score/temperature, score =
 * weighted sum of standardized features: -DB rank, our mean, positional need
 * (-inf for a dead position, e.g. 3rd QB), position-run share, QB-early bonus.
 * Standardization uses fixed scales (NOT per-pool z-score) so the softmax stays
 * sharp at temperature 0.8.
 */

export const REQUIRED = { QB: 2, RB: 2, WR: 3, TE: 1 }; // superflex targets
export const HARD_CAP = { QB: 2 };                      // 3rd QB can never score
export const RANK_SCALE = 8.0;
export const MEAN_SCALE = 8.0;

export const DEFAULT_WEIGHTS = {
  db_rank: 1.0, our_mean: 0.0, positional_need: 0.6, position_run: 0.0, qb_early: 0.0,
};

export function defaultProfiles(nTeams = 8) {
  return Array.from({ length: nTeams }, (_, i) => ({
    name: `AI-${i + 1}`, seat: i + 1,
    weights: { ...DEFAULT_WEIGHTS }, temperature: 0.8, notes: "",
  }));
}

/** Scores for each available player (index-aligned). -Infinity = ineligible. */
export function pickScores(available, counts, recent, weights) {
  const last = recent.slice(-5);
  const runShare = {};
  for (const p of ["QB", "RB", "WR", "TE"]) {
    runShare[p] = last.length ? last.filter((x) => x === p).length / last.length : 0;
  }
  return available.map((pl) => {
    const pos = pl.position;
    if (HARD_CAP[pos] != null && (counts[pos] || 0) >= HARD_CAP[pos]) return -Infinity;
    const fRank = -(pl.db_rank ?? 999) / RANK_SCALE;
    const fMean = (pl.points ?? pl.mean ?? 0) / MEAN_SCALE;
    const fNeed = Math.max(0, (REQUIRED[pos] ?? 0) - (counts[pos] || 0)) + 0.25;
    const fRun = runShare[pos] ?? 0;
    const fQb = pos === "QB" ? 1 : 0;
    return weights.db_rank * fRank + weights.our_mean * fMean
      + weights.positional_need * fNeed + weights.position_run * fRun
      + weights.qb_early * fQb;
  });
}

/** Softmax probabilities from scores at a temperature. */
export function pickProbabilities(available, counts, recent, profile) {
  const scores = pickScores(available, counts, recent, profile.weights);
  const t = Math.max(1e-6, profile.temperature ?? 0.8);
  let max = -Infinity;
  for (const s of scores) if (Number.isFinite(s) && s > max) max = s;
  if (!Number.isFinite(max)) return scores.map(() => 0);
  const ex = scores.map((s) => (Number.isFinite(s) ? Math.exp((s - max) / t) : 0));
  const sum = ex.reduce((a, b) => a + b, 0) || 1;
  return ex.map((e) => e / sum);
}

/** Sample one available player index via the model. rng() -> [0,1). */
export function samplePick(available, counts, recent, profile, rng = Math.random) {
  const pr = pickProbabilities(available, counts, recent, profile);
  let r = rng();
  for (let i = 0; i < pr.length; i++) {
    r -= pr[i];
    if (r <= 0) return i;
  }
  for (let i = pr.length - 1; i >= 0; i--) if (pr[i] > 0) return i;
  return 0;
}
