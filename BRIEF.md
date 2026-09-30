# Draft Battle Dashboard: Full Brief for Claude Code

Owner: Hollis Brady (GitHub `hbrady7`)
Repo: `hbrady7/draftbattle.js` (private, version control only)
Runs at: `localhost:5175`
Written: 2026-09-30, NFL Week 4 of the 2026 season. Week 4 opens Thursday Oct 1 (PIT @ CLE).

Read this whole file before touching anything. It covers the goal, the contest, the data, the model, how the model gets tested, the dashboard, and the build order. When something is unknown, it gives a default: use it, log it in `DECISIONS.md`, and keep going.

---

## 0. How to run this session

- **Run fully autonomously through every phase.** Don't pause for confirmation between phases. The only exceptions are the stop conditions in §19.
- **Commit and push to GitHub at the end of every phase.** Every phase in §17 ends with an explicit commit + push step. Never batch phases into one commit.
- **Git identity:** `hollisbrady2004@gmail.com` / `hbrady7`.
- **No `Co-Authored-By` trailers** in commit messages. This overrides any default attribution behavior.
- **Keep two files current in the repo root.**
  - `STATE.md`: current phase, what's done, what's next, and dead ends already tried.
  - `DECISIONS.md`: every default you took from this brief and every call you made that it doesn't cover.
- **Checks must actually run.** Every phase ends with a check that runs and prints a result. "Should work" doesn't count.
- **Order matters.** Phases 0–5 get a working baseline dashboard up in time for this week's draft. Phases 6–11 build the full model on top of it. Don't start the full model until the baseline dashboard runs.

---

## 1. What I'm trying to do

I play **Draft Battle** (draftbattle.com) every week. It's an 8-team best-ball draft against **7 AI drafters**. The AIs almost certainly draft off Draft Battle's own ranks and projections, and I think those are bad.

**The goal is the most accurate week-to-week fantasy projection model I can build, plus a local dashboard that turns it into draft decisions.** The dashboard gives me three things:

1. A **90% interval for every player's weekly points** from my own model.
2. My **team's projected weekly points**, with a 90% interval, both during the draft and after it.
3. My **chance of winning the contest**, live during the draft and after it, plus pick recommendations that maximize it.

"Most accurate" has to be measured, not claimed. §10 defines the scorecard. Every model piece has to earn its place by improving walk-forward results on past seasons, and the live scorecard keeps checking it every week.

Later I'll supply the 7 AI opponents' draft strategies. Don't wait on them; ship with default opponent profiles (§13).

---

## 2. The contest

| Item | Value | Status |
|---|---|---|
| Teams | 8 (me + 7 AI) | Assumed. Make it a config constant. |
| Draft | Snake, 11 rounds. I enter my seat (1–8). | Assumed |
| Format | Best ball: the lineup is set automatically for max points after games finish | Confirmed from a DB screenshot |
| Starters (9) | QB, RB, RB, WR, WR, WR, TE, FLEX (RB/WR/TE), SUPERFLEX (QB/RB/WR/TE) | Confirmed. The screenshot lineup shows 2 QBs, 2 RBs, 4 WRs, 1 TE. |
| Bench (2) | "2 lowest scoring players" | Confirmed |
| Slate | Full week, Thursday through Monday | Confirmed (screenshot shows SUN and MON games) |
| Win | Highest best-ball total of the 8 teams; ties count as wins | Assumed |
| Scoring | Full PPR: 0.05/pass yd, 4/pass TD, −1/INT, 0.1/rush yd, 6/rush TD, 0.1/rec yd, 6/rec TD, 1/rec, −1/fumble lost, 2/two-pt conversion | **Unconfirmed.** Put it in one config object (`model/scoring.json`), and use it everywhere actual and projected points get computed. |

Positions are QB/RB/WR/TE only. There are no kickers and no defenses.

---

## 3. Existing assets

### 3a. Files I'm providing (copy into the repo in Phase 0)

| File | What it is | Repo location |
|---|---|---|
| `ffb_pipeline.py` | My pipeline skeleton: board build, nflverse priors, PDF generation (9-knot PDFs, KDE/template shapes, `tilt_to_mean`), and the post-draft Monte Carlo (Gaussian copula, 257-step inverse-CDF tables with thin tails, best-ball lineup). | `scripts/legacy/ffb_pipeline.py` (reference) and pieces reused in `scripts/` |
| `player_sd.py` | My backtested weekly SD model: last 8 games, recency-weighted, scaled to the projection, blended with a position curve (2019–2026 QLIKE backtest). Also `match_mean_sd()`, which reshapes a PDF to hit a target mean and SD. | `scripts/player_sd.py` |
| `ffa.csv` | Fantasy Football Analytics Week 4 projections. 336 rows: 72 QB, 88 RB, 88 WR, 88 TE. `sd_pts` is disagreement between sources, **not** game-to-game SD. | `input_data/week4/ffa.csv` |
| `draft_battle_week4_projections.csv` | DB's board: `Rank, Name, Position, Projected Points`. 369 rows: 154 WR, 96 TE, 86 RB, 33 QB. **No team column.** | `input_data/week4/draft_battle_week4_projections.csv` |
| `stats_player_week_2025.csv`, `_2026.csv` | nflverse box scores (2026 has weeks 1–3) | `data/raw/stats_player/` |
| `PLAN.md` | The earlier plan. This brief supersedes it wherever they differ. | repo root, for reference |

