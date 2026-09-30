/**
 * Shared Monte Carlo core: correlated score sampling + best-ball scoring.
 *
 * Marginals: each player's own distribution.
 *   - Players carry a piecewise-linear PDF (min / max / 9 knots) plus
 *     the small implied tails just outside [min, max]. We sample it by
 *     inverting a pre-built CDF table.
 *   - Players without a PDF fall back to Gaussian μ + σz, clipped at 0.
 *
 * Dependence: a Gaussian copula. We draw correlated standard normals with a
 * Cholesky factor of the correlation matrix, push each through Φ, and feed
 * that uniform to the player's own inverse CDF.
 */

import { buildInvCdfTable, lerpInvCdfTable } from "./projDist.js";

export const N_TEAMS = 8;
export const N_ROUNDS = 11;

// Bitmasks for high-speed positional checking without string comparisons
const POS_MASK = {
  QB: 1, // 0001
  RB: 2, // 0010
  WR: 4, // 0100
  TE: 8, // 1000
};

// Allowed bits for flex slots
const FLEX_ALLOWED = POS_MASK.RB | POS_MASK.WR | POS_MASK.TE; // 1110
const SUPERFLEX_ALLOWED = POS_MASK.QB | POS_MASK.RB | POS_MASK.WR | POS_MASK.TE; // 1111

/** Cholesky factorization (lower triangular). */
export function cholesky(A, n) {
  const L = new Float64Array(n * n);
  for (let i = 0; i < n; i++) {
    for (let j = 0; j <= i; j++) {
      let sum = 0;
      for (let k = 0; k < j; k++) sum += L[i * n + k] * L[j * n + k];
      if (i === j) {
        const v = A[i * n + i] - sum;
        L[i * n + j] = v > 0 ? Math.sqrt(v) : 1e-9;
      } else {
        const Ljj = L[j * n + j];
        L[i * n + j] = Ljj > 1e-12 ? (A[i * n + j] - sum) / Ljj : 0;
      }
    }
  }
  return L;
}

/** Box-Muller standard normals. */
export function stdNormals(count, out) {
  const arr = out ?? new Float64Array(count);
  for (let i = 0; i < count - 1; i += 2) {
    const u1 = Math.random() || 1e-10;
    const u2 = Math.random();
    const mag = Math.sqrt(-2 * Math.log(u1));
    arr[i] = mag * Math.cos(2 * Math.PI * u2);
    arr[i + 1] = mag * Math.sin(2 * Math.PI * u2);
  }
  if (count % 2 === 1) {
    arr[count - 1] = Math.sqrt(-2 * Math.log(Math.random() || 1e-10)) * Math.cos(2 * Math.PI * Math.random());
  }
  return arr;
}

export function erf(x) {
  const sign = x < 0 ? -1 : 1;
  const ax = Math.abs(x);
  const t = 1 / (1 + 0.3275911 * ax);
  const y = 1 - (((((1.061405429 * t - 1.453152027) * t) + 1.421413741) * t - 0.284496736) * t + 0.254829592) * t * Math.exp(-ax * ax);
  return sign * y;
}

export function normCdf(z) {
  return 0.5 * (1 + erf(z / Math.SQRT2));
}

export function hasPdf(p) {
  return !!p && Array.isArray(p.knots) && p.knots.length >= 2
    && Number.isFinite(p.min) && Number.isFinite(p.max) && p.max > p.min;
}

export function corrCholesky(n, correlations) {
  const R = new Float64Array(n * n);
  for (let i = 0; i < n; i++) R[i * n + i] = 1;
  for (const [i, j, rho] of correlations || []) {
    if (i === j || i < 0 || j < 0 || i >= n || j >= n) continue;
    const r = Math.max(-0.95, Math.min(0.95, rho));
    R[i * n + j] = r;
    R[j * n + i] = r;
  }

  const A = new Float64Array(n * n);
  function factor(scale) {
    for (let i = 0; i < n; i++) {
      for (let j = 0; j < n; j++) {
        A[i * n + j] = i === j ? 1 : R[i * n + j] * scale;
      }
    }
    const L = cholesky(A, n);
    let minD = Infinity;
    for (let i = 0; i < n; i++) minD = Math.min(minD, L[i * n + i]);
    return { L, minD, scale };
  }

  let scale = 1;
  let res = factor(scale);
  while (res.minD < 1e-5 && scale > 0.3) {
    scale *= 0.85;
    res = factor(scale);
  }
  return res;
}

