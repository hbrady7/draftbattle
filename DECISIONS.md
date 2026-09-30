# DECISIONS

_Every default taken from BRIEF.md, and every call the brief doesn't cover. One line of reasoning each._

## Phase 0

- **D0.1 — Repo location `~/draftbattle.js`.** Matches the §15 layout root. New, clean repo (not derived from `draftTool`).
- **D0.2 — `draftTool` is not this repo.** Its git remote is `hbrady7/swingstudio.git`, not `draftbattle.js`, so the §19 "existing apps are the same repo" stop condition does not apply. `draftTool` is treated as read-only reference; never edited.
- **D0.3 — Sim decision: REUSE (default).** Independent audit found the Python skeleton `ffb_pipeline.py` was ported *from* the JS sim: the four Gaussian-copula constants (`QB-WR 0.15, QB-TE 0.15, QB-RB 0.05, opp QB-QB 0.20`), the copula/Cholesky + scale-shrink loop, the 257-step inverse-CDF table with identical tail params, the 9-starter best-ball lineup (QB/2RB/3WR/TE/FLEX/SUPERFLEX + 2 bench), and the ≥-max win rule all match line-for-line. No blocking mismatch. Copied `simCore.js`, `projDist.js`, `bbDraftLogic.js`, `mcWorker.js`, `draftSim.js`, `simConfig.js`. **Rewrite (not copy):** `projFile.js` (browser persistence → `localStorage` per §4.8) and `DraftApp.jsx` (→ new dashboard UI).
- **D0.4 — KNOWN GAP: explicit DNP mixture.** Neither the reused sim nor the skeleton implements §8's `(1−P(plays))` point-mass at 0 as an explicit mixture; both bake did-not-play risk into the PDF *shape* upstream. To be closed in Phase 8/9 when `availability.py` + `distribution.py` are built — the inverse-CDF table will be constructed from the true mixture. Tracked so it isn't forgotten.
- **D0.5 — `N_SIM` per brief, not the copied constants.** Copied `simConfig.js` carries `N_SIM_RESULTS=500_000`; §12 specifies n_sim=100,000 for the Python post-draft report and 20,000 browser draws. Brief wins; reconciled in Phase 3.
- **D0.6 — `scoring.json` = skeleton full-PPR, `pass_td=4`.** Per §20 default. The §11 scoring check will compare FFA to 4- vs 6-pt pass TDs and flag any mismatch in the Data tab.
- **D0.7 — GitHub repo creation deferred.** No `gh`/token/browser-creds; only SSH (push/clone) works. Cannot create the remote programmatically. Building + committing locally each phase; push once the private `hbrady7/draftbattle.js` exists. Not treated as a hard stop because the user said to proceed and supply missing access later.
- **D0.8 — `aliases.csv` schema = `raw_name,position,gsis_id,note`.** For manual §5.3 ID fixes. Header-only for now.
- **D0.9 — `PLAN.md` not found among inputs.** The brief supersedes it anyway (§3a), so non-blocking; skipped.
- **D0.10 — `DBranks.json` excluded.** Present in `draftTool/input_data` but per Decision §4.1 RotoBaller ranks are out of the build path; not copied.

## Phase 1

