/**
 * Live-draft Monte Carlo Web Worker (BRIEF §12).
 *
 * IN : { type:'INIT', players, correlations, profiles, seed, nSim }
 *      { type:'SCORE', rostersByTeam, myTeam, chunkId }          // current-rosters floor
 *      { type:'FILL',  myRoster, currentRosters, availableIdx, pickIndex, myTeam, fills, chunkId }
 * OUT: { type:'READY', N, nSim, nPdf }
 *      { type:'SCORE_RESULT', winPct, myMean, p05, p95, rank, teamMeans, chunkId }
 *      { type:'FILL_RESULT', winPct, chunkId }
 */
import { buildSimMatrix, bestBallTeamScores, setRngSeed, N_TEAMS } from "./simCore.js";
import { completeDraft, teamForPick } from "./draftSim.js";

let matrix = null, positionsByIdx = null, N = 0, nSim = 0;
let players = null, profiles = null;

function winAndStats(rostersByTeam, myTeam) {
  const teamScores = rostersByTeam.map((idxs) =>
    bestBallTeamScores(matrix, positionsByIdx, idxs, N, nSim));
  const my = teamScores[myTeam];
  let wins = 0, sum = 0;
  for (let s = 0; s < nSim; s++) {
    sum += my[s];
    let won = true;
    for (let t = 0; t < N_TEAMS; t++) {
      if (t !== myTeam && teamScores[t][s] > my[s]) { won = false; break; }
    }
    if (won) wins++;
  }
  const myArr = Array.from(my).sort((a, b) => a - b);
  const q = (p) => myArr[Math.max(0, Math.min(nSim - 1, Math.floor(p * (nSim - 1))))];
  const teamMeans = teamScores.map((ts) => {
    let s = 0; for (let i = 0; i < nSim; i++) s += ts[i]; return s / nSim;
  });
  const myMean = sum / nSim;
  const rank = 1 + teamMeans.filter((mm, t) => t !== myTeam && mm > myMean).length;
  return { winPct: (wins / nSim) * 100, myMean, p05: q(0.05), p95: q(0.95), rank, teamMeans };
}

self.onmessage = (e) => {
  const m = e.data;
  if (m.type === "INIT") {
    players = m.players;
    profiles = m.profiles;
    setRngSeed(m.seed ?? 12345);
    nSim = m.nSim ?? 12000;
    N = players.length;
    positionsByIdx = players.map((p) => p.position);
    const built = buildSimMatrix(players, m.correlations, nSim);
    matrix = built.matrix;
    self.postMessage({ type: "READY", N, nSim, nPdf: built.nPdf });
    return;
  }
  if (m.type === "SCORE") {
    self.postMessage({ type: "SCORE_RESULT", ...winAndStats(m.rostersByTeam, m.myTeam), chunkId: m.chunkId });
    return;
  }
  if (m.type === "FILL") {
    // Expected-fill: complete every roster K times via the §13 opponent model,
    // average my win%. rostersByTeam + availableIdx are LOCAL index arrays.
    const fills = m.fills ?? 30;
    const rows = (idxs) => idxs.map((li) => ({ player: players[li] }));
    const myRoster = rows(m.rostersByTeam[m.myTeam]);
    const otherRosters = m.rostersByTeam.filter((_, t) => t !== m.myTeam).map(rows);
    const availablePlayers = m.availableIdx.map((li) => players[li]);
    let winSum = 0;
    for (let f = 0; f < fills; f++) {
      const rosterIdxs = completeDraft(myRoster, otherRosters, availablePlayers,
        m.pickIndex, m.myTeam, { profiles, rng: Math.random });
      winSum += winAndStats(rosterIdxs, m.myTeam).winPct;
    }
    self.postMessage({ type: "FILL_RESULT", winPct: winSum / fills, chunkId: m.chunkId });
    return;
  }
};
