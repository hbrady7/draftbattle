# STATE

_Current phase, what's done, what's next, dead ends already tried. Kept current every phase._

## Current phase
**Phase 5 — Dashboard core.** Next (last baseline phase). Build the Board, Draft Room, and Data tabs + `npm run week -- --week N`. **Check:** `npm run build` passes; scripted mock draft from seat 4 updates win% each pick and exports valid JSON. Then: "Baseline ready for Week 4 at localhost:5175."

## Done
- **Phase 0 — Audit and set up. ✅ committed `59bc525`.** Audited `draftTool` → REUSE sim (D0.3); scaffolded repo; dark 6-tab shell serves on `:5175`.
- **Phase 1 — Data layer. ✅ committed `ab98a11`.** `data_sources.py` (every §5 source, 12h cache, leakage guards, core-source stop) + `ids.py` (name_key replica, gsis crosswalk). 68/68 source-seasons clean; DB top-200 match 100%; Sleeper live.
- **Phase 2 — Baseline model. ✅ committed `0dff88c`.** `distribution.py` (projDist.js port + shape-A template + DNP mixture) + `build_board.py` → `board.json` (369). Checks: §6b unit test, SD within 0.026, named players sane.
- **Phase 3 — Simulator. ✅ committed `2369f87`.** `sim.py` (seeded copula, vectorized best-ball, sim.json) + `simCore.js` seedable PRNG + `sim_parity.mjs`. Parity 0.25pt; 8×11 eval 71ms.
- **Phase 4 — Opponents. ✅ complete (committing now).**
  - `scripts/opponents.py`: §13 softmax pick model (fixed-scale features), 8 default profiles → `public/data/opponents.json`, 500-draft ADP sim + `--fit` stub.
  - `src/opponents/pickModel.js`: browser mirror for live-draft fills.
  - **Check passed:** Spearman(ADP, DB rank) = **0.998**; ADP tracks rank with realistic noise (Gibbs rank 1 → ADP 5.3).

## Next
- Phase 5 (last baseline phase): Board / Draft Room / Data tabs; `npm run week -- --week N` wrapper; wire `draftSim.completeDraft` to `pickModel`. **Check:** `npm run build` passes; scripted seat-4 mock draft updates win% each pick + exports valid JSON. Announce baseline ready.

## Blockers / open
- **GitHub remote still not created — push is blocked.** `git push` returns the exact error `ERROR: Repository not found` (SSH auth to `hbrady7` is confirmed working; the repo simply doesn't exist). Local commits continue each phase; all get pushed once `hbrady7/draftbattle.js` (private) exists — user to create it, or provide a PAT / install `gh`. See DECISIONS D0.7.

## Dead ends tried
- `gh` CLI, `brew`, `~/.git-credentials`, credential helper, keychain github item, `*TOKEN*` env var — all absent. SSH auth to `hbrady7` verified working (push fails only because the repo doesn't exist yet).
