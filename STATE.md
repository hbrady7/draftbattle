# STATE

_Current phase, what's done, what's next, dead ends already tried. Kept current every phase._

## Current phase
**Phase 2 — Baseline model.** Starting. Build the interim board (mean = 50% FFA + 50% ECR-implied, fallback FFA), SD from `player_sd.py`, shape-A PDF, simple P(plays) rule.

## Done
- **Phase 0 — Audit and set up. ✅ committed `59bc525` (local).** Audited `draftTool` → REUSE sim (D0.3); scaffolded repo; dark 6-tab shell serves on `:5175`; `npm run build` passes.
- **Phase 1 — Data layer. ✅ complete (local commit pending in this phase's commit).**
  - `scripts/data_sources.py`: every §5 source, 12h current-season cache, leakage-guard helpers, core-source stop policy. **68/68 source-seasons downloaded clean.**
  - `scripts/ids.py`: `name_key` exact replica, gsis crosswalk (`players.csv` ∪ `db_playerids.csv`), aliases, `resolve()`.
  - **Checks passed:** row counts printed for all sources; **DB top-200 gsis match = 100%** (≥95% target), FFA-name 97.5%; `build/unmatched.txt` written (0 rows); Sleeper API live.

## Next
- Phase 2 build (`scripts/build_board.py` + `scripts/distribution.py`): interim mean, `player_sd` SD, shape-A PDF via `match_mean_sd`, P(plays) = Q .85 / D .25 / O 0. **Check:** print full rows for Gibbs, Allen, Bryce Young, JSN, Kittle, Skattebo, Jack Strand, a backup QB; simulated SD within 0.1 of target for 20 random players.

## Blockers / open
- **GitHub remote still not created — push is blocked.** `git push` returns the exact error `ERROR: Repository not found` (SSH auth to `hbrady7` is confirmed working; the repo simply doesn't exist). Local commits continue each phase; all get pushed once `hbrady7/draftbattle.js` (private) exists — user to create it, or provide a PAT / install `gh`. See DECISIONS D0.7.

## Dead ends tried
- `gh` CLI, `brew`, `~/.git-credentials`, credential helper, keychain github item, `*TOKEN*` env var — all absent. SSH auth to `hbrady7` verified working (push fails only because the repo doesn't exist yet).