If a file isn't in the repo when you start, look in the folder I launched you from. If it isn't there either, stop (§19).

### 3b. Existing local apps (audit in Phase 0, don't edit in place)

- **`localhost:5174`, "Best Ball Projections"**, has tabs DRAFT ASSISTANT / PORTFOLIO / PDF BOARD.
  - The Draft Assistant has an available-players table with columns TOP1%, COUNT, PLAYER, PROJ, P10, RANK, HEDGE, TOP1%, RISK ≤25%, and a DRAFT button.
  - It has a rosters panel with My Team / Team 2 / …, each with 11 slots (QB, RB, RB, WR, WR, WR, TE, SUPERFLEX, FLEX, BENCH, BENCH).
  - It runs an in-browser Monte Carlo ("MC 5345ms").
- **`localhost:5173`**: a PDF Board game view.
  - Team pass/rush offense and defense priors vs. league, "top PPR vs [team] recently", per-player PDF editors with range sliders, "16 slates", and Export/Import JSON.
- These likely contain `simCore.js` and `projDist.js`. `ffb_pipeline.py` mirrors their constants.

---

## 4. Decisions already made (don't re-argue these)

1. **Player pool = DB's CSV.** It's what's actually draftable. RotoBaller `DBranks.json` isn't available; remove it from the build path.
2. **DB's projection is displayed and logged, but gets no weight in the mean** until the live scorecard shows it adds accuracy (§11).
3. **DB rank drives the AI opponent model** (§13).
4. **Every model component is chosen by walk-forward backtest** (§10). If the backtest says a feature doesn't help, it doesn't ship, even if it's in this brief.
5. **`player_sd.py` is the SD baseline.** Its settings came from a 2019–2026 backtest. A challenger replaces it only if it beats it on the §10 scorecard.
6. **90% CI = the 5th–95th percentile of what the simulator actually samples**, including the chance a player doesn't play. It is never mean ± 1.645·SD.
7. **Localhost only.** The Vite dev server runs on `localhost:5175` (5173 and 5174 are taken) with `strictPort: true`. No hosting, no deploy config, no deploy workflow. GitHub is for version control only.
8. **Vite + React frontend, Python for everything else.** No backend server. Data flows as JSON in `public/data/`. Browser state (in-progress draft, opponent edits, sliders) goes in `localStorage`, wrapped in try/catch.
9. **Canonical player ID = nflverse `gsis_id`.** Every file keys on it. For a DB-only player with no gsis match, the ID is `db_<name_key>_<pos>`.

---

## 5. Data layer

All of these sources are free and were confirmed reachable on 2026-09-30.

Cache everything under `data/raw/<source>/<season>.<ext>`.
- Past seasons download once.
- The current season re-downloads if the cache is older than 12 hours.
- `--refresh` forces a re-download.

