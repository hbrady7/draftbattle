# STATE

_Current phase, what's done, what's next, dead ends already tried. Kept current every phase._

## Current phase
**Phase 8 — Availability model.** Next. Fit the logistic P(plays) + E[snap share|plays] on 2019–2025 (report_status/practice_status/injury type/games-missed) and the vacated-opportunity redistribution rates. Replaces the Phase-2 simple rule.

**BASELINE READY for Week 4 at localhost:5175.** (Live draft now has data-driven AI-opponent WPA — see AI-opponent work.)

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

- **Phase 7 — Mean model. ✅ complete (committing now).**
  - `scripts/features.py` (game env, shares, efficiency, opponent adj — walk-forward-safe), `model_structural.py` (6b–6e), `model_gbm.py` (HistGradientBoostingRegressor, LightGBM libomp unavailable). Integrated into backtest.
  - **Result (post-leak-fix, weeks [3,7,11,15], n=3116): structural CRPS 3.661, gbm 3.672 beat ecr_implied 3.881 overall AND at every position; cov90 0.895/0.889 vs 0.845.** Edge is marginal (~0.2) and comes from the core's leak-free re-use of ECR + trailing; **no ablated feature group ships** (vegas/weather/participation/efficiency/opponent — all 95% CIs include 0).
  - Adversarial leakage audit: clean except the §5 Thursday-kickoff ECR drop wasn't applied → FIXED; re-run confirms the result holds.

## Next
- Phase 8: logistic availability model + vacated-opportunity redistribution → replaces the Phase-2 P(plays) rule; feeds the distribution's DNP mass.

## Side track — DONE ✅ (committed)
- **Data-driven AI opponents** from the user's Week-4 workbook (25 rooms / 2200 picks): `scripts/ingest_ai_data.py` → `public/data/ai_opponents.json` (9 AIs, per-round position + player-share priors + ADP). Live-draft JS: `src/opponents/aiModel.js` + per-seat AI assignment in the Draft Room; `P(available)` + per-candidate **WPA** now use the real AIs. Checks: build clean, archetype-match 7/7, name join 61%, win% finite+separated. Caveat: expected-fill baseline optimistic (~80%, rigid bots + greedy self-fill) — Δ/floor are the grounded signals (DECISIONS D-AI.4).

## Blockers / open
- **RESOLVED — remote created + pushed.** User created the repo; note it's named **`hbrady7/draftbattle`** (not `draftbattle.js`, despite the local dir). Remote = `git@github.com:hbrady7/draftbattle.git` (SSH). Phases 0–6 pushed to `origin/main` (`c80ebca`). Push each phase from here.

## Dead ends tried
- `gh` CLI, `brew`, `~/.git-credentials`, credential helper, keychain github item, `*TOKEN*` env var — all absent. SSH auth to `hbrady7` is the only GitHub auth; repo creation had to be done by the user (done).
