/** Piecewise-linear fantasy-point PDFs. */

export const N_KNOTS = 9;
export const LEGACY_STORAGE_KEY = "bb-wk2-projections-v1";

export function playerKey(p) {
  if (p?.id != null) return String(p.id);
  return `${p.name}|${p.team}|${p.position}`;
}

export function uniformKnots(n = N_KNOTS) {
  return Array.from({ length: n }, () => 1);
}

function xs(min, max, n) {
  if (n <= 1) return [min];
  const dx = (max - min) / (n - 1);
  return Array.from({ length: n }, (_, i) => min + i * dx);
}

function clampKnots(knots) {
  return knots.map((y) => (Number.isFinite(y) ? Math.max(0, y) : 0));
}

export function isValidRange(min, max) {
  return Number.isFinite(min) && Number.isFinite(max) && max > min + 1e-6;
}

export function summarize(min, max, knots) {
  const n = knots?.length || 0;
  if (!isValidRange(min, max) || n < 2) return null;
  const dx = (max - min) / (n - 1);
  const ys = clampKnots(knots);
  const uniform = ys.every((y) => y <= 1e-12);
  const yUse = uniform ? ys.map(() => 1) : ys;

  let mass = 0;
  let moment = 0;
  let m2 = 0;
  for (let i = 0; i < n - 1; i++) {
    const x0 = min + i * dx;
    const y0 = yUse[i];
    const y1 = yUse[i + 1];
    const dy = y1 - y0;
    mass += dx * (y0 + y1) / 2;
    moment += dx * (x0 * y0 + (x0 * dy + dx * y0) / 2 + (dx * dy) / 3);
    m2 += dx * (
      x0 * x0 * y0
      + (x0 * x0 * dy + 2 * x0 * dx * y0) / 2
      + (2 * x0 * dx * dy + dx * dx * y0) / 3
      + (dx * dx * dy) / 4
    );
  }
  if (mass <= 1e-12) return null;
  const mean = moment / mass;
  const variance = Math.max(0, m2 / mass - mean * mean);

  function invCdf(p) {
    const target = Math.min(1, Math.max(0, p)) * mass;
    let acc = 0;
    for (let i = 0; i < n - 1; i++) {
      const x0 = min + i * dx;
      const y0 = yUse[i];
      const y1 = yUse[i + 1];
      const dy = y1 - y0;
      const area = dx * (y0 + y1) / 2;
      if (acc + area >= target - 1e-12) {
        const need = Math.max(0, target - acc);
        let s;
        if (Math.abs(dy) < 1e-12) {
          s = y0 > 1e-12 ? (need / dx) / y0 : 0;
        } else {
          const a = dy / 2;
          const b = y0;
          const c = -need / dx;
          const disc = Math.max(0, b * b - 4 * a * c);
          s = (-b + Math.sqrt(disc)) / (2 * a);
        }
        return x0 + Math.min(1, Math.max(0, s)) * dx;
      }
      acc += area;
    }
    return max;
  }

  return {
    min,
    max,
    knots: yUse,
    mean,
    median: invCdf(0.5),
    p10: invCdf(0.1),
    p90: invCdf(0.9),
    sd: Math.sqrt(variance),
    invCdf,
    xs: xs(min, max, n),
  };
}

/** Draw u ~ U(0,1) through the inverse CDF. */
export function sample(min, max, knots, u) {
  const s = summarize(min, max, knots);
  if (!s) return null;
  return s.invCdf(u);
}

function quantileOf(sortedValues, q) {
  const pos = (sortedValues.length - 1) * q;
  const base = Math.floor(pos);
  const rest = pos - base;
  if (sortedValues[base + 1] !== undefined) {
    return sortedValues[base] + rest * (sortedValues[base + 1] - sortedValues[base]);
  }
  return sortedValues[base];
}