| Source | URL pattern | Seasons | Used for |
|---|---|---|---|
| Player weekly stats | `github.com/nflverse/nflverse-data/releases/download/stats_player/stats_player_week_{Y}.csv` | 2019–2026 | Actual points (re-scored with our config), targets, carries, air yards, target share, WOPR |
| Play-by-play | `.../pbp/play_by_play_{Y}.csv.gz` | 2019–2026 | Team pace, neutral pass rate, pass rate over expected, dropbacks, red-zone and inside-10 opportunities, end-zone targets, designed QB runs vs. scrambles |
| Participation | `.../pbp_participation/pbp_participation_{Y}.csv` | 2019–2025 (**not 2026**) | Who was on the field for each dropback → route-participation proxy. For 2026, fall back to snap share. |
| Snap counts | `.../snap_counts/snap_counts_{Y}.csv` | 2019–2026 | Offensive snap % (role and usage) |
| Expected fantasy points | `github.com/ffverse/ffopportunity/releases/download/latest-data/ep_weekly_{Y}.csv` | 2019–2026 | Expected receptions, yards, and TDs per player-game from play context. Re-score the component `_exp` columns with our scoring config; don't use their totals. |
| Injuries | `.../injuries/injuries_{Y}.csv` | 2019–2026 | `report_status` (Out/Doubtful/Questionable), `practice_status`, injury type |
| Schedules and lines | `raw.githubusercontent.com/nflverse/nfldata/master/data/games.csv` | all | `spread_line`, `total_line`, roof, surface, temp, wind, rest days, **projected starting QBs** (`away_qb_name`, `home_qb_name`), kickoff times |
| Depth charts | `.../depth_charts/depth_charts_{Y}.csv` | 2019–2026 | Current role and slot (WR1/WR2, RB1, TE1) |
| Players | `.../players/players.csv` | — | gsis ID, names, position, draft round/pick, birth date |
| Weekly rosters | `.../weekly_rosters/roster_weekly_{Y}.csv` | 2019–2026 | Team on each week (trades, signings) |
| Historical consensus ranks | `raw.githubusercontent.com/dynastyprocess/data/master/files/db_fpecr.parquet` | 2020–2026, ~16 weeks/season | FantasyPros weekly positional expert rankings (`ecr_type == "wp"`) with `ecr, sd, best, worst`. **This is the only free archive of what "the market" projected each week**, so it's the backtest stand-in for FFA/DB. |
| Current consensus ranks | `raw.githubusercontent.com/dynastyprocess/data/master/files/fp_latest_weekly.csv` | current week | Live ECR input |
| ID crosswalk | `raw.githubusercontent.com/dynastyprocess/data/master/files/db_playerids.csv` | — | gsis ↔ FantasyPros ↔ Sleeper ↔ other IDs |
| FFA weekly CSV | I drop it in `input_data/week{N}/` | from 2026 W4 | Live projection source, logged every week |
| DB weekly CSV | I drop it in `input_data/week{N}/` | from 2026 W4 | Player pool, DB rank/projection, logged every week |
| Sleeper projections (optional) | `api.sleeper.app/projections/nfl/{Y}/{W}?season_type=regular` | historical | Unofficial. Test it in Phase 1; if it responds, pull 2020–2026 as a second historical projection source. If it doesn't, log it and move on. |

**Leakage guards.** The backtest must use only what was knowable before kickoff.
- **ECR archive scrape dates are Fridays.**
  - Map each scrape to the NFL week containing the following Sunday.
  - Drop ECR rows for players whose game kicked off before the scrape timestamp (Thursday games).
- **Injury `report_status`** is the final pre-game report, so it's fine to use.
- **Snap counts, participation, and xFP** for week w can only be used for weeks after w.
- **`spread_line`/`total_line`** are near-closing lines. That's slightly optimistic compared with a Wednesday draft. Accept it and note it in the backtest report.

**Name/ID resolution.**
1. Match on gsis ID through `db_playerids.csv` and `players.csv`.
2. If that fails, fall back to `name_key()` (from `ffb_pipeline.py`: lowercase, strip punctuation and Jr/Sr/II/III/IV/V) plus position.
3. Apply manual fixes from `input_data/aliases.csv`.

Week 4 baseline: 195 of DB's top 200 match FFA by name alone. Only Jack Strand (QB, DB rank 90) is unmatched in DB's top 150. Write every unmatched row to `build/unmatched.txt`.

---

## 6. The projection model: mean

### 6a. Structure

Points are built bottom-up. Everything is fit on 2019–2025 and chosen by the §10 backtest.

```
Game environment  →  Team volume  →  Player share  →  Efficiency  →  Points
(Vegas lines)        (plays, pass    (targets,        (yards, TDs     (scoring
                      rate, TDs)      carries, RZ)     per opportunity) config)
```

Then this "own model" is stacked with market sources (ECR-implied points, FFA, and later DB) using weights the data picks (§6g).

### 6b. Game environment (per team-game)

- **Implied team total.** In nflverse, a positive `spread_line` means the home team is favored.
  - `home_implied = (total_line + spread_line) / 2`
  - `away_implied = (total_line − spread_line) / 2`
  - Unit test: TEN @ BAL, total 43.5, spread 11.5 → BAL 27.5, TEN 16.0.
- **Expected offensive plays.** Regress on the team's neutral-situation seconds per play, the opponent's, and the spread (the favorite runs more late, the underdog passes more). Shrink team pace toward league average with a backtested k.
- **Expected pass rate.** Neutral pass rate over expected (PROE) for the team, shrunk toward league average, plus a spread term and an opponent defense term.
- **Expected offensive TDs.** Regress on implied total, split into pass-TD share vs. rush-TD share by team (shrunk) and red-zone tendency.
- **Weather.** Wind ≥ 15 mph and precipitation lower pass rate and passing efficiency; domes get a small bump. Use `roof`/`wind`/`temp` from `games.csv`. Future games often have NA weather: treat it as neutral and allow a manual override in `input_data/week{N}/weather.csv`. **This is a backtest-gated feature**: keep it only if it helps.
- **If lines are missing** for a game, fall back to team-strength ratings built from each team's last-10-game points for and against, shrunk. Flag it.

### 6c. Team volume → player opportunity

For every player on the team:

- **Route participation** = share of team dropbacks the player was on the field for (from participation data, 2019–2025).
  - 2026 fallback: offensive snap % × the player's historical dropback/snap ratio.
