import { useEffect, useMemo, useRef, useState } from "react";

/**
 * Manage the live-draft sim worker over a capped draftable universe (top-K by DB
 * rank) with a dense local index space. Returns helpers to score rosters (floor)
 * and estimate the expected-fill win%.
 */
export function useSim(board, sim, opponents, aiData, { universeSize = 200, nSim = 12000 } = {}) {
  const [ready, setReady] = useState(false);
  const workerRef = useRef(null);
  const waiters = useRef(new Map());
  const chunk = useRef(0);

  // Build the capped universe + local remap (stable for the session).
  const universe = useMemo(() => {
    if (!board || !sim) return null;
    const pool = board.filter((p) => p.idx != null).sort((a, b) => a.db_rank - b.db_rank).slice(0, universeSize);
    const localOf = new Map(pool.map((p, i) => [p.id, i]));
    const globalToLocal = new Map(pool.map((p, i) => [p.idx, i]));
    const players = pool.map((p, i) => ({
      idx: i, id: p.id, name: p.name, nk: p.nk, position: p.position, team: p.team,
      db_rank: p.db_rank, points: p.mean, sd_pts: p.sd, min: p.min, max: p.max, knots: p.knots,
    }));
    const correlations = sim.correlations
      .filter(([a, b]) => globalToLocal.has(a) && globalToLocal.has(b))
      .map(([a, b, r]) => [globalToLocal.get(a), globalToLocal.get(b), r]);
    return { pool, players, correlations, localOf };
  }, [board, sim, universeSize]);

  useEffect(() => {
    if (!universe || !opponents) return;
    const w = new Worker(new URL("./simWorker.js", import.meta.url), { type: "module" });
    workerRef.current = w;
    w.onmessage = (e) => {
      const m = e.data;
      if (m.type === "READY") { setReady(true); return; }
      const resolve = waiters.current.get(m.chunkId);
      if (resolve) { waiters.current.delete(m.chunkId); resolve(m); }
    };
    w.postMessage({
      type: "INIT", players: universe.players, correlations: universe.correlations,
      profiles: opponents.profiles, aiData: aiData ?? null, seed: sim.meta?.seed ?? 12345, nSim,
    });
    return () => { w.terminate(); setReady(false); };
  }, [universe, opponents, sim, nSim, aiData]);

  const call = (msg) => new Promise((resolve) => {
    const id = ++chunk.current;
    waiters.current.set(id, resolve);
    workerRef.current.postMessage({ ...msg, chunkId: id });
  });

  return {
    ready,
    universe,
    /** rostersByTeam: array[8] of LOCAL idx arrays. */
    score: (rostersByTeam, myTeam) => call({ type: "SCORE", rostersByTeam, myTeam }),
    /** rostersByTeam + availableIdx: LOCAL idx arrays. aiSeatNames: array[8] AI names (null = my seat). */
    fill: (rostersByTeam, availableIdx, pickIndex, myTeam, fills = 30, aiSeatNames = null) =>
      call({ type: "FILL", rostersByTeam, availableIdx, pickIndex, myTeam, fills, aiSeatNames }),
    /** §12 per-candidate win%: resolves { baseline, results:[{localIdx, winPct}] }. */
    evaluate: (rostersByTeam, availableIdx, pickIndex, myTeam, candidateLocalIdxs, fills = 12, aiSeatNames = null) =>
      call({ type: "EVALUATE", rostersByTeam, availableIdx, pickIndex, myTeam, candidateLocalIdxs, fills, aiSeatNames }),
  };
}
