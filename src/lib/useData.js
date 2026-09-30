import { useEffect, useState } from "react";
import { nameKey } from "../opponents/aiModel.js";

/** Load the built JSON from public/data (served at /data/*). */
export function useData() {
  const [state, setState] = useState({ loading: true, error: null, board: null, sim: null, opponents: null, meta: null, aiData: null });
  useEffect(() => {
    let alive = true;
    Promise.all([
      fetch("/data/board.json").then((r) => r.json()),
      fetch("/data/sim.json").then((r) => r.json()),
      fetch("/data/opponents.json").then((r) => r.json()),
      fetch("/data/meta.json").then((r) => r.json()),
      fetch("/data/ai_opponents.json").then((r) => (r.ok ? r.json() : null)).catch(() => null), // optional
    ])
      .then(([board, sim, opponents, meta, aiData]) => {
        if (!alive) return;
        // Join sim idx + correlations universe onto board rows by id; cache name_key.
        const idxById = new Map(sim.players.map((p) => [p.id, p.idx]));
        const players = board.map((p) => ({ ...p, idx: idxById.get(p.id) ?? null, points: p.mean, nk: nameKey(p.name) }));
        setState({ loading: false, error: null, board: players, sim, opponents, meta, aiData });
      })
      .catch((e) => alive && setState((s) => ({ ...s, loading: false, error: String(e) })));
    return () => { alive = false; };
  }, []);
  return state;
}