- **Target share** = targets / team pass attempts.
  - Estimate it as an EWMA (half-life chosen by backtest; start the search at 3 games), shrunk toward a role prior.
  - The role prior comes from depth-chart slot plus the previous season's share, and for rookies from draft capital.
  - Use beta-binomial shrinkage: prior strength k is backtested per position.
- **Air-yards share and end-zone target share** feed the efficiency layer (6d).
- **Carry share** of team RB carries, with **inside-10 carry share** modeled separately (goal-line role drives TDs).
- **QB designed-run rate and scramble rate**, each shrunk separately, are what separate rushing QBs.
- **Vacated opportunity.** When a teammate is projected out (§7):
  - redistribute his expected targets and carries to active teammates;
  - use redistribution rates learned from 2019–2025 games where a player with ≥ 15% target share (or ≥ 40% carry share) missed: who absorbed the volume, by position and depth slot.
  - Default until fit: proportional to current share within the same position group, 70% of his targets to WR/TE and 30% to RB.
- **Coherence.** Team targets and carries must sum to team volume. Rescale shares after redistribution.

Expected opportunities = share × team volume. For example, expected targets = target share × expected team pass attempts.

### 6d. Efficiency

- Start from **expected** value per opportunity: ffopportunity's expected catch rate, yards, and TDs per target/carry (driven by depth of target and field position).
- Add a player-specific over- or under-performance term (actual − expected, per opportunity), **shrunk heavily toward 0**. Efficiency is noisy and stabilizes slowly, so the backtest picks the shrinkage k per stat.
- **Opponent adjustment.** Fantasy points allowed over expected by position for the opposing defense, shrunk heavily. It's expected to be small, and it's backtest-gated.

### 6e. Points

Score every component (receptions, receiving yards, receiving TDs, carries, rushing yards, rushing TDs, pass yards, pass TDs, INTs, fumbles lost, 2-pt conversions) with `model/scoring.json`. This gives the **own-model mean**, conditional on the player playing.

### 6f. Challenger: gradient-boosted direct model

Train **LightGBM** (`pip install lightgbm`) to predict league points directly.
- Features: every input above (implied total, spread, pace, PROE, route participation, EWMA shares, xFP trailing means, snap %, depth slot, days of rest, home/away, opponent adjustment, weather, ECR rank, and ECR SD across experts).
- Objective: L2, trained walk-forward.
- It competes with the structural model (6b–6e) in the stack (6g). Whichever is better, or their blend, is chosen by the data.

### 6g. Stacking: the final mean

**Candidate inputs:**
- structural own model
- LightGBM
- **ECR-implied points**
- trailing 8-game mean on the current team
- live only: FFA, DB, and Sleeper if available

**ECR-implied points.** Convert weekly positional ECR rank to points with an isotonic (monotone) fit of actual points on ECR rank, per position, fit on prior seasons only. Also keep ECR's cross-expert `sd` as a feature: high disagreement signals uncertainty.

**Fitting the weights:**
- Non-negative weights that sum to 1, fit by constrained least squares walk-forward, **separately per position**.
- Also test separate weights for weeks 1–4 vs. 5+, since early-season history is thin. Keep the split only if it helps.

**Live bridging.** FFA and DB have no history.
- Until 6 weeks are logged, **FFA takes the ECR-implied points weight**, split 50/50 with current ECR-implied points.
- DB gets weight 0.
- After 6+ logged weeks, refit including FFA and DB as separate inputs, shrunk toward the backtest weights (§11).

**Post-stack adjustments, in order:**
1. **Backup QB.** If he isn't the projected starter in `games.csv`, cap his mean at 4.5.
2. **Availability.** The mean stays conditional on playing. The did-not-play probability enters through the distribution (§8), not by shaving the mean.
3. **Manual overrides.** `input_data/week{N}/overrides.csv` holds `player, mean` or `player, status`. Overrides always win and are flagged in the UI.

### 6h. DB-only players

A DB player with no gsis match and no FFA match:
- mean = DB proj × 0.85, because DB runs hot on players nobody else projects;
- a `DB-only` flag;
- SD from the `player_sd` curve at that mean.

---

## 7. Availability model

- **Fit a logistic model on 2019–2025** for P(plays) and E[snap share | plays] / baseline snap share.
  - Inputs: `report_status`, final `practice_status`, injury type (grouped: soft tissue, lower leg, upper body, concussion, illness, other), position, and games missed in a row.
  - "Plays" means he recorded ≥ 1 offensive snap.
- **Hard rules:**
  - Out or IR → P(plays) = 0.
  - No designation → use the base rate for a healthy player, which is near 1.
- **Late-news override:** `input_data/week{N}/injuries.csv` (`player, status`) sets P(plays) directly: Active = 1, Out = 0.
- **Snap multiplier:** a Questionable player who plays is often limited. Apply the fitted snap multiplier to his opportunity share, not directly to points.
- **Teammate effects** come from the vacated-opportunity step (6c), weighted by each teammate's P(out). Use expected-value redistribution, not all-or-nothing.

