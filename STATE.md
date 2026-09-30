# STATE

_Current phase, what's done, what's next, dead ends already tried. Kept current every phase._

## Current phase
**Phase 4 — Opponents.** Next. Build the 7 default AI profiles + `scripts/opponents.py` / `src/opponents/`; check 500-draft simulated ADP vs DB rank.

## Done
- **Phase 0 — Audit and set up. ✅ committed `59bc525`.** Audited `draftTool` → REUSE sim (D0.3); scaffolded repo; dark 6-tab shell serves on `:5175`.
- **Phase 1 — Data layer. ✅ committed `ab98a11`.** `data_sources.py` (every §5 source, 12h cache, leakage guards, core-source stop) + `ids.py` (name_key replica, gsis crosswalk). 68/68 source-seasons clean; DB top-200 match 100%; Sleeper live.
- **Phase 2 — Baseline model. ✅ committed `0dff88c`.** `distribution.py` (projDist.js port + shape-A template + DNP mixture) + `build_board.py` → `board.json` (369). Checks: §6b unit test, SD within 0.026, named players sane.
- **Phase 3 — Simulator. ✅ complete (committing now).**
  - `scripts/sim.py`: seeded numpy Gaussian-copula sim (100k), ported `build_correlations`, vectorized best-ball (validated == greedy), writes `public/data/sim.json`.
  - `src/sim/simCore.js`: added seedable mulberry32 PRNG (`setRngSeed`). `scripts/sim_parity.mjs`: Node driver running the browser's JS sim.
  - **Checks passed:** parity **0.25pt** (JS 20k vs Python 100k); per-pick 8×11 eval **71ms** (<300ms); simConfig reconciled to §12 (20k/40k, Python 100k).

## Next
- Phase 4: default AI opponent profiles + `scripts/opponents.py` + `src/opponents/`; softmax pick model (neg DB rank + positional need, temp 0.8). **Check:** 500-draft simulated ADP vs DB rank (high rank correlation).

## Blockers / open
- **GitHub remote still not created — push is blocked.** `git push` returns the exact error `ERROR: Repository not found` (SSH auth to `hbrady7` is confirmed working; the repo simply doesn't exist). Local commits continue each phase; all get pushed once `hbrady7/draftbattle.js` (private) exists — user to create it, or provide a PAT / install `gh`. See DECISIONS D0.7.

## Dead ends tried
- `gh` CLI, `brew`, `~/.git-credentials`, credential helper, keychain github item, `*TOKEN*` env var — all absent. SSH auth to `hbrady7` verified working (push fails only because the repo doesn't exist yet).