/** Silverman's rule of thumb, robust to outliers via the IQR. */
function silvermanBandwidth(values) {
  const n = values.length;
  if (n < 2) return 1;
  const mean = values.reduce((a, b) => a + b, 0) / n;
  const variance = values.reduce((a, b) => a + (b - mean) ** 2, 0) / (n - 1);
  const sd = Math.sqrt(variance);
  const sorted = [...values].sort((a, b) => a - b);
  const iqr = quantileOf(sorted, 0.75) - quantileOf(sorted, 0.25);
  const spread = iqr > 1e-6 ? Math.min(sd, iqr / 1.349) : sd;
  const safe = spread > 1e-6 ? spread : Math.max(sd, 1e-6);
  return 0.9 * safe * Math.pow(n, -0.2);
}

/**
 * Boundary knots aren't assumed to be hard walls: a knot that's still high
 * relative to the curve's peak implies the true distribution hasn't finished
 * tapering off yet, so a small, unseen slice of probability is assumed to
 * fall beyond that edge. A knot near zero implies the curve has already
 * tapered to (near) nothing, so almost no mass is assumed beyond it. This
 * tail share grows/shrinks continuously with the edge knot's height,
 * capped at `maxTailFrac` (5% by default) per side.
 */
export const MAX_TAIL_FRAC = 0.05;
/** Hard cap on implied tail width (fantasy points) so samples cannot explode. */
export const TAIL_WIDTH_CAP = 6;
export const TAIL_WIDTH_SPAN_FRAC = 0.15;

export function edgeTailFraction(edgeHeight, peakHeight, maxTailFrac = MAX_TAIL_FRAC) {
  if (!(peakHeight > 1e-9)) return 0;
  const ratio = Math.max(0, Math.min(1, edgeHeight / peakHeight));
  return maxTailFrac * ratio;
}

/**
 * Implied mass just outside [min, max]. Width is finite: a triangle that
 * continues the edge knot down to zero, capped at 8 points or 30% of the
 * visible span, and never below 0.
 */
export function tailSpec(min, max, knots, maxTailFrac = MAX_TAIL_FRAC) {
  const n = knots?.length || 0;
  if (!isValidRange(min, max) || n < 2) return null;
  const ys = clampKnots(knots);
  const peak = Math.max(...ys, 0);
  const tailL = edgeTailFraction(ys[0], peak, maxTailFrac);
  const tailR = edgeTailFraction(ys[n - 1], peak, maxTailFrac);
  const span = max - min;
  const cap = Math.min(TAIL_WIDTH_CAP, Math.max(0, TAIL_WIDTH_SPAN_FRAC * span));
  const leftW = min <= 0 ? 0 : Math.min(cap, min);
  const rightW = cap;
  return {
    tailL,
    tailR,
    leftW,
    rightW,
    visibleShare: Math.max(0, 1 - tailL - tailR),
    leftAtom: tailL > 0 && leftW <= 1e-9,
  };
}

/**
 * Inverse CDF of the visible piecewise-linear curve plus the implied
 * triangular tails. `u` is in [0, 1]. Left tail (if any) is a triangle
 * peaking at `min`; if min is 0 the leftover left mass is a point at 0.
 * Right tail is a triangle peaking at `max` and decaying to `max + rightW`.
 */
export function invCdfWithTails(min, max, knots, u, maxTailFrac = MAX_TAIL_FRAC) {
  const spec = tailSpec(min, max, knots, maxTailFrac);
  const vis = summarize(min, max, knots);
  if (!spec || !vis) return null;
  const p = Math.min(1 - 1e-12, Math.max(1e-12, u));

  if (p < spec.tailL) {
    if (spec.leftAtom || spec.leftW <= 1e-9) return min;
    const t = p / spec.tailL;
    return (min - spec.leftW) + spec.leftW * Math.sqrt(t);
  }

  const rightStart = 1 - spec.tailR;
  if (spec.tailR > 0 && p > rightStart) {
    const t = (p - rightStart) / spec.tailR;
    const tt = Math.min(1, Math.max(0, t));
    return max + spec.rightW * (1 - Math.sqrt(1 - tt));
  }

  const visP = spec.visibleShare > 1e-12
    ? (p - spec.tailL) / spec.visibleShare
    : 0.5;
  return vis.invCdf(visP);
}

