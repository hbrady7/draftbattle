# draftbattle.js

Local best-ball projection model + draft dashboard for [Draft Battle](https://draftbattle.com):
an 8-team, 11-round snake best-ball draft vs 7 AI drafters. Per-player weekly 90%
intervals, your team's projected points, and a **live win % with per-player WPA
(win-% added)** during the draft — driven by the AIs' *real* observed behavior.
**Localhost only** (`localhost:5175`); GitHub is version control.

The full projection model is **validated**: on the held-out 2025 season the stacked
model (structural + gradient-boosted + market) beats the market (ECR) on CRPS at
every position — see the **Model** tab. `BRIEF.md` = spec, `STATE.md` = status,
`DECISIONS.md` = every call + caveat.

## Weekly routine

1. Drop this week's `ffa.csv` and the DB CSV into `input_data/week{N}/` (+ `injuries.csv` / `overrides.csv` for late news).
2. `npm run week -- --week N` — builds the board/sim/opponents, logs projections, runs the scoring check. Read the printout.
3. Right before drafting: `npm run week -- --week N --refresh` for the latest injuries/lines.
4. `npm run dev` → **localhost:5175** → **Draft Room**: set your seat, assign the 7 AIs you face, enter picks; watch win % + each player's WPA and who'll fall to you.
5. After the games: `python scripts/make_week.py --week N --score` → the **Results** tab shows your players vs their 90% CI + coverage.
6. `git commit && git push`.

## Dev

```
npm install                     # once
./venv/bin/python -V            # Python deps preinstalled in ./venv
npm run dev                     # serve localhost:5175
npm run build                   # production build check
python scripts/backtest.py      # walk-forward scorecard
python scripts/stack.py         # refit stack + held-out 2025 eval (freezes params.json)
```

## Tabs
**Board** projections + 90% CI + edge vs DB · **Draft Room** live win %, WPA, who-falls-to-you ·
**Opponents** the 7 real AI drafters · **Results** scored weeks · **Model** backtest + held-out validation ·
**Data** build status + scoring check.