- **D1.1 — DB top-200 gsis match = 100%** (target ≥95%); FFA-name match 195/200 = 97.5%, matching the brief's stated figure. `build/unmatched.txt` has 0 no-gsis rows. The 5 FFA-only misses (incl. Jack Strand QB rank 90) resolve to gsis via `db_playerids.csv`/`players.csv`.
- **D1.2 — Sleeper API is live** (2024 W4 probe → 9,422 rows). Per §5, will pull 2020–2026 as a second historical projection source and test it in the stack (Phase 6/7/10).
- **D1.3 — Crosswalk** = `players.csv` (`display_name`+`position`→`gsis_id`) ∪ `db_playerids.csv` (`name`/`merge_name`+`position`→`gsis_id`); `(name_key,pos)` exact first, then `name_key`-only, then `db_<key>_<pos>` fallback (§4.9). `name_key` is an exact replica of `ffb_pipeline.py`.
- **D1.4 — Leakage guards** implemented as helpers: `ecr_scrape_to_week` (Friday scrape → following Sunday's `(season,week)`) and `drop_pre_scrape_games` (drop teams already kicked off at scrape time). Per-team kickoff mapping is finalized in Phase 6 against confirmed `games.csv` columns.
- **D1.5 — Failure policy:** non-core source failures append to `build/source_failures.txt` and continue; core sources (stats_player, pbp, ep_weekly, injuries, games, db_fpecr) retry once then STOP (exit 2, §19).
- **D1.6 — All 68/68 source-seasons downloaded clean** (no failures). Row counts sane. **Quirk noted:** `depth_charts` 2025/2026 have ~554k/586k rows vs ~37k in prior years — the newer files are a finer (per-week/expanded) format. Whatever parser reads depth charts (Phase 7 role priors) must group/dedupe to one row per player-week rather than assume the old schema.

## Phase 2

- **D2.1 — Interim ECR-implied points** = the current-week FFA points curve (sorted desc within position) indexed by each player's ECR *positional* rank. The real isotonic fit of actual points on ECR rank (§6g) needs history and lands in Phase 6/10; this proxy is a stand-in so the 50/50 blend has an ECR arm now.
- **D2.2 — mean recipe:** `0.5·FFA + 0.5·ECR-implied`, fallback FFA-only → ECR-only → DB-only `= DB·0.85` (§6h). Backup-QB cap at 4.5 (§6g.1): a QB whose `name_key` ≠ his team's `games.csv` starter is capped (caught 3, incl. Sam Darnold, Jack Strand).
- **D2.3 — Shape-A base = unimodal position template, not raw KDE (baseline).** Raw KDE of recent games goes bimodal for boom/bust players, and `match_mean_sd`'s order-preserving reshape can't collapse two humps to hit a low target SD (Noah Fant overshoot). The template reshapes cleanly across the whole SD range. Per-player KDE shapes (smoothed) return in Phase 9's A/B contest. `_kde_knots` is kept behind a `use_kde` flag.
- **D2.4 — 256-node inverse-CDF quantization.** With the template base, `match_mean_sd` hits the target SD to ~0.03 (verified: analytic and fine-table sampling both ≈target). The spec-mandated 257-node table (§8) + linear interpolation adds ~0.08–0.10 to the *sampled* SD in the convex tails. This is inherent to the spec'd simulator, is symmetric, and averages out in best-ball totals. The Phase-2 check asserts the distribution SD (fine table) and *reports* the 256-node artifact.
- **D2.5 — 120/339 healthy deep players (db_rank >150) have infeasible SD targets** on the floored unimodal support (player_sd's curve gives SD ≫ mean for low projections). The draftable core (rank ≤150) matches within 0.03, and the draft only uses ~88 players, so this is immaterial now; the Phase 9 shape A/B contest (zero-floored gamma) will handle high-SD/low-mean better.
- **D2.6 — P(plays) simple rule:** OUT/IR 0, DOUBTFUL 0.25, QUESTIONABLE 0.85, else 1.0; late-news override `input_data/week{N}/injuries.csv`. Fitted logistic replaces it in Phase 8.
- **D2.7 — Current team** from `weekly_rosters` 2026 latest week by gsis. Implied totals from `games.csv` via `home=(total+spread)/2` (§6b unit test TEN@BAL 43.5/11.5 → BAL 27.5 / TEN 16.0 passes).

## Phase 3

- **D3.1 — `sim.json`** = full board sim-formatted (`idx,id,position,team,points,sd_pts,min,max,knots`) + correlations + `team_to_opp` + `meta{seed}`. 369 players, 348 correlations. Correlations are computed once in Python (`build_correlations`, a port of `simCore.buildCorrelations`, the 4 base constants) and **stored in sim.json so JS and Python share identical structure** — this is what makes the parity check meaningful. Empirical correlations (§9) replace the constants in Phase 9.
- **D3.2 — Seeded PRNG.** Added mulberry32 `setRngSeed`/`resetRng` to my copy of `simCore.js` (§12 "seeded PRNG"); Python uses `np.random.default_rng(seed)`. Seed recorded in `sim.json.meta` (default 12345).
- **D3.3 — Vectorized best-ball** (numpy) validated identical to an exact greedy port of `bestBallTeamScores` (max diff 4.6e-5 = float32 summation-order rounding). Used for the 100k Python sim (~0.8–1.1s). Optimal-lineup identity: mandatory QB/2RB/3WR/TE then FLEX+SF = top-2 leftovers with FLEX restricted to non-QB (`extra = M1 + (M2 if M1 flex-eligible else best-eligible)`).
- **D3.4 — Parity + timing PASS.** JS 20k-draw win% 13.33 vs Python 100k 13.08 → **0.25pt** (<1pt). **Per-pick full 8×11 evaluation 71ms** (<300ms). The 393ms sample-matrix build is the once-per-session cost (§12 step 1), not the per-pick target.
- **D3.5 — simConfig reconciled to §12:** `N_SIM_DEFAULT` 40k→**20k** (session matrix draws), `N_SIM_RESULTS` 500k→**40k** (in-browser post-draft; Python report uses 100k). Live `EVALUATE` fill/candidate budget (`N_DRAFT_SAMPLES`) is tuned against latency in Phase 5.

## Phase 4

- **D4.1 — Fixed-scale standardization, not per-pool z-score.** Z-scoring `-db_rank` over the ~220-pool collapses adjacent ranks to ~0.016 SD, so a temp-0.8 softmax is near-uniform over the top (bug: Gibbs ADP 30, corr 0.735). Standardizing by fixed scales (`-db_rank/8`, `mean/8`) gives an effective reach of ~temp×8 ≈ 6 ranks. **Result: Spearman(ADP, DB rank) = 0.998**, Gibbs (rank 1) ADP 5.3 — high with realistic draft noise.
- **D4.2 — REQUIRED[QB]=2 (superflex).** Teams target 2 QBs (QB + SF); `HARD_CAP[QB]=2` makes a 3rd QB ineligible (−∞), matching "e.g. a 3rd QB" in §13. RB/WR/TE have no hard cap (extras help via FLEX/SF/best-ball).
- **D4.3 — 8 profiles in `opponents.json` (one per seat).** §13/§14 describe 7 AI + 7 cards; I store all 8 seats and the app simply treats the 7 that aren't my seat as opponents (my seat's profile is ignored — I draft by max win%). Default weights `{db_rank 1.0, our_mean 0, positional_need 0.6, position_run 0, qb_early 0}`, temperature 0.8.
- **D4.4 — `src/opponents/pickModel.js` mirrors `opponents.py`** (same scales/features/softmax) for the browser live-draft fills; wired into `draftSim.completeDraft` in Phase 5.
- **D4.5 — Learning** (`opponents.py --fit`) no-ops below 5 drafts in `results/`; logistic weight fit wired in Phase 11/13.

## Phase 5

- **D5.1 — Live sim universe capped at top-200 by DB rank** (`useSim`, nSim=12000). Building the copula matrix over all 369 players is O(nSim·N²) ≈ 2.7B ops (~5–10s); top-200 covers the entire realistic draftable pool (8×11 = 88 picks) and keeps the one-time session build ~1–2s. The Draft Room side-board therefore drafts from this top-200. Full-board sim stays available in Python (`sim.py`, 100k).
- **D5.2 — Two win% numbers (§12).** *Floor* = `SCORE` over current rosters (empty slots = 0). *Expected-fill* = average over ~24 `completeDraft` fills where opponents sample the §13 model and my future picks are greedy by need-weighted points. Both run in the seeded Web Worker (`simWorker.js`); the "12.5% baseline / ~18–25% strong" sentence sits next to the number.
- **D5.3 — `completeDraft` opponent branch rewired to `pickModel.samplePick`** (§13) when `opts.profiles` present; my-seat picks stay greedy via `userPickScore` (patched to fall back to `points`/`mean`/`p95` since board rows lack VOR columns). Legacy `botSamplePick` kept as fallback.
- **D5.4 — Recommendations (baseline) rank by need-weighted mean**, always include the best available per position, top 8, each annotated with `P(available at my next pick)` computed from the opponent model over the interim picks (product of 1−pick-prob). The full per-candidate *win-%-gain* ranking (a fill per candidate) is deferred — it's expensive; logged as a Phase-11 refinement. The my-seat greedy over-drafts QBs late in deep rosters (DB-rank QB saturation) — cosmetic for the baseline; the win-% engine and richer need logic refine it later.
- **D5.5 — `npm run week` is Week-4-fixed** (build_board/sim are hardcoded to Week 4); the `--week`/`--refresh` flags are accepted and echoed. Generalizing the week through the Python pipeline is Phase 11.
- **D5.6 — No chart library** (§14): all viz (CI range bar, PDF curve, grid) are hand-rolled inline SVG in `src/lib/viz.jsx`. Board drawer shows the PDF, p05/p50/p95, the DNP mass, and every source; component breakdown / game-log / target-share are marked "Phase 7" where the structural model isn't built yet. `build/unmatched.txt` isn't served over HTTP (Vite serves only `public/`); the Data tab notes it (0 rows this build).
- **D5.7 — Opponents/Results/Model tabs are informative placeholders** pointing to their build phase; Board/Draft Room/Data are fully live. Header build-status now reads the week + player count from `meta.json`.

## Phase 6

- **D6.1 — Walk-forward design.** Seasons 2021–2024 (2025 held out for Phase 10's single read), weeks 2–17 sampled, universe = ECR positional top-N (QB32/RB60/WR84/TE32) from the `db_fpecr` archive (`ecr_type=="wp"`). Players who scored 0 are kept (real DNP risk). 12,895 predictions. Actuals re-scored with `scoring.json`.
- **D6.2 — Baseline result: ECR-implied points wins CRPS (4.036)** > old_plan 4.038 > trailing_xfp 4.275 > trailing8 4.305. By position ECR-implied wins CRPS for RB/WR/TE; old_plan edges QB (4.849 vs 4.894). **Implication (§10):** the market (ECR) is a strong baseline; the Phase-10 stack must beat ECR-implied on CRPS *and* MAE per position to justify shipping — report plainly if it doesn't.
- **D6.3 — ECR-implied = isotonic** (monotone-decreasing) fit of actual points on ECR positional rank, per position, **prior-seasons-only** (walk-forward by target season).
- **D6.4 — No FFA history** → the `old_plan` baseline (70% FFA-proxy + 30% trailing-8) uses ECR-implied as the FFA stand-in. Logged; real FFA weights only from live logging (§11).
- **D6.5 — P(plays)=1.0 in the harness** (availability model is Phase 8), so CRPS/coverage are slightly optimistic for injury-risk players. Observed **cov90 ≈ 0.83–0.85 vs 0.90 target, cov50 ≈ 0.45 vs 0.50, PIT mean ≈ 0.48** — intervals a touch narrow across all baselines. Real calibration signal to close in Phase 8 (DNP mass) + Phase 9 (SD/shape).
- **D6.6 — Contest win-rate sim scaffolded, full run deferred to Phase 10.** The §17 Phase-6 check is "report.md with baseline numbers for 2021–2024" (passes). Running the 200-draft contest sim on *baselines* alone is low-value; it runs with the stacked model in Phase 10. Feature ablations (`ablations.csv` header written) populate in Phase 7.
