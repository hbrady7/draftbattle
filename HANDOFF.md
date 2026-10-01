# HANDOFF — draftbattle.js (session context for a fresh terminal)

Read this first. It's the one-file catch-up on everything built and decided for this
project, so a new Claude Code session knows the full state. Deeper detail lives in
`BRIEF.md` (the original spec), `STATE.md` (phase status), `DECISIONS.md` (every call +
caveat), `README.md`, and `backtest/report.md`.

---

## What this is

A **local best-ball fantasy-football projection model + live draft dashboard** for
**Draft Battle** (draftbattle.com): an 8-team, 11-round **snake, superflex best-ball**
draft against **7 AI drafters**. Goal (met): the most accurate week-to-week projection
I can *measure*, plus a dashboard that turns it into draft decisions — per-player 90%
intervals, team projected points, and a live **win %** with **per-player WPA** (win-%
added) and pick recommendations. **Localhost only** (`localhost:5175`); GitHub is just
version control. Built for **2026 NFL Week 4** (opened Thu Oct 1).

## Status: BUILD COMPLETE — all 12 phases (0–11) + extra features. Everything pushed.

The full projection model is **validated**: on the held-out **2025** season the stacked
model (structural + gradient-boosted + market/ECR) **beats the market (ECR) on CRPS at
every position** (QB 4.30<4.67, RB 3.48<3.58, WR 3.49<3.78, TE 3.55<3.87), walk-forward
audited leak-free. It is the **live board mean** (`meta.mean_recipe` = "full stack").

## Repo & environment (important gotchas)

- **Local dir:** `~/draftbattle.js`. **Remote: `git@github.com:hbrady7/draftbattle.git`**
  — note the repo is named **`draftbattle`, NOT `draftbattle.js`** (despite the dir).
- **Git:** identity `hbrady7` / `hollisbrady2004@gmail.com`; **NO `Co-Authored-By` trailer**
  (house style). SSH is the only GitHub auth on this machine. Commit + push after each
  substantive change. Latest commit at session end: **`ba39c31`** (all pushed).
- **Python:** a venv at `~/draftbattle.js/venv` (pandas/numpy/scipy/sklearn/pyarrow/
  requests/openpyxl). Run scripts as `./venv/bin/python scripts/<x>.py`.
- **No `gh` CLI, no Homebrew, no `libomp`** on this machine. Consequence: **LightGBM is
  unusable** → the GBM is sklearn `HistGradientBoostingRegressor` (equivalent). Repo
  creation had to be done by the user (done).
- **Data cache:** `data/raw/` (gitignored) holds all nflverse/ffverse/dynastyprocess
  downloads (68 source-seasons, 2019–2026). 12h current-season cache; `--refresh` forces.
- **Dev server keeps getting reaped** when started as a harness background task — run it
  in a normal terminal (`npm run dev` from `~/draftbattle.js`, or `! npm run dev`) for a
  stable server. `caffeinate -dimsu` was used to keep the Mac awake during long builds.

## Run it

```
npm install                       # once
npm run dev                       # serve the dashboard at localhost:5175
npm run week -- --week 4          # rebuild board/sim/opponents + log projections + scoring check
npm run week -- --week 4 --refresh   # + pull latest injuries/lines before drafting
./venv/bin/python scripts/make_week.py --week 3 --score   # after games: fill the scorecard
./venv/bin/python scripts/backtest.py   # walk-forward scorecard
./venv/bin/python scripts/stack.py      # refit stack + held-out 2025 eval (freezes params.json)
npm run build                     # production build check
```

## How the model works (the pipeline)

1. **Data layer** — `scripts/data_sources.py` (every source, caching, leakage guards),
   `scripts/ids.py` (gsis crosswalk + `name_key`). DB top-200 ID match 100%.
2. **Mean** — a **per-position NNLS stack** (frozen in `model/params.json['stack']`) of:
   `structural` (bottom-up: Vegas env → team volume → player shares → efficiency →
   points; `scripts/model_structural.py` + `features.py`), `gbm` (HistGBR;
   `model_gbm.py`), and `ecr_implied` (isotonic fit of actual pts on ECR positional rank,
   prior-seasons-only). Weights ~ QB gbm.47/struct.32/ecr.21 · RB gbm.42/struct.27/ecr.31 ·
   WR struct.69/ecr.23/gbm.08 · TE struct.44/gbm.36/ecr.20. Live upcoming-week projection:
   `scripts/project_week.py` (W4 Vegas + through-W3 usage → the trained models → stack).
   Ablations showed the exotic structural features (Vegas/weather/participation/efficiency/
   opponent) don't individually "ship" — the edge is the core's leak-free use of ECR +
   trailing.
3. **Availability** — `scripts/availability.py`: logistic P(plays) + snap multiplier +
   vacated-opportunity redistribution → `params.json['availability']`. Feeds the DNP mass.
