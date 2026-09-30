import { useEffect, useState } from "react";

/** Load the built JSON from public/data (served at /data/*). */
export function useData() {
  const [state, setState] = useState({ loading: true, error: null, board: null, sim: null, opponents: null, meta: null });
  useEffect(() => {
    let alive = true;
    Promise.all([
      fetch("/data/board.json").then((r) => r.json()),
      fetch("/data/sim.json").then((r) => r.json()),
      fetch("/data/opponents.json").then((r) => r.json()),
      fetch("/data/meta.json").then((r) => r.json()),
    ])
      .then(([board, sim, opponents, meta]) => {
        if (!alive) return;
        // Join sim idx + correlations universe onto board rows by id.
        const idxById = new Map(sim.players.map((p) => [p.id, p.idx]));
        const players = board.map((p) => ({ ...p, idx: idxById.get(p.id) ?? null, points: p.mean }));
        setState({ loading: false, error: null, board: players, sim, opponents, meta });
      })
      .catch((e) => alive && setState((s) => ({ ...s, loading: false, error: String(e) })));
    return () => { alive = false; };
  }, []);
  return state;
}
