/**
 * Monte Carlo Web Worker for the Best Ball draft advisor.
 *
 * Messages IN:
 *   { type: 'INIT', players, correlations }
 *   { type: 'EVALUATE', myRoster, otherRosters, available, pickIndex, myTeam, candidates, chunkId }
 *   { type: 'SCORE_ALL_TEAMS', rosterIdxsByTeam }
 *
 * Messages OUT:
 *   { type: 'READY', nPlayers, nPdf, shrink }
 *   { type: 'RESULT', results, elapsed, chunkId }
 *   { type: 'ALL_TEAMS_RESULT', teamRates, elapsed }
 *   { type: 'PROGRESS', msg }
 */

import { N_SIM_DEFAULT, N_DRAFT_SAMPLES } from "../config/simConfig.js";
import { buildSimMatrix, bestBallTeamScores, finishRates, N_TEAMS } from "./simCore.js";
import { completeDraft, placeCandidate } from "./draftSim.js";

const N_SIM = N_SIM_DEFAULT;

let simMatrix = null;
let players = null;
let positionsByIdx = null;

// Portfolio Tracking Variables
let globalHistoricalWins = null;
let riskThreshold = 0;

self.onmessage = function (e) {
  const { type } = e.data;

  if (type === "INIT") {
    players = e.data.players;
    const { historicalContests } = e.data;
    const N = players.length;
    
    positionsByIdx = new Array(N);
    const idToLocal = {};
    for (let i = 0; i < N; i++) {
      positionsByIdx[i] = players[i]?.position ?? "";
      if (players[i]?.id) idToLocal[players[i].id] = i;
    }
    
    const built = buildSimMatrix(
      players,
      e.data.correlations,
      N_SIM,
      (msg) => postMessage({ type: "PROGRESS", msg })
    );
    simMatrix = built.matrix;

    // Pre-calculate the Historical Portfolio Win Vector
    globalHistoricalWins = new Uint16Array(N_SIM);
    if (historicalContests && historicalContests.length > 0) {
      for (const contest of historicalContests) {
        const teamScores = contest.teams.map((tIds) => {
          const localIds = tIds.map((id) => idToLocal[id]).filter((idx) => idx != null);
          return bestBallTeamScores(simMatrix, positionsByIdx, localIds, N, N_SIM);
        });

        const myTeamIdx = contest.myTeamIdx;
        const myScores = teamScores[myTeamIdx];
        
        for (let s = 0; s < N_SIM; s++) {
          const my = myScores[s];
          let won = true;
          for (let t = 0; t < teamScores.length; t++) {
            if (t !== myTeamIdx && teamScores[t][s] > my) { won = false; break; }
          }
          if (won) globalHistoricalWins[s]++;
        }
      }
      // Threshold: <= 25% of total contests (historical + the 1 we are drafting right now)
      riskThreshold = Math.floor((historicalContests.length + 1) * 0.25);
    } else {
      riskThreshold = 0; 
    }

    postMessage({ type: "READY", nPlayers: N, nPdf: built.nPdf, shrink: built.shrink });
    return;
  }

  if (type === "EVALUATE") {
    const t0 = performance.now();
    const { myRoster, otherRosters, available, pickIndex, myTeam, candidates, chunkId } = e.data;
    const N = players.length;

    const results = candidates.map((candidate) => {
      const newMyRoster = placeCandidate(myRoster, candidate);
      const newAvailable = available.filter((p) => p.id !== candidate.id);

      let top1Sum = 0, meanSum = 0, riskSum = 0;
      
      for (let d = 0; d < N_DRAFT_SAMPLES; d++) {
        const rosterIdxs = completeDraft(
          newMyRoster,
          otherRosters,
          newAvailable,
          pickIndex + 1,
          myTeam
        );
        const teamScores = rosterIdxs.map((idxs) =>
          bestBallTeamScores(simMatrix, positionsByIdx, idxs, N, N_SIM)
        );
        
        const myScores = teamScores[myTeam];
        let simTop1 = 0, simMean = 0, simRisk = 0;
        
        for (let s = 0; s < N_SIM; s++) {
          const my = myScores[s];
          simMean += my;
          
          let wonThis = 1;
          for (let t = 0; t < N_TEAMS; t++) {
            if (t !== myTeam && teamScores[t][s] > my) { wonThis = 0; break; }
          }
          simTop1 += wonThis;
          
          // Ultra-fast marginal risk check against pre-calculated history
          if (globalHistoricalWins[s] + wonThis <= riskThreshold) {
            simRisk++;
          }
        }

        top1Sum += (simTop1 / N_SIM) * 100;
        riskSum += (simRisk / N_SIM) * 100;
        meanSum += (simMean / N_SIM);
      }

      return {
        id: candidate.id,
        top1Rate: top1Sum / N_DRAFT_SAMPLES,
        riskPct: riskSum / N_DRAFT_SAMPLES,
        mean: meanSum / N_DRAFT_SAMPLES,
      };
    });

    results.sort((a, b) => b.top1Rate - a.top1Rate);
    postMessage({ type: "RESULT", results, elapsed: performance.now() - t0, chunkId });
    return;
  }

  if (type === "SCORE_ALL_TEAMS") {
    const t0 = performance.now();
    const { rosterIdxsByTeam } = e.data;
    const N = players.length;
    const teamScores = rosterIdxsByTeam.map((idxs) =>
      bestBallTeamScores(simMatrix, positionsByIdx, idxs, N, N_SIM)
    );
    const teamRates = rosterIdxsByTeam.map((_, teamIdx) => {
      const { top1Rate, top2Rate, mean } = finishRates(teamScores, teamIdx, N_SIM, N_TEAMS);
      return { top1Rate, top2Rate, mean };
    });
    postMessage({ type: "ALL_TEAMS_RESULT", teamRates, elapsed: performance.now() - t0 });
    return;
  }
};