---

## 8. Distribution

For each player, the weekly distribution = **(1 − P(plays)) point mass at 0 + P(plays) × conditional distribution.**

**Conditional SD:** `player_sd.py` at the stacked mean (it's the baseline). Challenger: an SD model that adds implied-total and route-participation terms. It ships only if it wins on CRPS.

**Conditional shape.** Two candidates compete on the backtest:
- **A:** the skeleton's 9-knot PDF (KDE of recent games or a position template, role tweaks, `tilt_to_mean`), with `match_mean_sd()` applied (player_sd edit 2).
- **B:** a zero-floored gamma per position, with the skew multiplier fit by minimizing CRPS.

The one with lower walk-forward CRPS wins, per position.

**Simulator table.** Build the 257-step inverse-CDF table (`build_inv_cdf_table`, including thin tails) from the final mixture.
- Quantiles `p05, p25, p50, p75, p95` come off that table, and **`ci90 = [p05, p95]`**.
- **Locked players:** if a player's game has finished (e.g. Thursday night), his distribution is a point mass at his actual league score, pulled from nflverse stats. Wire this to the skeleton's `locked_scores` concept.

---

## 9. Correlations

Replace the skeleton's four constants with **empirical Gaussian-copula correlations** fit on 2019–2025.

**Method:**
1. Compute walk-forward PIT residuals: each player-game's actual score converted to its percentile under our predicted distribution, then to a normal score.
2. Correlate those residuals between player pairs by **role-pair category**. Roles are within-team ranks of projected mean: QB1, RB1, RB2, WR1, WR2, WR3, TE1.

**Categories:**
- **Same team:** QB1–WR1, QB1–WR2, QB1–WR3, QB1–TE1, QB1–RB1, QB1–RB2, WR1–WR2, WR1–TE1, RB1–RB2, RB1–WR1.
  - Expect negatives where players compete for the same volume, e.g. RB1–RB2.
- **Opponents:** QB1–QB1, QB1–opp WR1, WR1–opp WR1, RB1–opp QB1, RB1–opp RB1.

**Additional requirements:**
- Shrink each estimate toward 0 with its standard error.
- Keep the skeleton's constants as a fallback if a category has fewer than 500 pairs.
- Guarantee positive semi-definiteness with the skeleton's scale-down loop, or Higham nearest-correlation if the scale-down drops below 0.8.
- **Validation:** simulated vs. actual distribution of team best-ball totals on held-out 2025 weeks. The 90% coverage of team totals must be within ±3 points of 90%.

---

## 10. Backtest and scorecard (this defines "most accurate")

`scripts/backtest.py` runs a walk-forward: for every season S in 2021–2025 and every week w ≥ 2, fit on everything strictly before (S, w), then predict (S, w).
- Week 1 uses prior-season data with carryover shrinkage.
- **2025 is the final held-out check.** Choose hyperparameters on 2021–2024, then report 2025 once.

**Universe:** per week, players inside ECR's positional top N (QB 32, RB 60, WR 84, TE 32), which mimics a draftable pool. Keep players who didn't play (actual 0) in the universe. That's real risk.

**Scorecard** (by position and overall):

| Metric | Measures | Why it matters here |
|---|---|---|
| MAE, RMSE of mean | Point accuracy | Baseline accuracy |
| Spearman rank correlation within position-week | Ordering | Drafting is about order |
| CRPS | Whole-distribution accuracy | The primary metric for choosing between models |
| 50% and 90% interval coverage | Calibration | The dashboard shows intervals |
| PIT histogram | Calibration shape | Catches skew errors |
| Brier score for P(top-5 at position) and P(≥ 25 pts) | Tails | Winner-take-all contests are won in the tails |
| **Contest win rate** | The actual objective | See below |

**Contest win-rate backtest.** For each held-out week:
1. Simulate 200 drafts. The 7 opponents use the §13 default profile, drafting off ECR rank (the historical stand-in for DB rank). I draft greedily by max win % using the model.
2. Score every roster with **actual** best-ball points.
3. Report my realized win rate against the 12.5% baseline.

A model that improves CRPS but lowers realized win rate needs a look before shipping.

**Baselines to beat:**
- ECR-implied points alone
- trailing 8-game mean
- trailing xFP mean
- the old plan (70% FFA-proxy + 30% trailing mean, with `player_sd`)

The final stack must beat ECR-implied points on CRPS and MAE for every position. If it doesn't beat it at some position, the stack weights will say so. Report it plainly.

**Feature gating:**
- Each feature group gets an ablation: model with and without it.
- It ships only if walk-forward CRPS improves by a **paired bootstrap across weeks** (95% interval of the improvement excludes 0).

Feature groups:
- Vegas environment
- route participation
- vacated opportunity
- efficiency terms
- opponent adjustment
- weather
- availability model
- LightGBM
- each correlation category

**Frozen parameters.** Everything fit is written to `model/params.json`, with the fit window, the metric it won on, and the git commit. The live build reads params; it never refits silently.

**Outputs:**
- `backtest/report.md`: plain-language summary, with every number table-backed
- `backtest/report.json`: consumed by the Model tab
- `backtest/ablations.csv`

---

## 11. Live tracking and weekly refit

Every week, `make_week` writes `logs/week{N}/projections.parquet` (CSV is fine if pyarrow is missing). It holds, per player:
- every source's number
- every model component
- stacked mean, SD, P(plays), quantiles
- DB rank/proj, and the build timestamp

After the games, `python scripts/make_week.py --week N --score`:
1. pulls actual stats from nflverse, re-scored with our config;
2. appends actuals to the log;
3. updates the running live scorecard in `logs/scorecard.json`: our model vs. FFA vs. DB vs. ECR, using the same metrics as §10.

**At 6+ logged weeks:**
- Refit the stack weights including FFA and DB as separate inputs, shrunk toward the backtest weights.
- Refit the calibration check.
- Commit the new `params.json` with a note in `DECISIONS.md`.

**Scoring check (runs every build):** for the top 24 QBs, compare FFA's points to our component projection scored at 4 vs. 6 points per passing TD. Print which one FFA matches better. If FFA looks like it uses different scoring than `scoring.json`, flag it in the Data tab. That mismatch would bias every FFA-weighted mean.

---

## 12. Simulator

**Python (`scripts/sim.py`).**
- Port `project_results` from the skeleton to read `sim.json`, the gsis IDs, and the empirical correlation matrix.
- **Seed the RNG** and record the seed in `meta.json`.
- n_sim = 100,000 for the post-draft report.

**Browser (`src/sim/`, in a Web Worker):**
1. Draw Z (players × 20,000) once per session with a seeded PRNG.
2. Apply the Cholesky factor.
3. Apply Φ, then the player's inverse-CDF table.
4. Compute the best-ball lineup per team per draw: QB, 2 RB, 3 WR, TE; then FLEX = best remaining RB/WR/TE; then SUPERFLEX = best remaining of any position.
5. Win = my total ≥ max of all 8.
- Use Float32Array. Target < 300 ms for a full 8 × 11 evaluation.
- Reuse `simCore.js`/`projDist.js` if the Phase 0 audit says they match.

**Parity check:** browser win % within 1 percentage point of Python on the same saved draft.

**Live-draft win %.** Show two numbers:
- **Expected fill:** complete every roster by sampling picks from the opponent model (§13), with my own future picks greedy by expected points while filling needed slots. Run 200 fills × 100 draws each and average.
- **Current rosters only:** no fill. This is a floor.

**Recommendations.**
- Candidates: the top 15 available by expected win-% contribution, always including the best available at each position.
- For each candidate: win % if taken now, and P(he's still there at my next pick) from the opponent model.
- Show the top 8.

**What good looks like:** the 8-team baseline is **12.5%**, and a strong draft lands around **18–25%**. Show that sentence next to the number.

---

## 13. AI opponent model

- **Files:** `scripts/opponents.py` and `src/opponents/`.
- **One editable profile per AI team:**

```json
{"name": "AI-1", "seat": 1,
 "weights": {"db_rank": 1.0, "our_mean": 0.0, "positional_need": 0.6, "position_run": 0.0, "qb_early": 0.0},
 "temperature": 0.8, "notes": ""}
```

**Pick probability** = softmax over available players of score / temperature. The score is a weighted sum of standardized features:
- negative DB rank
- our mean
- positional need from unfilled required slots (−∞ for a position the team can't use anymore, e.g. a 3rd QB)
- position-run bonus from the share of the last 5 picks at that position
- QB-early bonus

**Default:** all 7 teams draft off DB rank plus positional need, with temperature 0.8. When I give you real strategies, each becomes a weights edit with the text saved in `notes`.

**Check:** simulate 500 drafts, print each player's simulated ADP next to his DB rank for the top 50, and print the rank correlation. It should be high.

**Learning.** Exported drafts log predicted vs. actual picks. Once there are 5+ drafts in `results/`, `opponents.py fit` fits the weights by logistic regression. Build it now; it no-ops below 5 drafts.

---

## 14. Dashboard (`localhost:5175`)

**Design:**
- Dark, and it should look at home next to my existing apps (black/dark green, yellow accent).
- One accent color means "me"; AI teams are muted; position colors appear only as thin left borders.
- Readable at 13-inch laptop width.
- **No chart library.** Use tiny SVG components for PDF curves, range bars, PIT histograms, and calibration plots.

**Tabs:**

1. **Board**
   - Table columns: pos, name, team, opp, implied team total, DB rank, DB proj, our mean, **90% CI range bar with DB proj as a tick**, edge (our − DB, color-scaled), SD, P(plays), flags.
   - Filters: position, hide drafted, DB-only, injured.
   - Clicking a row opens a drawer with:
     - the PDF with p05/p50/p95 and the did-not-play mass shown separately;
     - the mean broken into components (targets × yards/target, TDs, etc.);
     - every source's number side by side (own, LightGBM, ECR-implied, FFA, DB) with stack weights;
     - last-8 game log bars with xFP overlaid;
     - route participation and target-share trend;
     - injury status and practice history;
     - the SD breakdown.
2. **Draft Room**
   - Grid of 8 × 11, snake order, my seat highlighted. I set my seat.
   - Enter picks with fuzzy search or by clicking a player on the side board.
   - Header: live win % (expected fill + current-rosters floor), expected best-ball points with 90% CI, and my rank of 8.
   - Side panel: the top 8 recommendations with win-% gain and P(available at my next pick).
   - Under each opponent: a predicted-next-picks strip.
   - Controls: undo, reset, and export draft JSON (skeleton `results/*.json` format plus a `predictions` log).
3. **Opponents**
   - Seven editable profile cards (weights, temperature, notes), with export/import.
   - "Test" replays a saved draft and shows the predicted-pick hit rate.
4. **Results**
   - After `--score`, each of my players' actual score shown against his 90% CI.
   - Contest coverage rate, and the portfolio report across all of this week's contests.
5. **Model**
   - Backtest scorecard (§10), live scorecard (§11), a PIT histogram and 90% coverage by position, stack weights by position, and the ablation table.
   - Plain-language callouts, e.g. "90% intervals caught 84% of outcomes this season: intervals are too narrow."
6. **Data**
   - Week selector and drag-and-drop preview for new FFA/DB CSVs (parsed client-side).
   - Build status from `meta.json`, the unmatched-names list, the scoring-check result, missing-lines flags, and cache ages.

---

## 15. Repo layout

```
draftbattle.js/
  BRIEF.md  STATE.md  DECISIONS.md  README.md
  scripts/
    legacy/ffb_pipeline.py     # reference copy, unchanged
    player_sd.py
    data_sources.py            # downloads, caching, leakage guards
    ids.py                     # gsis crosswalk, name_key, aliases
    features.py                # environment, volume, shares, efficiency
    model_structural.py        # 6b–6e
    model_gbm.py               # 6f
    stack.py                   # 6g
    availability.py            # §7
    distribution.py            # §8
    correlations.py            # §9
    backtest.py                # §10
    sim.py                     # §12 Python sim
    opponents.py               # §13
    make_week.py               # one command: build, --refresh, --score
  model/scoring.json  model/params.json
  input_data/aliases.csv
  input_data/week4/{ffa.csv, draft_battle_week4_projections.csv, injuries.csv?, overrides.csv?, weather.csv?}
  data/raw/...                 # cached downloads (gitignored)
  public/data/                 # board.json, sim.json, all_projections.json, priors.json, player_sd.json, opponents.json, meta.json, backtest.json, scorecard.json
  logs/week{N}/  logs/scorecard.json
  backtest/report.md  backtest/report.json  backtest/ablations.csv
  results/
  src/  (sim/, opponents/, components/, tabs/)
  build/unmatched.txt
```

Gitignore `data/raw/`. Commit everything in `public/data/`, `logs/`, `backtest/`, `model/`, and `results/`.

---

## 16. Non-goals

- No scraping draftbattle.com and no logging into it. Its data comes from CSVs I download.
- No paid data sources.
- No kickers or defenses.
- No hosting.

---

## 17. Build phases

Each phase ends with a check that runs, then commit + push, then an update to `STATE.md`.

**Part 1: usable baseline for this week's draft**

**Phase 0: Audit and set up**
1. Find the local projects serving `:5173`/`:5174`: search my home directory for Vite projects containing `simCore.js`, `projDist.js`, or "Best Ball Projections".
2. Compare their sim math with `ffb_pipeline.py` §9.
3. Decide: **reuse** the sim and draft-room components if they match the math and the 11-slot lineup (default), or **port fresh** only if the audit finds a blocking mismatch. Log the decision. Copy what you reuse; never edit the old apps.
4. Check for `hbrady7/draftbattle.js`. Clone it if it exists; create it as a **private** repo if not.
5. Copy the input files in and scaffold `STATE.md`, `DECISIONS.md`, and `scoring.json`.
6. **Check:** an empty Vite app serves on 5175.
7. Commit + push.

**Phase 1: Data layer**
1. Build `data_sources.py` and `ids.py`: every §5 source, the cache, the leakage-guard helpers, the crosswalk, and the Sleeper test.
2. **Check:** print row counts per source per season, the ID match rate for DB's top 200 (target ≥ 95%), and write `build/unmatched.txt`.
3. Commit + push.

**Phase 2: Baseline model**
1. Build the interim board: mean = 50% FFA + 50% ECR-implied points (from the current `fp_latest_weekly.csv`), falling back to FFA only.
2. Starting QBs and implied totals come from `games.csv`.
3. SD from `player_sd.py`. Shape A from §8, with the P(plays) point mass from report status using the simple rule Q 0.85 / D 0.25 / O 0. The fitted model replaces this in Phase 8.
4. **Check:** print full rows for Gibbs, Allen, Bryce Young, Jaxon Smith-Njigba, Kittle, Skattebo, Jack Strand, and one backup QB. Simulated SD within 0.1 of target for 20 random players.
5. Commit + push.

**Phase 3: Simulator**
1. Build `sim.json`, the browser Web Worker sim, and the seeded Python sim.
2. **Check:** parity within 1 point on a synthetic draft, and timing < 300 ms.
3. Commit + push.

**Phase 4: Opponents**
1. Build the default profiles.
2. **Check:** 500-draft simulated ADP vs. DB rank.
3. Commit + push.

**Phase 5: Dashboard core**
1. Build the Board, Draft Room, and Data tabs, plus `npm run week -- --week N`.
2. **Check:** `npm run build` passes, and a scripted mock draft from seat 4 updates win % after every pick and exports valid JSON.
3. Commit + push.
4. **Tell me the baseline is ready** with one line in `STATE.md` and the terminal: "Baseline ready for Week N at localhost:5175."

**Part 2: full model**

**Phase 6: Backtest harness**
1. Build `backtest.py` with the walk-forward loop, universe, scorecard, bootstrap, and contest win-rate sim.
2. Run the four baselines.
3. **Check:** `backtest/report.md` exists with baseline numbers for 2021–2024.
4. Commit + push.

**Phase 7: Mean model**
1. Build the structural model (6b–6e) and LightGBM (6f), with ablations for each feature group.
2. **Check:** the ablation table is printed, and the chosen features are logged in `DECISIONS.md` with their CRPS gains.
3. Commit + push.

**Phase 8: Availability**
1. Fit the logistic model and the vacated-opportunity redistribution rates.
2. **Check:** calibration table of predicted P(plays) vs. actual, by report status.
3. Commit + push.

**Phase 9: Distribution and correlations**
1. Run the shape A vs. B contest, the SD challenger, and the empirical correlation fit.
2. **Check:** coverage within ±3 points of target for players and team totals on 2021–2024.
3. Commit + push.

**Phase 10: Stack and held-out test**
1. Fit the stack weights per position.
2. Run the **single held-out 2025 evaluation** and write it to the report.
3. Freeze `params.json`.
4. **Check:** the stack beats ECR-implied points on CRPS for each position, or the report says plainly where it doesn't.
5. Commit + push.

**Phase 11: Wire in, track, finish**
1. Swap the baseline mean for the full model in `make_week`.
2. Add live logging, `--score`, the scorecard, the scoring check, and the Opponents, Results, and Model tabs.
3. Write the README (§18).
4. **Check:** a clean clone → `npm install` → `npm run week -- --week 4` serves the full-model board. Running `--score` on Week 3 (already played) fills the scorecard.
5. Commit + push.

---

## 18. Weekly routine (README.md, 6 lines)

1. Drop this week's `ffa.csv` and the DB CSV into `input_data/week{N}/`. Add `injuries.csv` or `overrides.csv` only for late news.
2. `npm run week -- --week N`, then read the validation printout, including the scoring check.
3. Right before drafting: `npm run week -- --week N --refresh` for the latest injuries and lines, plus locked scores for games already played.
4. Open `localhost:5175` → Draft Room → set my seat → draft → export the draft JSON into `results/`.
5. After the games: `python scripts/make_week.py --week N --score`, then check Results and Model.
6. Commit and push.

---

## 19. Stop conditions

Stop and ask me only when one of these happens:

- A required input file (§3a) can't be found anywhere.
- GitHub push fails (auth or permissions). Report the exact error.
- The existing apps turn out to be the same repo as `draftbattle.js`, or reusing them would mean editing them in place.
- A core free source in §5 fails, other than Sleeper, which is optional. The core sources are stats_player, pbp, ffopportunity, injuries, games.csv, and db_fpecr. Retry once before stopping.
- After Phase 10 the stack loses to ECR-implied points on CRPS at **every** position. Stop and report instead of shipping a worse model.

For everything else, take the default, log it in `DECISIONS.md`, and keep going.

---

## 20. Open items I still owe (none of these block the build)

| Item | Default until I answer |
|---|---|
| Draft Battle's exact scoring, and the scoring used to pull `ffa.csv` | `scoring.json` = skeleton scoring. The §11 scoring check flags FFA mismatches. |
| 8 teams / 11 rounds / snake | Config constants with those values |
| Does DB export team or injury data? | Team from the gsis crosswalk; injuries from nflverse plus `injuries.csv` |
| The 7 AI strategies | Default DB-rank profiles |
| When I usually draft relative to kickoff (Wed? Sat?) | Build assumes any time. `--refresh` and locked scores handle it. |