export function buildSimMatrix(playerList, correlations, nSim, onProgress) {
  const N = playerList.length;
  const byIdx = new Array(N);
  for (const p of playerList) if (p?.idx != null && p.idx < N) byIdx[p.idx] = p;
  for (let i = 0; i < N; i++) if (!byIdx[i]) byIdx[i] = playerList[i];

  onProgress?.(`Building ${N}×${N} copula correlation…`);
  const { L, scale } = corrCholesky(N, correlations);

  onProgress?.("Building inverse-CDF tables…");
  const tables = new Array(N);
  const mu = new Float64Array(N);
  const sd = new Float64Array(N);
  const usePdf = new Uint8Array(N);
  let nPdf = 0;
  for (let i = 0; i < N; i++) {
    const p = byIdx[i];
    mu[i] = p?.points ?? 0;
    sd[i] = Math.max(0.5, p?.sd_pts ?? 4);
    if (hasPdf(p)) {
      usePdf[i] = 1;
      tables[i] = buildInvCdfTable(p.min, p.max, p.knots);
      nPdf++;
    }
  }

  onProgress?.(`Pre-sampling ${nSim.toLocaleString()} scenarios (${nPdf}/${N} from PDFs)…`);
  const mat = new Float32Array(nSim * N);
  const z = new Float64Array(N);
  for (let s = 0; s < nSim; s++) {
    stdNormals(N, z);
    const base = s * N;
    for (let i = 0; i < N; i++) {
      const row = i * N;
      let yi = 0;
      for (let j = 0; j <= i; j++) yi += L[row + j] * z[j];
      let val;
      if (usePdf[i]) {
        const u = Math.min(1 - 1e-9, Math.max(1e-9, normCdf(yi)));
        val = lerpInvCdfTable(tables[i], u);
      } else {
        val = mu[i] + sd[i] * yi;
      }
      mat[base + i] = val > 0 ? val : 0;
    }
  }
  onProgress?.(`Simulation matrix ready (${nSim.toLocaleString()} × ${N}).`);
  return { matrix: mat, shrink: scale, nPdf };
}

/**
 * Best-ball total for one roster in every sim. Zero-allocation loop for performance.
 * Lineup: 1 QB, 2 RB, 3 WR, 1 TE, 1 SUPERFLEX (QB/RB/WR/TE), 1 FLEX (RB/WR/TE).
 */
export function bestBallTeamScores(simMatrix, positionsByIdx, playerIndices, N, nSim) {
  const nPlayers = playerIndices.length;
  const out = new Float32Array(nSim);
  
  // Pre-allocate scratchpads outside the loop
  const scores = new Float32Array(nPlayers);
  const posBits = new Int32Array(nPlayers);
  const order = new Int32Array(nPlayers);
  const used = new Uint8Array(nPlayers);

  // Map string positions to bitmasks once
  for (let k = 0; k < nPlayers; k++) {
    const pStr = positionsByIdx[playerIndices[k]];
    posBits[k] = POS_MASK[pStr] || 0;
  }

  for (let s = 0; s < nSim; s++) {
    const baseRow = s * N;
    
    // 1. Gather scores via direct matrix stride indexing
    for (let k = 0; k < nPlayers; k++) {
      scores[k] = simMatrix[baseRow + playerIndices[k]];
      order[k] = k;
      used[k] = 0;
    }

    // 2. Inline Insertion Sort (fastest for small N like 11)
    for (let i = 1; i < nPlayers; i++) {
      let j = i;
      while (j > 0 && scores[order[j - 1]] < scores[order[j]]) {
        const temp = order[j];
        order[j] = order[j - 1];
        order[j - 1] = temp;
        j--;
      }
    }

    let total = 0;
    
    // 3. Roster fill logic using bitwise operators
    // take() inline macro to prevent closure creation
    let takenQB = 0, takenRB = 0, takenWR = 0, takenTE = 0, takenSF = 0, takenFLEX = 0;

    for (let i = 0; i < nPlayers; i++) {
      const k = order[i];
      if (used[k]) continue;
      const bit = posBits[k];

      // Mandatory Slots
      if (bit === POS_MASK.QB && takenQB < 1) {
        used[k] = 1; takenQB++; total += scores[k]; continue;
      }
      if (bit === POS_MASK.RB && takenRB < 2) {
        used[k] = 1; takenRB++; total += scores[k]; continue;
      }
      if (bit === POS_MASK.WR && takenWR < 3) {
        used[k] = 1; takenWR++; total += scores[k]; continue;
      }
      if (bit === POS_MASK.TE && takenTE < 1) {
        used[k] = 1; takenTE++; total += scores[k]; continue;
      }
      
      // Flex Slot
      if (takenFLEX < 1 && (bit & FLEX_ALLOWED)) {
        used[k] = 1; takenFLEX++; total += scores[k]; continue;
      }

      // Superflex Slot
      if (takenSF < 1 && (bit & SUPERFLEX_ALLOWED)) {
        used[k] = 1; takenSF++; total += scores[k]; continue;
      }

      // Early exit if all 9 starting slots are filled
      if (takenQB === 1 && takenRB === 2 && takenWR === 3 && takenTE === 1 && takenSF === 1 && takenFLEX === 1) {
        break;
      }
    }
    
    out[s] = total;
  }
  return out;
}

