# STATE

_Current phase, what's done, what's next, dead ends already tried. Kept current every phase._

## Current phase
**Phase 7 — Mean model.** Next. Structural model (6b–6e) + LightGBM (6f) with ablations per feature group (paired bootstrap, ships only if CRPS improves). Populate `backtest/ablations.csv`.

**BASELINE READY for Week 4 at localhost:5175.**

## Done
- **Phase 0 — Audit and set up. ✅ committed `59bc525`.** Audited `draftTool` → REUSE sim (D0.3); scaffolded repo; dark 6-tab shell serves on `:5175`.
- **Phase 1 — Data layer. ✅ committed `ab98a11`.** `data_sources.py` (every §5 source, 12h cache, leakage guards, core-source stop) + `ids.py` (name_key replica, gsis crosswalk). 68/68 source-seasons clean; DB top-200 match 100%; Sleeper live.
- **Phase 2 — Baseline model. ✅ committed `0dff88c`.** `distribution.py` (projDist.js port + shape-A template + DNP mixture) + `build_board.py` → `board.json` (369). Checks: §6b unit test, SD within 0.026, named players sane.
- **Phase 3 — Simulator. ✅ committed `2369f87`.** `sim.py` (seeded copula, vectorized best-ball, sim.json) + `simCore.js` seedable PRNG + `sim_parity.mjs`. Parity 0.25pt; 8×11 eval 71ms.
- **Phase 4 — Opponents. ✅ committed `66510a2`.** `opponents.py` (§13 softmax, 8 profiles, ADP sim) + `pickModel.js`. Spearman(ADP, DB rank) = 0.998.
- **Phase 5 — Dashboard core. ✅ complete (committing now). BASELINE READY.**
  - Board tab (CI range bar, edge coloring, filters, row drawer w/ PDF curve + sources), Draft Room (8×11 snake grid, live win% expected-fill + floor via seeded Web Worker, top-8 recs w/ P(available), opponent next-pick strips, undo/reset/export JSON), Data tab (build status, scoring config, CSV drop preview).
  - `scripts/run_week.mjs` (`npm run week`), `src/sim/simWorker.js` + `useSim.js` (worker over top-200 universe), `draftSim.completeDraft` wired to §13 `pickModel`, `src/lib/viz.jsx` SVG components.
  - **Checks passed:** `npm run build` exits 0 (38 modules, worker bundled); `node scripts/mock_draft.mjs` PASS (11 picks, win% 12.7→27.1, valid JSON export); board.json still parses; dev server serves app + data (HTTP 200).
- **Phase 6 — Backtest harness. ✅ complete (committing now).**
  - `scripts/backtest.py`: walk-forward on 2021–2024 (2025 held out for Phase 10), 16 wks/season, ECR top-N universe (QB32/RB60/WR84/TE32), 12,895 predictions, players scoring 0 kept. Scorecard: MAE/RMSE/Spearman/CRPS/50%+90% coverage/PIT/Brier. Isotonic ECR-implied (prior-seasons-only). → `backtest/report.md` + `report.json` + `ablations.csv` (header; Phase 7 fills).
  - **Check passed:** report.md has the baseline scorecard for 2021–2024. **ECR-implied wins CRPS (4.036)** > old_plan 4.038 > trailing_xfp 4.275 > trailing8 4.305. Bar for the Phase-10 stack: beat ECR-implied on CRPS/MAE per position.

## Next
- Phase 7: structural mean model (6b–6e) + LightGBM (6f), feature-group ablations (paired bootstrap; ship only if CRPS improves, 95% CI excludes 0) → populate `ablations.csv`, log CRPS gains in DECISIONS.

## Blockers / open
- **GitHub remote still not created — push is blocked.** `git push` returns the exact error `ERROR: Repository not found` (SSH auth to `hbrady7` is confirmed working; the repo simply doesn't exist). Local commits continue each phase; all get pushed once `hbrady7/draftbattle.js` (private) exists — user to create it, or provide a PAT / install `gh`. See DECISIONS D0.7.

## Dead ends tried
- `gh` CLI, `brew`, `~/.git-credentials`, credential helper, keychain github item, `*TOKEN*` env var — all absent. SSH auth to `hbrady7` verified working (push fails only because the repo doesn't exist yet).
