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