/** Mean / P10 (top-10% threshold = 90th percentile) including implied tails. */
export function pdfStats(min, max, knots, maxTailFrac = MAX_TAIL_FRAC) {
  const vis = summarize(min, max, knots);
  const spec = tailSpec(min, max, knots, maxTailFrac);
  if (!vis || !spec) return null;
  const leftMean = spec.leftAtom || spec.leftW <= 1e-9
    ? min
    : min - spec.leftW / 3;
  const rightMean = max + spec.rightW / 3;
  const mean = spec.visibleShare * vis.mean
    + spec.tailL * leftMean
    + spec.tailR * rightMean;
  return {
    mean,
    visMean: vis.mean,
    sd: vis.sd,
    p10: invCdfWithTails(min, max, knots, 0.9, maxTailFrac),
    p90: invCdfWithTails(min, max, knots, 0.9, maxTailFrac),
    median: invCdfWithTails(min, max, knots, 0.5, maxTailFrac),
    spec,
  };
}

export function buildInvCdfTable(min, max, knots, n = 256) {
  const table = new Float32Array(n + 1);
  for (let i = 0; i <= n; i++) {
    table[i] = invCdfWithTails(min, max, knots, i / n) ?? 0;
  }
  return table;
}

export function lerpInvCdfTable(table, u) {
  const n = table.length - 1;
  const x = Math.min(1 - 1e-12, Math.max(1e-12, u)) * n;
  const i = Math.min(n - 1, Math.floor(x));
  const f = x - i;
  return table[i] * (1 - f) + table[i + 1] * f;
}

/**
 * For each knot, the share of the *total* distribution (visible curve plus
 * the small assumed tails beyond min/max) that lies to the right of that
 * knot's fantasy-point value. The leftmost knot's share is therefore
 * slightly under 100% (100% minus the assumed left-tail share), and the
 * rightmost knot's share equals the assumed right-tail share (usually a
 * few percent, or 0% if the curve already sits at zero at the boundary).
 */
export function knotRightTailShares(min, max, knots, { maxTailFrac = 0.05 } = {}) {
  const n = knots?.length || 0;
  if (!isValidRange(min, max) || n < 2) return null;
  const dx = (max - min) / (n - 1);
  const ys = clampKnots(knots);
  const uniform = ys.every((y) => y <= 1e-12);
  const yUse = uniform ? ys.map(() => 1) : ys;

  const peak = Math.max(...yUse);
  const tailL = edgeTailFraction(yUse[0], peak, maxTailFrac);
  const tailR = edgeTailFraction(yUse[n - 1], peak, maxTailFrac);
  const visibleShare = Math.max(0, 1 - tailL - tailR);

  const segAreas = [];
  for (let i = 0; i < n - 1; i++) {
    segAreas.push(dx * (yUse[i] + yUse[i + 1]) / 2);
  }
  const rawMass = segAreas.reduce((a, b) => a + b, 0);
  const cumLeft = [0];
  for (let i = 0; i < segAreas.length; i++) cumLeft.push(cumLeft[i] + segAreas[i]);

  return yUse.map((_, i) => {
    const x = min + i * dx;
    const rightVisibleFrac = rawMass > 1e-12 ? (rawMass - cumLeft[i]) / rawMass : 1 - i / (n - 1);
    const pctRight = tailR + visibleShare * rightVisibleFrac;
    return { x, pctRight: Math.max(0, Math.min(1, pctRight)) };
  });
}

/**
 * Nudge sharply-kinked knots toward their neighbors' average (discrete
 * Laplacian smoothing). Endpoints are left fixed so the support and rough
 * mean/median don't drift; interior knots that already sit close to the
 * local trend line barely move, while sharp spikes/dips get softened.
 */
export function smoothKnots(knots, { passes = 2, strength = 0.45 } = {}) {
  const n = knots?.length || 0;
  if (n < 3) return knots ? [...knots] : knots;
  let cur = knots.map((y) => (Number.isFinite(y) ? Math.max(0, y) : 0));
  for (let p = 0; p < passes; p++) {
    const next = [...cur];
    for (let i = 1; i < n - 1; i++) {
      const neighborAvg = (cur[i - 1] + cur[i + 1]) / 2;
      next[i] = Math.max(0, cur[i] + strength * (neighborAvg - cur[i]));
    }
    cur = next;
  }
  return cur.map((y) => Math.round(y * 1000) / 1000);
}

