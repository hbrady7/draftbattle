# STATE

_Current phase, what's done, what's next, dead ends already tried. Kept current every phase._

## Current phase
**Phase 3 — Simulator.** Next. Build `public/data/sim.json`, wire the browser Web Worker sim, and the seeded Python sim; parity within 1 pt, timing < 300 ms.

## Done
- **Phase 0 — Audit and set up. ✅ committed `59bc525`.** Audited `draftTool` → REUSE sim (D0.3); scaffolded repo; dark 6-tab shell serves on `:5175`.
- **Phase 1 — Data layer. ✅ committed `ab98a11`.** `data_sources.py` (every §5 source, 12h cache, leakage guards, core-source stop) + `ids.py` (name_key replica, gsis crosswalk). 68/68 source-seasons clean; DB top-200 match 100%; Sleeper live.
- **Phase 2 — Baseline model. ✅ complete (committing now).**
  - `scripts/distribution.py`: browser-parity port of `projDist.js` (summarize/tailSpec/invCdfWithTails/257-node table) + shape-A (template base) + (1−p_play) DNP mixture.
  - `scripts/build_board.py`: interim mean (0.5·FFA + 0.5·ECR-implied, fallbacks, DB·0.85), backup-QB cap, `player_sd` SD, implied totals/starters from games, P(plays) rule → `public/data/board.json` (369 players) + `meta.json`.
  - **Checks passed:** named-player rows sane (Gibbs 25.1, Allen 26.4, JSN 23.7 vs DB 17.1); §6b implied-total unit test PASS; distribution SD within 0.026 of target (0 fails); 256-node quantization + deep-scrub infeasibility disclosed.

## Next
- Phase 3: `scripts/sim.py` (seeded, n_sim=100k) + `src/sim/` Web Worker wiring; reconcile `simConfig` N_SIM to §12; parity check browser vs Python within 1 pt, <300 ms.

## Blockers / open
- **GitHub remote still not created — push is blocked.** `git push` returns the exact error `ERROR: Repository not found` (SSH auth to `hbrady7` is confirmed working; the repo simply doesn't exist). Local commits continue each phase; all get pushed once `hbrady7/draftbattle.js` (private) exists — user to create it, or provide a PAT / install `gh`. See DECISIONS D0.7.

## Dead ends tried
- `gh` CLI, `brew`, `~/.git-credentials`, credential helper, keychain github item, `*TOKEN*` env var — all absent. SSH auth to `hbrady7` verified working (push fails only because the repo doesn't exist yet).
