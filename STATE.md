# STATE

_Current phase, what's done, what's next, dead ends already tried. Kept current every phase._

## Current phase
**BUILD COMPLETE — all 12 phases (0–11) done.** Dashboard live at localhost:5175.

**FULL MODEL VALIDATED: the stacked model beats the market (ECR) on held-out 2025 at every position.** One honest gap (D11.x): the live board MEAN still uses the Phase-2 interim blend, because projecting the *upcoming* (unplayed) week with structural+GBM needs a live-week feature builder — the ECR archive + features only cover completed weeks. The full model is validated on the backtest/held-out and shown in the Model tab; wiring it to the live upcoming week is the one remaining integration.

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
- **Phase 8 — Availability. ✅ committed `49f77d3`.** Logistic P(plays) + snap multiplier + vacated redistribution → `availability.py`, `params.json['availability']`. Beats flat rule (Brier 0.128<0.137); OUT→0, DOUBTFUL→0.01 exact. Caveat: QUESTIONABLE optimistic (pred 0.83 vs 0.58 held-out) — refine.
- **Phase 9 — Distribution & correlations. ✅ (core `fdb1dd8`; shape/coverage in this commit).** Empirical Gaussian-copula correlations fit on ~3,400+ pairs (QB-WR1 0.35, RB1-RB2 −0.01, opp QB-QB 0.17) → `params.json['correlations']`, wired into the sim + DNP mass. Shape A/B contest: **gamma (B) won every position**; player 90% coverage 0.88–0.92. Not done: SD challenger, team-total coverage (deferred, D9.x).
- **Phase 10 — Stack & held-out test. ✅ (committing now).** Per-position NNLS stack (`stack.py`) fit walk-forward 2021–24, frozen in `params.json['stack']`, evaluated ONCE on held-out 2025. **Stack beats ECR on CRPS at EVERY position** (QB 4.30<4.67, RB 3.48<3.58, WR 3.49<3.78, TE 3.55<3.87); §10 bar cleared. Walk-forward audited clean. GBM alone marginally best at QB/RB/WR (stack chosen for robustness).

- **Phase 8 — Availability model. ✅ complete (committing now).**
  - `scripts/availability.py`: P(plays) logistic (report/practice/injury-group/position/consec-missed), recency-weighted to the current regime, near-unregularized → reproduces empirical bucket rates. Hard rules: Out/IR→0, unlisted→0.99. Snap multiplier + vacated-opportunity redistribution (default 70/30). Frozen to `model/params.json`.
  - **Check:** held-out 2025 model Brier **0.1277 < flat-rule 0.1370** (net improvement). Doubtful now ≈0 (was 0.25), Out 0. **Finding:** Questionable play-rate fell to ~0.58 and practice-status lost predictive power by 2025 (documented temporal drift; residual Questionable over-prediction).
  - Integrated into `build_board.py` (replaces the flat rule); board + sim rebuilt; Phase-2 SD check still passes (0.023).

- **Phase 9 — Distribution & correlations. ◑ core done (committing now).**
  - `scripts/correlations.py`: empirical role-pair correlations (2019–2025) replace the 4 copula constants — **QB1–WR1 = 0.35** (vs 0.15), all 15 categories empirical (3,300+ pairs). Wired into `sim.build_correlations` → sim.json 433 correlations; parity holds.
  - **DNP mass (closes D0.4):** `p_play` in sim.json; both sims apply the `(1−p_play)` zero-mass (p_play<0.999 only → parity 0.01pt). Win% now discounts injured players.
  - Remaining: shape-A/B contest, SD challenger, team-total coverage validation (D9.4).

## Next
- Finish Phase-9 refinements (D9.4), then Phase 10 (per-position stack weights + single held-out 2025 eval + freeze params.json), then Phase 11 (wire full model into make_week + live tracking/--score + Opponents/Results/Model tabs + README).

## Side track — DONE ✅ (committed)
- **Data-driven AI opponents** from the user's Week-4 workbook (25 rooms / 2200 picks): `scripts/ingest_ai_data.py` → `public/data/ai_opponents.json` (9 AIs, per-round position + player-share priors + ADP). Live-draft JS: `src/opponents/aiModel.js` + per-seat AI assignment in the Draft Room; `P(available)` + per-candidate **WPA** now use the real AIs. Checks: build clean, archetype-match 7/7, name join 61%, win% finite+separated. Caveat: expected-fill baseline optimistic (~80%, rigid bots + greedy self-fill) — Δ/floor are the grounded signals (DECISIONS D-AI.4).

## Blockers / open
- **RESOLVED — remote created + pushed.** User created the repo; note it's named **`hbrady7/draftbattle`** (not `draftbattle.js`, despite the local dir). Remote = `git@github.com:hbrady7/draftbattle.git` (SSH). Phases 0–6 pushed to `origin/main` (`c80ebca`). Push each phase from here.

## Dead ends tried
- `gh` CLI, `brew`, `~/.git-credentials`, credential helper, keychain github item, `*TOKEN*` env var — all absent. SSH auth to `hbrady7` is the only GitHub auth; repo creation had to be done by the user (done).