4. **Distribution** — `scripts/distribution.py`: per player a **zero-floored gamma** (won
   the A/B shape contest) at (mean, player_sd SD) + a `(1−p_play)` point-mass at 0; 257-node
   inverse-CDF table (browser-parity port of `src/sim/projDist.js`).
5. **Correlations** — `scripts/correlations.py`: **empirical** Gaussian-copula role-pair
   correlations fit on ~3,400+ pairs (QB1-WR1 **0.35**, QB-TE1 0.26, RB1-RB2 ≈ −0.01, opp
   QB-QB 0.17) → `params.json['correlations']`, replacing the old 4 constants.
6. **Simulator** — `scripts/sim.py` (seeded numpy copula, vectorized best-ball, 100k) and
   `src/sim/simCore.js` + `simWorker.js` (browser Web Worker, 20k draws). Parity 0.25pt;
   per-pick 8×11 eval ~70ms. `public/data/sim.json` carries players + correlations.
7. **Backtest** — `scripts/backtest.py`: walk-forward 2021–2024 (2025 held out), ECR top-N
   universe, CRPS (primary) + MAE/Spearman/coverage/PIT/Brier. `backtest/report.md`.

Scoring (`model/scoring.json`, confirmed from DB's settings): full PPR, **4-pt pass TD**,
0.05/pass yd, −1 INT, 6/rush+rec TD, 0.1/rush+rec yd, +1/reception, −1 fumble lost,
**+6 kick/punt return TD**.

## The live draft (Draft Room) — what the user cares most about

- **6 tabs** (`src/tabs/`): Board, Draft Room, Data, Model, Results, Opponents.
- **Deterministic AI opponents** (`src/opponents/aiModel.js`): built from the user's
  `Week4_AI_Draft_Prediction_Model.xlsx` → **25 real rooms, 2,200 picks, 9 named AIs** →
  `scripts/ingest_ai_data.py` → `public/data/ai_opponents.json` (per-AI round-by-round
  position script + player priors + ADP). **The bots draft deterministically: the
  highest-ranked available player (by `db_rank` = draft-page ranking) at the position
  their script calls for.** The 7 "usable" AIs (≥15 rooms): Cobble, Hocking, Krebs,
  Paterson, Tubbs, Beaumont, Mullins (Faleolo/Crookshank dropped — too few rooms). You
  assign each opponent seat to an AI in the Draft Room (defaults to those 7).
- **WPA (win % added):** per-candidate win% via the seeded Web Worker (place the player,
  complete the draft with the deterministic bots, measure win%). Shows win%, Δ, points,
  90% CI, matchup, and **exact** P(available at your next pick) with 🔒 take-now / ⏳ wait
  tags.
- **Draft Plan** (`src/opponents/draftPlan.js`, `scripts/plan_check.mjs`): given your
  **seat**, forward-sims the whole deterministic draft and outputs the optimal target at
  each of your 11 rounds — grab scarce players now, **defer fallers** (e.g. a QB ranked
  #13 the bots won't take until R4 gets scheduled at R4, not reached for at R1). Value =
  board mean × positional need; timing = the exact bot schedule. Re-plans live.
- **Seat picker** is prominent ("Seat N"); player names show **first name** in the grid/strips.

## Known caveats / deferrals (all logged in DECISIONS.md)

- **Win% absolute runs high (~80%)** because the real bots draft rigid, exploitable
  scripts — trust the **Δ/WPA ranking + the floor**, not the headline %.
- **Questionable-injury** play-rate is optimistic (pred ~0.83 vs ~0.58 held-out; the
  injury universe includes deep players).
- **Deferred (nice-to-haves):** SD-model challenger, team-best-ball-total coverage check;
  `make_week --score` currently scores the ECR-implied line (not the full stack yet); the
  GBM re-trains per build (fast) rather than persisting; the per-candidate win% `evaluate`
  runs over the top-200 universe while the Draft Plan uses the full board.
- **Rankings:** the user's updated draft-page ranking matches the loaded `db_rank` to
  within a few spots (top ~25 exact). To load an exact newer file, drop
  `draft_battle_week4_projections.csv` into `input_data/week4/` and `npm run week`.

## How we got here (session arc, so you know the user's priorities)

Built autonomously phase-by-phase (0→11), committing/pushing each. The user then drove a
series of live-draft upgrades, in order: **per-player WPA recommendations** → **ingest the
real 25-room AI data** → **drop low-data AIs + first-name display + smart pick-entry** →
**value-aware "take now / wait" recs** → **deterministic bots + exact who-falls** →
**pre-draft Draft Plan exploiting bot timing**. The through-line: the user wants the tool
to **exploit the now-perfectly-predictable bots to extract maximum draft value** (wait on
players the bots ignore, grab scarce value at the last moment), with everything grounded
in the ff data.

## Good first moves in a new session

1. `cat STATE.md DECISIONS.md` for status + rationale; `BRIEF.md` for the full spec.
2. `npm run dev` (in a real terminal) → open localhost:5175 → Draft Room.
3. `git log --oneline` to see the 20+ commits (phases + feature work).
