# draftbattle.js

Local best-ball projection model + draft dashboard for [Draft Battle](https://draftbattle.com):
an 8-team, 11-round snake best-ball draft against 7 AI drafters. Builds a weekly fantasy
projection with 90% intervals, my team's projected points, and a live win % with pick
recommendations. **Localhost only** (`localhost:5175`); GitHub is version control only.

See `BRIEF.md` for the full spec, `STATE.md` for current status, `DECISIONS.md` for the log.

## Weekly routine

1. Drop this week's `ffa.csv` and the DB CSV into `input_data/week{N}/`. Add `injuries.csv` or `overrides.csv` only for late news.
2. `npm run week -- --week N`, then read the validation printout, including the scoring check.
3. Right before drafting: `npm run week -- --week N --refresh` for the latest injuries, lines, and locked scores for games already played.
4. Open `localhost:5175` → Draft Room → set my seat → draft → export the draft JSON into `results/`.
5. After the games: `python scripts/make_week.py --week N --score`, then check Results and Model.
6. Commit and push.

## Dev

```
npm install
npm run dev      # serves the dashboard on localhost:5175 (strictPort)
npm run build    # production build check
```

_Baseline dashboard (Phases 0–5) comes up first; the full model (Phases 6–11) stacks on top._