export function finishRates(teamScores, myTeamIdx, nSim, nTeams = N_TEAMS) {
  let top1 = 0, top2 = 0, sumMy = 0;
  const myScores = teamScores[myTeamIdx];
  for (let s = 0; s < nSim; s++) {
    const my = myScores[s];
    sumMy += my;
    let rank = 1;
    for (let t = 0; t < nTeams; t++) {
      if (t !== myTeamIdx && teamScores[t][s] > my) rank++;
    }
    if (rank <= 1) top1++;
    if (rank <= 2) top2++;
  }
  return {
    top1Rate: (top1 / nSim) * 100,
    top2Rate: (top2 / nSim) * 100,
    mean: sumMy / nSim,
  };
}

export function buildCorrelations(players, teamToOpp) {
  const BASE_SAME = { "QB-WR": 0.15, "QB-TE": 0.15, "QB-RB": 0.05 };
  const BASE_OPP  = { "QB-QB": 0.20 };

  const ROLE_DELTA = [
    ["QB",      "PASS1",  "same", 0.25],
    ["RUSH_QB", "PASS1",  "same", 0.13],
    ["QB",      "PASS2",  "same", 0.15],
    ["RUSH_QB", "PASS2",  "same", 0.15],
    ["RUSH_QB", "WR",     "same", 0.05], 
    ["PASS1",   "PASS1",  "opp",  0.18],
    ["QB",      "PASS1",  "opp",  0.08],
    ["RUSH_QB", "PASS1",  "opp",  0.05],
  ];

  function getRoleDelta(posA, roleA, posB, roleB, scope) {
    if (roleA == null && roleB == null) return 0;
    const keyA = roleA ?? posA;
    const keyB = roleB ?? posB;
    for (const [ra, rb, sc, delta] of ROLE_DELTA) {
      if (sc !== scope) continue;
      if ((keyA === ra && keyB === rb) || (keyA === rb && keyB === ra)) return delta;
    }
    return 0;
  }

  const corr = new Map();
  function addCorr(i, j, rho) {
    if (i === j) return;
    const key = `${Math.min(i, j)},${Math.max(i, j)}`;
    const prev = corr.get(key) ?? 0;
    if (Math.abs(rho) >= Math.abs(prev)) corr.set(key, rho);
  }

  const byTeam = new Map();
  for (const p of players) {
    const t = p.team ?? "";
    if (!byTeam.has(t)) byTeam.set(t, []);
    byTeam.get(t).push(p);
  }

  for (const [, plist] of byTeam) {
    const qbs  = plist.filter((p) => p.position === "QB")
                      .sort((a, b) => (b.points ?? 0) - (a.points ?? 0));
    const recs = plist.filter((p) => p.position === "WR" || p.position === "TE");
    const rbs  = plist.filter((p) => p.position === "RB");
    if (!qbs.length) continue;
    const q = qbs[0]; 
    const qRole = q.role ?? null;

    for (const r of recs) {
      const base  = BASE_SAME[`QB-${r.position}`] ?? 0;
      const delta = getRoleDelta("QB", qRole, r.position, r.role ?? null, "same");
      const rho   = Math.max(-0.95, Math.min(0.95, base + delta));
      if (rho !== 0) addCorr(q.idx, r.idx, rho);
    }
    for (const rb of rbs) {
      const base  = BASE_SAME["QB-RB"] ?? 0;
      const delta = getRoleDelta("QB", qRole, "RB", rb.role ?? null, "same");
      const rho   = Math.max(-0.95, Math.min(0.95, base + delta));
      if (rho !== 0) addCorr(q.idx, rb.idx, rho);
    }
  }

  const seenGames = new Set();
  for (const [team, opp] of Object.entries(teamToOpp)) {
    const gameKey = [team, opp].sort().join("@");
    if (seenGames.has(gameKey)) continue;
    seenGames.add(gameKey);

    const ti = byTeam.get(team) ?? [];
    const oi = byTeam.get(opp)  ?? [];

    const tiQbs = ti.filter((p) => p.position === "QB")
                    .sort((a, b) => (b.points ?? 0) - (a.points ?? 0));
    const oiQbs = oi.filter((p) => p.position === "QB")
                    .sort((a, b) => (b.points ?? 0) - (a.points ?? 0));
    const tiStarterIdx = tiQbs[0]?.idx ?? -1;
    const oiStarterIdx = oiQbs[0]?.idx ?? -1;

    for (const a of ti) {
      for (const b of oi) {
        const base =
          a.position === "QB" && b.position === "QB" &&
          a.idx === tiStarterIdx && b.idx === oiStarterIdx
            ? BASE_OPP["QB-QB"]
            : 0;
        const delta = getRoleDelta(
          a.position, a.role ?? null,
          b.position, b.role ?? null,
          "opp"
        );
        const rho = Math.max(-0.95, Math.min(0.95, base + delta));
        if (rho !== 0) addCorr(a.idx, b.idx, rho);
      }
    }
  }

  const result = [];
  for (const [key, rho] of corr) {
    const [i, j] = key.split(",").map(Number);
    result.push([i, j, rho]);
  }
  result.sort((a, b) => a[0] - b[0] || a[1] - b[1]);
  return result;
}