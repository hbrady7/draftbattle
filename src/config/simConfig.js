/** Correlated score scenarios per session matrix (§12: browser draws 20,000). */
export const N_SIM_DEFAULT = 20_000;

/** Independent future-draft fills averaged per candidate in the live advisor.
 *  (Opponent-draft uncertainty; each fill is scored over the full N_SIM matrix.
 *  Tuned against the live-eval latency budget in Phase 5.) */
export const N_DRAFT_SAMPLES = 20;

/** Scenarios for the post-draft results view in-browser. Python's post-draft
 *  report (scripts/sim.py) uses 100,000; the browser trades a little precision
 *  for interactivity. */
export const N_SIM_RESULTS = 40_000;
