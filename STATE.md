# STATE

_Current phase, what's done, what's next, dead ends already tried. Kept current every phase._

## Current phase
**Phase 0 — Audit and set up.** Local work complete; finishing with the serve check + commit.

## Done
- Located all §3a input files (in `~/Downloads` and `~/Downloads/draftTool`).
- Audited the existing app `~/Downloads/draftTool` (React 19 + Vite sim stack). Decision: **REUSE** its sim math (see DECISIONS D0.3). Copied `simCore.js`, `projDist.js`, `bbDraftLogic.js`, `mcWorker.js`, `draftSim.js`, `simConfig.js` into `src/sim` + `src/config` verbatim.
- Scaffolded repo at `~/draftbattle.js` per §15: dirs, `BRIEF.md`, `STATE.md`, `DECISIONS.md`, `model/scoring.json`, input files in `input_data/week4`, box scores cached in `data/raw/stats_player`.
- Built the Vite + React shell (6-tab dark dashboard) that serves on `:5175` (strictPort).
- `git init`, SSH remote set to `git@github.com:hbrady7/draftbattle.js.git`, branch `main`, local identity `hbrady7 / hollisbrady2004@gmail.com`.

## Next
- Phase 1 — Data layer (`scripts/data_sources.py`, `scripts/ids.py`): every §5 source, cache, leakage guards, crosswalk, Sleeper test. Target ≥95% ID match on DB top-200.

## Blockers / open
- **GitHub remote not yet created.** No `gh` CLI, no token, no browser creds on this machine — only SSH works, which can push/clone but not *create* a repo. The `hbrady7/draftbattle.js` repo does not exist yet, so the first `push` will fail with "repository not found." Local commits proceed each phase; they get pushed once the remote exists (user to create it private, or provide a PAT / install `gh`). See DECISIONS D0.6.

## Dead ends tried
- `gh` CLI: not installed. `brew`: not installed. No `~/.git-credentials`, no credential helper, no keychain github item, no `*TOKEN*` env var. SSH auth to `hbrady7` verified working.