function peakNormalize(knots) {
  const peak = Math.max(...knots, 0);
  if (peak <= 1e-9) return knots.map(() => 1);
  return knots.map((k) => Math.round((Math.max(0, k) / peak) * 1000) / 1000);
}

/**
 * Multiply a piecewise-linear density by exp(λ (x-mid)/span) and search λ
 * so the mean on [min, max] matches `targetMean` (clamped into the interval).
 * Lowering max then piles mass toward the right; raising min piles it left.
 */
export function tiltKnotsToMean(min, max, knots, targetMean) {
  if (!isValidRange(min, max) || !knots?.length) return knots;
  const n = knots.length;
  const span = max - min;
  const xmid = (min + max) / 2;
  const grid = xs(min, max, n);
  const base = clampKnots(knots);
  if (base.every((y) => y <= 1e-12)) return uniformKnots(n);

  const target = Math.min(max - span * 1e-4, Math.max(min + span * 1e-4, targetMean));

  function tilted(lambda) {
    return base.map((y, i) => y * Math.exp(lambda * (grid[i] - xmid) / span));
  }
  function meanOf(lambda) {
    return summarize(min, max, tilted(lambda))?.mean;
  }

  const untilted = meanOf(0);
  if (untilted == null) return peakNormalize(base);
  if (Math.abs(untilted - target) < 0.04) return peakNormalize(base);

  let lo = -30;
  let hi = 30;
  const mLo = meanOf(lo);
  const mHi = meanOf(hi);
  if (mLo != null && target <= mLo) return peakNormalize(tilted(lo));
  if (mHi != null && target >= mHi) return peakNormalize(tilted(hi));

  for (let i = 0; i < 48; i++) {
    const mid = (lo + hi) / 2;
    const m = meanOf(mid);
    if (m == null) break;
    if (m < target) lo = mid;
    else hi = mid;
  }
  return peakNormalize(tilted((lo + hi) / 2));
}

/**
 * Fit slider heights to observed game scores on [min, max].
 * 1. Evaluate a Gaussian KDE at the knot abscissae (2025 shape).
 * 2. Exponentially tilt that curve so the mean on the new support matches
 *    the sample mean (or the nearest mean the interval can support).
 * Heights are relative; summarize() renormalizes area. Peak knot is 1.
 */
export function fitKnotsFromScores(scores, min, max, n = N_KNOTS) {
  if (!scores?.length || !isValidRange(min, max)) return null;
  const h = Math.max(silvermanBandwidth(scores), 1e-3);
  const dx = (max - min) / (n - 1);
  const norm = 1 / (scores.length * h * Math.sqrt(2 * Math.PI));
  const knots = [];
  for (let i = 0; i < n; i++) {
    const x = min + i * dx;
    let density = 0;
    for (const s of scores) {
      const u = (x - s) / h;
      density += Math.exp(-0.5 * u * u);
    }
    knots.push(density * norm);
  }
  const mu = scores.reduce((a, b) => a + b, 0) / scores.length;
  return tiltKnotsToMean(min, max, knots, mu);
}

/** One-time read of the old in-browser copy, if a disk file has not been chosen yet. */
export function loadLegacyProjections() {
  try {
    const raw = localStorage.getItem(LEGACY_STORAGE_KEY);
    if (!raw) return {};
    const data = JSON.parse(raw);
    if (data && data.byId && typeof data.byId === "object") return data.byId;
    if (data && typeof data === "object" && !Array.isArray(data)) return data;
    return {};
  } catch {
    return {};
  }
}

export function clearLegacyProjections() {
  try {
    localStorage.removeItem(LEGACY_STORAGE_KEY);
  } catch { /* ignore */ }
}

export function recordFromState(player, min, max, knots) {
  const s = summarize(min, max, knots);
  if (!s) return null;
  return {
    min: s.min,
    max: s.max,
    knots: knots.map((y) => Math.round(Math.max(0, y) * 1000) / 1000),
    name: player.name,
    team: player.team,
    position: player.position,
    updatedAt: new Date().toISOString(),
  };
}
