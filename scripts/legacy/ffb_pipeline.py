#!/usr/bin/env python3
"""
ffb_pipeline.py: NFL weekly fantasy football pipeline, all in one file.

This file combines build_board.py, ingest_sources.py, espnFetch.py,
get_priors.py, generate_pdfs.py, update_board.py and project_results.py.
The logic is unchanged. Only names that collided between files were renamed
(see "Merged names" at the bottom of this docstring).

"PDF" here means probability density function (a player's distribution of
fantasy points), not a PDF document.


SETUP
-----
Put this file in the same folder the original scripts lived in (e.g. scripts/),
one level below the project root. Paths are resolved from the project root:
ROOT = the parent of this file's folder.

Dependencies: numpy, pandas. requests is only needed when the ESPN override is on.
Optional: b0_markov.py next to this file supplies norm_team(); without it, team
strings are upper-cased and stripped.


COMMANDS
--------
  python scripts/ffb_pipeline.py build [--refresh-stats]   full pre-draft build (board -> priors -> PDFs)
  python scripts/ffb_pipeline.py priors [--refresh-stats]  priors only (needs an existing board.json)
  python scripts/ffb_pipeline.py pdfs                      PDFs only, from the existing board.json
  python scripts/ffb_pipeline.py update                    live-draft rank/projection refresh from draft-page HTML
  python scripts/ffb_pipeline.py results                   post-draft portfolio simulation
  python scripts/ffb_pipeline.py espn [--week N] [--player NAME]   test the ESPN fetch
  python scripts/ffb_pipeline.py config                    print the parsed playerList.js config

--refresh-stats (or --force) re-downloads the nflverse box scores, including the
normally permanent 2025 cache.

Typical week: build -> (draft; optionally update during it) -> save drafts to
results/ -> results.


FILES
-----
Inputs
  input_data/DBranks.json               RotoBaller ranks + projections (may be RTF-wrapped). Defines the player pool.
  input_data/ffa.csv                    FFA model: player, position, team, points, sd_points|sd_pts, floor, ceiling|cieling
  input_data/fantasypros/{QB,RB,WR,TE}.csv   FantasyPros stat lines (header row skipped; columns by position order)
  input_data/user_projections.json      {"byId": {"<id>": {min, max, knots, ...}}} manual PDFs; override the algorithm
  input_data/playerlistondraft.rtf      saved draft-page HTML (for `update`)
  src/config/playerList.js              pos_limits, exclude, force_include, early_wk_ovrd, locked_scores
  src/config/simConfig.js               N_SIM_RESULTS = 100_000
  results/*.json                        completed drafts: {"rosters": [[{"slot", "player": {id, name, team, position}}]], "myTeam": i, "teamNames": [...]}
  data/stats_player_week_{2025,2026}.csv    nflverse cache (auto-downloaded)

Outputs
  public/data/board.json                player pool, matchups, priors, team profiles
  public/data/priors.json               per-player game logs + team stats
  public/data/all_projections.json      per-player PDFs: {min, max, knots[9], source}
  public/data/portfolio.json            simulation results


SCORING (full PPR)
------------------
0.05/pass yd, 4/pass TD, -1/INT, 0.1/rush yd, 6/rush TD, 0.1/rec yd, 6/rec TD,
1/reception, -1/fumble lost. Historical box scores also get 2/two-point conversion;
FantasyPros projections do not.


playerList.js FORMAT
--------------------
  export const config = {
      pos_limits: { QB: 32, RB: 40, WR: 50, TE: 24 },
      exclude: ["Sam Darnold", "Rams"],        // player names or team abbreviations
      force_include: ["Drew Lock"],            // added back even if outside the position cap
      early_wk_ovrd: 0,                        // >0 = pull that week's ESPN projections
      locked_scores: { "Joe Burrow": 31.2 }    // name or id -> fixed score in the sim
  };
Use double quotes and no comments. The loader converts JS to JSON with regex; if
parsing fails it silently falls back to defaults (your excludes, force-includes
and ESPN override are lost). locked_scores is parsed separately by `results` and
survives a failed parse.


HOW EACH STAGE WORKS
--------------------
1. build (build_board)
   - Loads RotoBaller, drops free agents and excludes, keeps the top N per position
     by ranking (N from pos_limits), then adds force-includes from outside the cut.
   - Merges FFA (mean/SD/floor/ceiling) and FantasyPros (stat line rescored to
     league scoring) by (name key, position).
   - If early_wk_ovrd > 0, pulls ESPN projections for that week.
   - Infers games from opponent strings ("@ BAL", "vs. SEA"), writes board.json,
     then runs priors and PDFs.

2. priors (build_priors)
   - Downloads nflverse weekly stats. 2025 is cached permanently; 2026 is
     re-checked every 12 h and re-downloaded if the remote file is newer.
   - Keeps REG season only. For each board player, keeps games on his CURRENT
     team at his position, rescored to league points.
   - Team profiles: pass/rush yards per attempt, and OAP (how far an offense beat
     what its opponents usually allow, or how far a defense held offenses under
     their usual output, in %), plus the top 5 fantasy games each defense allowed in 2026.

3. pdfs (generate_all_pdfs)
   - "Qualified" = 8+ games with > 0 points on the current team.
   - Target mean = 45% FFA + 45% FantasyPros (+10% historical average if qualified).
     ESPN, when present, replaces both (averaged with FantasyPros). Falls back to
     RotoBaller, then 8.0. Backup QBs capped at 4.5. Q/O/D/IR pulled 35% toward
     the lowest estimate.
   - SD: qualified = 0.8 x historical SD; else position CV x mean.
   - Range: mean -2 SD to +2.6 SD, widened to real worst/best games, then adjusted
     by role (QB floor, featured RB ceiling, backup caps, etc.).
   - Shape: qualified = Gaussian KDE of real game scores; else a position template.
     Role tweaks: dual-threat QB (5.5+ rush att/g) skewed up, committee RB skewed
     down with a spike near 0, injured players get a spike at 0.
   - Exponentially tilted so the mean hits the target, smoothed, stored as 9
     knot heights between min and max. user_projections.json overrides by id.

4. update (update_board)
   - Scrapes rank and projection from the saved draft-page HTML, updates
     ranking / projectedPoints / pos_rank in board.json. Does NOT rerun PDFs.

5. results (project_results)
   - Loads every draft in results/, simulates N_SIM_RESULTS weeks.
   - Gaussian copula: same-team QB-WR/TE 0.15, QB-RB 0.05, opposing starting QBs 0.20.
   - Each correlated normal draw -> percentile -> player's inverse CDF (with thin
     tails past min/max). locked_scores are fixed values.
   - Best-ball lineup per team per sim: QB, 2 RB, 3 WR, TE, FLEX (RB/WR/TE),
     SUPERFLEX (any). Win = highest score in the contest (ties count as wins).
   - Output: avg wins, shutout %, win distribution, per-player exposure and
     downside impact (avg wins when he's below median), hedge score (% of bad
     sims, <= 25% of contests won, where he hits his top 25%; > 25 = hedge).


KNOWN QUIRKS (behavior preserved as-is)
---------------------------------------
- `update` barely affects anything downstream: projectedPoints only feeds the
  target mean when both FFA and FantasyPros are missing, and PDFs aren't regenerated.
- Role-based correlation bumps (PASS1, RUSH_QB, ...) never fire because nothing
  assigns roles. all_projections.json has no "points", so QB starter ordering in
  the sim falls back to projectedPoints.
- ESPN fetch sends blank cookies, so it only works for a public league; otherwise
  it warns and the build continues without ESPN.
- Legacy names: fit2025 / y2025 hold combined 2025+2026 data; wk1 is the most
  recent game (players) or 2026 averages (teams). Game spread/total/kickoff in
  board.json are placeholders.
- The sim is unseeded, so results vary slightly run to run.


MERGED NAMES
------------
Functions that existed under the same name in more than one file:
  clean_name, name_key          ingest_sources + espnFetch (identical) + get_priors.clean_name_key (identical)
  draft_name_key                update_board.clean_name_key / project_results.clean_name_key
                                (does NOT strip a trailing "(QB)" tag)
  norm_team                     ingest_sources version (b0_markov or upper/strip fallback)
  nfl_norm_team                 get_priors.norm_team (JAC->JAX, LA->LAR)
  fp_line_points                build_board.calc_league_points (projection line, no 2-pt, 1 dp)
  game_line_points              get_priors.calc_league_points (box score, with 2-pt, 2 dp)
  build_board                   build_board.build
  update_board                  update_board.update
  project_results               project_results.run
  generate_pdfs_main            generate_pdfs.main
"""

from __future__ import annotations

import argparse
import csv
import html
import json
import math
import os
import re
import statistics
import sys
import time
import urllib.request
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any, Dict, Optional

import numpy as np
import pandas as pd


# ══════════════════════════════════════════════════════════════════════════════
# 1. PATHS & SHARED CONSTANTS
# ══════════════════════════════════════════════════════════════════════════════

ROOT = Path(__file__).resolve().parents[1]

INPUT_DIR = ROOT / "input_data"
CONFIG_DIR = ROOT / "src" / "config"
DATA_DIR = ROOT / "data"
OUT_DIR = ROOT / "public" / "data"
RESULTS_DIR = ROOT / "results"

BOARD_PATH = OUT_DIR / "board.json"
PROJECTIONS_PATH = OUT_DIR / "all_projections.json"
PRIORS_PATH = OUT_DIR / "priors.json"
PORTFOLIO_PATH = OUT_DIR / "portfolio.json"

USER_PROJ_PATH = INPUT_DIR / "user_projections.json"
DRAFT_RTF_PATH = INPUT_DIR / "playerlistondraft.rtf"
PLAYER_LIST_CONFIG = CONFIG_DIR / "playerList.js"
SIM_CONFIG_PATH = CONFIG_DIR / "simConfig.js"

SKILL_POSITIONS = {"QB", "RB", "WR", "TE"}
SUFFIXES = {"jr", "sr", "ii", "iii", "iv", "v"}

TEAM_NAMES = {
    "ARI": "Cardinals", "ATL": "Falcons", "BAL": "Ravens", "BUF": "Bills",
    "CAR": "Panthers", "CHI": "Bears", "CIN": "Bengals", "CLE": "Browns",
    "DAL": "Cowboys", "DEN": "Broncos", "DET": "Lions", "GB": "Packers",
    "HOU": "Texans", "IND": "Colts", "JAX": "Jaguars", "JAC": "Jaguars", "KC": "Chiefs",
    "LAC": "Chargers", "LAR": "Rams", "LV": "Raiders", "MIA": "Dolphins",
    "MIN": "Vikings", "NE": "Patriots", "NO": "Saints", "NYG": "Giants",
    "NYJ": "Jets", "PHI": "Eagles", "PIT": "Steelers", "SEA": "Seahawks",
    "SF": "49ers", "TB": "Buccaneers", "TEN": "Titans", "WAS": "Commanders",
}


# ══════════════════════════════════════════════════════════════════════════════
# 2. SHARED NAME & TEAM HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def clean_name(name: str) -> str:
    """Removes trailing position tags like (QB) and strips whitespace."""
    return re.sub(r"\s*\(([A-Z]{2,3})\)\s*$", "", str(name or "")).strip()


def name_parts(name: str) -> list[str]:
    n = clean_name(name).lower()
    n = re.sub(r"[^a-z0-9\s]", "", n)
    return [p for p in n.split() if p and p not in SUFFIXES]


def name_key(name: str) -> str:
    """Matching key: lowercase, punctuation and suffixes removed, (POS) tag stripped."""
    return "".join(name_parts(name))


def draft_name_key(text: str) -> str:
    """Matching key used by update/results. Same as name_key but keeps a trailing (POS) tag."""
    t = re.sub(r"[^a-zA-Z0-9\s]", "", str(text).lower())
    parts = [p for p in t.split() if p and p not in SUFFIXES]
    return "".join(parts)


# Board-side team normalizer (used by ingestion and build).
try:
    from b0_markov import norm_team
except ImportError:
    # Fallback normalizer if b0_markov is not available
    def norm_team(team_str: str) -> str:
        return str(team_str).strip().upper()


def nfl_norm_team(team: str | None) -> str:
    """nflverse-side team normalizer (used by priors): JAC->JAX, LA->LAR, NaN->''."""
    if not team or pd.isna(team):
        return ""
    t = str(team).upper().strip()
    if t in {"JAC", "JAX"}:
        return "JAX"
    if t == "LA":
        return "LAR"
    return t


def standardize_team(abbr: str) -> str:
    """Forces JAC to JAX and LA to LAR for universal UI matching."""
    if not abbr:
        return abbr
    abbr = str(abbr).strip().upper()
    if abbr == "JAC":
        return "JAX"
    if abbr == "LA":
        return "LAR"
    return abbr


# ══════════════════════════════════════════════════════════════════════════════
# 3. ESPN FETCH  (was espnFetch.py)
# ══════════════════════════════════════════════════════════════════════════════

ESPN_LEAGUE_ID = "1391562842"
ESPN_SEASON = 2026

# ESPN defaultPositionId mapping: 1=QB, 2=RB, 3=WR, 4=TE, 5=K, 16=D/ST
ESPN_POS_MAP = {1: "QB", 2: "RB", 3: "WR", 4: "TE", 5: "K", 16: "D/ST"}


def fetch_espn_projections(
    week: int,
    league_id: str = ESPN_LEAGUE_ID,
    season: int = ESPN_SEASON,
    cookies: Optional[dict] = None
) -> Dict[str, float]:
    """
    Fetches ESPN projections for all players for a specific scoring period (week).
    Returns a dictionary mapping name_key(name) -> projected appliedTotal fantasy points.
    """
    import requests  # only needed when the ESPN override is active

    if cookies is None:
        cookies = {"espn_s2": "", "swid": ""}

    url = (
        f"https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl/seasons/{season}"
        f"/segments/0/leagues/{league_id}?scoringPeriodId={week}"
        f"&view=players_wl&view=kona_player_info"
    )

    filters = {
        "players": {
            "limit": 1500,
            "sortDraftRanks": {
                "sortPriority": 100,
                "sortAsc": True,
                "value": "STANDARD"
            }
        }
    }

    headers = {"x-fantasy-filter": json.dumps(filters)}

    print(f"Fetching ESPN Week {week} projections from league {league_id}...")
    resp = requests.get(url, headers=headers, cookies=cookies)
    resp.raise_for_status()

    players_data = resp.json().get("players", [])
    projections: Dict[str, float] = {}

    for entry in players_data:
        p_info = entry.get("player", {})
        name = p_info.get("fullName")
        if not name:
            continue

        stats_array = p_info.get("stats", [])
        week_stat = next(
            (
                s for s in stats_array
                if s.get("statSourceId") == 1
                and s.get("statSplitTypeId") == 1
                and s.get("scoringPeriodId") == week
            ),
            None
        )

        if week_stat:
            pts = float(week_stat.get("appliedTotal") or 0.0)
            key = name_key(name)
            projections[key] = round(pts, 2)

    print(f"Loaded ESPN projections for {len(projections)} players.")
    return projections


# ══════════════════════════════════════════════════════════════════════════════
# 4. SOURCE INGESTION  (was ingest_sources.py)
# ══════════════════════════════════════════════════════════════════════════════

FP_COLMAP = {
    "QB": ["player", "team", "pass_att", "pass_cmp", "pass_yds", "pass_td", "int",
           "rush_att", "rush_yds", "rush_td", "fl", "fpts"],
    "RB": ["player", "team", "rush_att", "rush_yds", "rush_td", "rec", "rec_yds",
           "rec_td", "fl", "fpts"],
    "WR": ["player", "team", "rec", "rec_yds", "rec_td", "rush_att", "rush_yds",
           "rush_td", "fl", "fpts"],
    "TE": ["player", "team", "rec", "rec_yds", "rec_td", "fl", "fpts"],
}


def r1(x):
    if x is None or (isinstance(x, float) and not np.isfinite(x)):
        return None
    return round(float(x), 1)


def r2(x):
    if x is None or (isinstance(x, float) and not np.isfinite(x)):
        return None
    return round(float(x), 2)


def fcsv(val):
    if val is None:
        return None
    s = str(val).replace(",", "").replace("\xa0", "").strip()
    if not s or s.upper() in {"NA", "N/A", "-"}:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def model_cell(row, *cols):
    for c in cols:
        if c in row and pd.notna(row[c]):
            return row[c]
    return None


def load_player_config() -> dict:
    """
    Reads config/playerList.js to extract quota and inclusion/exclusion logic.
    Expects a JS file exporting an object, e.g.:
    export const config = {
        pos_limits: { QB: 32, RB: 40, WR: 50, TE: 24 },
        exclude: ["Sam Darnold", "Rams"],
        force_include: ["Drew Lock"]
    };
    """
    config_path = PLAYER_LIST_CONFIG
    default_config = {
        "pos_limits": {"QB": 32, "RB": 40, "WR": 50, "TE": 24},
        "exclude": [],
        "force_include": [],
        "early_wk_ovrd": 0,
        "locked_scores": {}
    }

    if not config_path.exists():
        print(f"Warning: {config_path} not found. Using default player config.")
        return default_config

    text = config_path.read_text(encoding="utf-8")

    # Extract object between first { and last }
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1:
        return default_config

    json_str = text[start:end+1]

    # Clean up standard JS to be valid JSON (quote unquoted keys, remove trailing commas)
    json_str = re.sub(r'([{,]\s*)([A-Za-z0-9_]+)(\s*:)', r'\1"\2"\3', json_str)
    json_str = re.sub(r',\s*([\]}])', r'\1', json_str)

    try:
        return json.loads(json_str)
    except json.JSONDecodeError as e:
        print(f"Warning: Could not parse playerList.js as JSON: {e}. Check formatting.")
        return default_config


def load_roto_projections(path: Path = INPUT_DIR / "DBranks.json") -> list[dict]:
    """Reads the primary RotoBaller ranks/projections, stripping RTF headers."""
    if not path.exists():
        raise FileNotFoundError(f"Missing Roto projections at {path}")

    raw = path.read_text(encoding="latin-1")
    # Clean RTF unicode escapes
    raw = re.sub(r"\\'([0-9a-fA-F]{2})", lambda m: chr(int(m.group(1), 16)), raw)
    # Clean standard escapes
    text = re.sub(r"\\([{}])", r"\1", raw)

    m = re.search(r'\{"players":', text)
    if not m:
        raise ValueError(f"No players JSON object found in {path}")

    data, _ = json.JSONDecoder().raw_decode(text[m.start():])
    return data["players"]


def load_model_projections(path: Path = INPUT_DIR / "ffa.csv") -> list[dict]:
    """Reads the custom model projections (FFA) for floor/ceiling/sd_pts."""
    if not path.exists():
        print(f"Warning: Model projections not found at {path}")
        return []

    df = pd.read_csv(path)
    recs = []
    for r in df.to_dict("records"):
        pos = str(r.get("position") or "").upper().strip()
        if pos not in SKILL_POSITIONS:
            continue
        recs.append({
            "name": r.get("player"),
            "position": pos,
            "team": norm_team(r.get("team")) if pd.notna(r.get("team")) else None,
            "points": r1(model_cell(r, "points")),
            "sd_points": r2(model_cell(r, "sd_points", "sd_pts")),
            "floor": r1(model_cell(r, "floor")),
            "ceiling": r1(model_cell(r, "ceiling", "cieling")),
        })
    return recs


def load_fp_projections(fp_dir: Path = INPUT_DIR / "fantasypros") -> list[dict]:
    """Iterates through QB/RB/WR/TE csv files in the fantasypros directory."""
    recs = []

    if not fp_dir.exists():
        print(f"Warning: FantasyPros directory not found at {fp_dir}")
        return recs

    for pos, cols in FP_COLMAP.items():
        path = fp_dir / f"{pos}.csv"
        if not path.exists():
            continue

        with path.open(encoding="utf-8-sig", newline="") as fh:
            reader = csv.reader(fh)
            next(reader, None)  # Skip header
            for row in reader:
                if not row:
                    continue
                name = str(row[0] if row else "").replace("\xa0", "").strip()
                if not name:
                    continue

                padded = list(row) + [""] * max(0, len(cols) - len(row))
                raw = {cols[i]: padded[i] for i in range(len(cols))}
                team_raw = str(raw.get("team") or "").replace("\xa0", "").strip()

                recs.append({
                    "name": name,
                    "position": pos,
                    "team": norm_team(team_raw) if team_raw else None,
                    "pass_att": r1(fcsv(raw.get("pass_att"))),
                    "pass_cmp": r1(fcsv(raw.get("pass_cmp"))),
                    "pass_yds": r1(fcsv(raw.get("pass_yds"))),
                    "pass_td": r1(fcsv(raw.get("pass_td"))),
                    "int": r1(fcsv(raw.get("int"))),
                    "rush_att": r1(fcsv(raw.get("rush_att"))),
                    "rush_yds": r1(fcsv(raw.get("rush_yds"))),
                    "rush_td": r1(fcsv(raw.get("rush_td"))),
                    "rec": r1(fcsv(raw.get("rec"))),
                    "rec_yds": r1(fcsv(raw.get("rec_yds"))),
                    "rec_td": r1(fcsv(raw.get("rec_td"))),
                    "fl": r1(fcsv(raw.get("fl"))),
                })
    return recs


def filter_and_rank_players(raw_players: list[dict], config: dict) -> list[dict]:
    """
    Applies pos_limits, name/team exclusions, and force inclusions from the config.
    Returns the truncated/filtered list of eligible players.
    """
    pos_limits = config.get("pos_limits", {"QB": 32, "RB": 40, "WR": 50, "TE": 24})

    # Normalize strings for easier matching
    excludes = [str(x).lower().strip() for x in config.get("exclude", [])]
    includes = [str(x).lower().strip() for x in config.get("force_include", [])]

    by_pos = {p: [] for p in pos_limits.keys()}

    # First Pass: Organize and remove exclusions
    for p in raw_players:
        pos = p.get("position")
        if pos not in by_pos:
            continue
        if p.get("isFreeAgent"):
            continue

        name_clean = clean_name(p.get("name", ""))
        team_clean = norm_team(p.get("team", ""))

        # Check Exclusion criteria (match player name OR team name)
        if name_clean.lower() in excludes or team_clean.lower() in excludes:
            continue

        by_pos[pos].append(p)

    selected = []

    # Second Pass: Sort by ranking, apply limits, and apply force-includes
    for pos, rows in by_pos.items():
        # Sort lower ranking = better. Nulls go to the back.
        rows.sort(key=lambda x: (
            x.get("ranking") is None,
            x.get("ranking") if x.get("ranking") is not None else 10**9,
        ))

        pos_limit = pos_limits.get(pos, 50)
        pos_selected = rows[:pos_limit]

        # Track names already in the limit cut
        selected_names = {clean_name(p["name"]).lower() for p in pos_selected}

        # Scan players outside the cut for force-includes
        for p in rows[pos_limit:]:
            name_clean = clean_name(p["name"]).lower()
            if name_clean in includes and name_clean not in selected_names:
                pos_selected.append(p)
                selected_names.add(name_clean)

        # Assign pos_rank metadata for final list
        for i, p in enumerate(pos_selected, start=1):
            p["pos_rank"] = i
            selected.append(p)

    return selected


# ══════════════════════════════════════════════════════════════════════════════
# 5. HISTORICAL PRIORS & TEAM PROFILES  (was get_priors.py)
# ══════════════════════════════════════════════════════════════════════════════

CACHE_TTL_SECONDS = 12 * 3600


def fnum(row: dict | pd.Series, *cols: str, default: float = 0.0) -> float:
    for c in cols:
        if c in row and pd.notna(row[c]):
            try:
                return float(row[c])
            except (ValueError, TypeError):
                continue
    return default


def game_line_points(py, ptd, ints, ry, rtd, recy, rectd, rec, fl, twopt) -> float:
    """League points for one historical box score (includes 2-pt conversions)."""
    pts = (
        0.05 * py + 4.0 * ptd - 1.0 * ints + 0.1 * ry + 6.0 * rtd +
        0.1 * recy + 6.0 * rectd + 1.0 * rec - 1.0 * fl + 2.0 * twopt
    )
    return round(float(pts), 2)


def build_team_stats(weekly_df: pd.DataFrame) -> dict:
    team_stats_map = {}

    pass_yds = pd.to_numeric(weekly_df.get('passing_yards', 0), errors='coerce').fillna(0)
    pass_tds = pd.to_numeric(weekly_df.get('passing_tds', 0), errors='coerce').fillna(0)
    ints = pd.to_numeric(weekly_df.get('interceptions', weekly_df.get('passing_interceptions', 0)), errors='coerce').fillna(0)
    rush_yds = pd.to_numeric(weekly_df.get('rushing_yards', 0), errors='coerce').fillna(0)
    rush_tds = pd.to_numeric(weekly_df.get('rushing_tds', 0), errors='coerce').fillna(0)
    rec_yds = pd.to_numeric(weekly_df.get('receiving_yards', 0), errors='coerce').fillna(0)
    rec_tds = pd.to_numeric(weekly_df.get('receiving_tds', 0), errors='coerce').fillna(0)
    receptions = pd.to_numeric(weekly_df.get('receptions', 0), errors='coerce').fillna(0)
    fl = pd.to_numeric(weekly_df.get('rushing_fumbles_lost', 0), errors='coerce').fillna(0) + \
         pd.to_numeric(weekly_df.get('receiving_fumbles_lost', 0), errors='coerce').fillna(0) + \
         pd.to_numeric(weekly_df.get('sack_fumbles_lost', 0), errors='coerce').fillna(0)
    twopt = pd.to_numeric(weekly_df.get('passing_2pt_conversions', 0), errors='coerce').fillna(0) + \
            pd.to_numeric(weekly_df.get('rushing_2pt_conversions', 0), errors='coerce').fillna(0) + \
            pd.to_numeric(weekly_df.get('receiving_2pt_conversions', 0), errors='coerce').fillna(0)

    weekly_df['ppr_fast'] = (0.05 * pass_yds + 4.0 * pass_tds - 1.0 * ints +
                             0.1 * rush_yds + 6.0 * rush_tds + 0.1 * rec_yds + 6.0 * rec_tds +
                             1.0 * receptions - 1.0 * fl + 2.0 * twopt)
    weekly_df['tds_fast'] = pass_tds + rush_tds + rec_tds

    weekly_df['pass_att'] = pd.to_numeric(weekly_df.get('attempts', 0), errors='coerce').fillna(0)
    weekly_df['pass_yds_num'] = pass_yds
    weekly_df['rush_att'] = pd.to_numeric(weekly_df.get('carries', 0), errors='coerce').fillna(0)
    weekly_df['rush_yds_num'] = rush_yds

    cols = ['pass_att', 'pass_yds_num', 'rush_att', 'rush_yds_num']
    games = weekly_df.groupby(['season', 'week', 'team_norm', 'opp_norm'])[cols].sum().reset_index()

    games['off_pass_ypa'] = np.where(games['pass_att'] > 0, games['pass_yds_num'] / games['pass_att'], 0.0)
    games['off_rush_ypa'] = np.where(games['rush_att'] > 0, games['rush_yds_num'] / games['rush_att'], 0.0)

    g25 = games[games['season'] == 2025].copy()
    g26 = games[games['season'] == 2026].copy()

    # Define Baselines (Mean of Game YPAs)
    def_base_26 = g26.groupby('opp_norm')[['off_pass_ypa', 'off_rush_ypa']].mean().rename(columns={'off_pass_ypa': 'def_pass_ypa_26', 'off_rush_ypa': 'def_rush_ypa_26'})
    def_base_cum = games.groupby('opp_norm')[['off_pass_ypa', 'off_rush_ypa']].mean().rename(columns={'off_pass_ypa': 'def_pass_ypa_cum', 'off_rush_ypa': 'def_rush_ypa_cum'})
    off_base_26 = g26.groupby('team_norm')[['off_pass_ypa', 'off_rush_ypa']].mean().rename(columns={'off_pass_ypa': 'off_pass_ypa_26', 'off_rush_ypa': 'off_rush_ypa_26'})
    off_base_cum = games.groupby('team_norm')[['off_pass_ypa', 'off_rush_ypa']].mean().rename(columns={'off_pass_ypa': 'off_pass_ypa_cum', 'off_rush_ypa': 'off_rush_ypa_cum'})

    # Merge baselines to evaluate 2026 OAP per game
    g26 = g26.merge(def_base_26, on='opp_norm', how='left')
    g26 = g26.merge(def_base_cum, on='opp_norm', how='left')
    g26 = g26.merge(off_base_26, on='team_norm', how='left')
    g26 = g26.merge(off_base_cum, on='team_norm', how='left')

    # Offensive OAP
    g26['oap_off_pass_26'] = np.where(g26['def_pass_ypa_26'] > 0, (g26['off_pass_ypa'] - g26['def_pass_ypa_26']) / g26['def_pass_ypa_26'] * 100, 0.0)
    g26['oap_off_rush_26'] = np.where(g26['def_rush_ypa_26'] > 0, (g26['off_rush_ypa'] - g26['def_rush_ypa_26']) / g26['def_rush_ypa_26'] * 100, 0.0)
    g26['oap_off_pass_cum'] = np.where(g26['def_pass_ypa_cum'] > 0, (g26['off_pass_ypa'] - g26['def_pass_ypa_cum']) / g26['def_pass_ypa_cum'] * 100, 0.0)
    g26['oap_off_rush_cum'] = np.where(g26['def_rush_ypa_cum'] > 0, (g26['off_rush_ypa'] - g26['def_rush_ypa_cum']) / g26['def_rush_ypa_cum'] * 100, 0.0)

    # Defensive OAP
    g26['oap_def_pass_26'] = np.where(g26['off_pass_ypa_26'] > 0, (g26['off_pass_ypa'] - g26['off_pass_ypa_26']) / g26['off_pass_ypa_26'] * 100, 0.0)
    g26['oap_def_rush_26'] = np.where(g26['off_rush_ypa_26'] > 0, (g26['off_rush_ypa'] - g26['off_rush_ypa_26']) / g26['off_rush_ypa_26'] * 100, 0.0)
    g26['oap_def_pass_cum'] = np.where(g26['off_pass_ypa_cum'] > 0, (g26['off_pass_ypa'] - g26['off_pass_ypa_cum']) / g26['off_pass_ypa_cum'] * 100, 0.0)
    g26['oap_def_rush_cum'] = np.where(g26['off_rush_ypa_cum'] > 0, (g26['off_rush_ypa'] - g26['off_rush_ypa_cum']) / g26['off_rush_ypa_cum'] * 100, 0.0)

    # Aggregate Team OAPs across all 2026 games
    team_off_agg = g26.groupby('team_norm')[['pass_att', 'rush_att', 'off_pass_ypa', 'off_rush_ypa', 'oap_off_pass_26', 'oap_off_rush_26', 'oap_off_pass_cum', 'oap_off_rush_cum']].mean()
    team_def_agg = g26.groupby('opp_norm')[['pass_att', 'rush_att', 'off_pass_ypa', 'off_rush_ypa', 'oap_def_pass_26', 'oap_def_rush_26', 'oap_def_pass_cum', 'oap_def_rush_cum']].mean()

    # Overall 2025 Regular Season Averages
    off_25_sum = g25.groupby('team_norm')[cols].sum()
    off_25_sum['overall_pass_ypa'] = np.where(off_25_sum['pass_att'] > 0, off_25_sum['pass_yds_num'] / off_25_sum['pass_att'], 0.0)
    off_25_sum['overall_rush_ypa'] = np.where(off_25_sum['rush_att'] > 0, off_25_sum['rush_yds_num'] / off_25_sum['rush_att'], 0.0)

    def_25_sum = g25.groupby('opp_norm')[cols].sum()
    def_25_sum['overall_pass_ypa'] = np.where(def_25_sum['pass_att'] > 0, def_25_sum['pass_yds_num'] / def_25_sum['pass_att'], 0.0)
    def_25_sum['overall_rush_ypa'] = np.where(def_25_sum['rush_att'] > 0, def_25_sum['rush_yds_num'] / def_25_sum['rush_att'], 0.0)

    # Filter Top 5 Allowed specifically to the 2026 season
    skill_df = weekly_df[weekly_df['position'].isin(['QB', 'RB', 'WR', 'TE'])]
    skill_df_26 = skill_df[skill_df['season'] == 2026]
    top_vs = skill_df_26.sort_values('ppr_fast', ascending=False).groupby('opp_norm').head(5)

    teams = set(weekly_df['team_norm'].unique()) | set(weekly_df['opp_norm'].unique())
    teams = {t for t in teams if t}

    for t in teams:
        stats = {}
        y2025 = {
            "off_pass_ypa": 0.0, "off_rush_ypa": 0.0,
            "def_pass_ypa": 0.0, "def_rush_ypa": 0.0,
            "off_pass_ypa_pct": 0.0, "off_rush_ypa_pct": 0.0,
            "def_pass_ypa_pct": 0.0, "def_rush_ypa_pct": 0.0
        }

        if t in team_off_agg.index:
            orow = team_off_agg.loc[t]
            o25_pass = off_25_sum.loc[t]['overall_pass_ypa'] if t in off_25_sum.index else 0.0
            o25_rush = off_25_sum.loc[t]['overall_rush_ypa'] if t in off_25_sum.index else 0.0
            y2025['off_pass_ypa'] = float((o25_pass + orow['off_pass_ypa']) / 2 if o25_pass else orow['off_pass_ypa'])
            y2025['off_rush_ypa'] = float((o25_rush + orow['off_rush_ypa']) / 2 if o25_rush else orow['off_rush_ypa'])
            y2025['off_pass_ypa_pct'] = float(orow['oap_off_pass_26'])
            y2025['off_rush_ypa_pct'] = float(orow['oap_off_rush_26'])

        if t in team_def_agg.index:
            drow = team_def_agg.loc[t]
            d25_pass = def_25_sum.loc[t]['overall_pass_ypa'] if t in def_25_sum.index else 0.0
            d25_rush = def_25_sum.loc[t]['overall_rush_ypa'] if t in def_25_sum.index else 0.0
            y2025['def_pass_ypa'] = float((d25_pass + drow['off_pass_ypa']) / 2 if d25_pass else drow['off_pass_ypa'])
            y2025['def_rush_ypa'] = float((d25_rush + drow['off_rush_ypa']) / 2 if d25_rush else drow['off_rush_ypa'])
            y2025['def_pass_ypa_pct'] = float(drow['oap_def_pass_26'])
            y2025['def_rush_ypa_pct'] = float(drow['oap_def_rush_26'])

        stats['y2025'] = y2025

        wk1 = {}
        if t in team_off_agg.index:
            orow = team_off_agg.loc[t]
            wk1["off_pass_att"] = round(float(orow['pass_att']), 1)
            wk1["off_pass_ypa"] = float(orow['off_pass_ypa'])
            wk1["off_rush_att"] = round(float(orow['rush_att']), 1)
            wk1["off_rush_ypa"] = float(orow['off_rush_ypa'])
            wk1["off_pass_ypa_vs_opp"] = float(orow['oap_off_pass_cum'])
            wk1["off_rush_ypa_vs_opp"] = float(orow['oap_off_rush_cum'])

        if t in team_def_agg.index:
            drow = team_def_agg.loc[t]
            wk1["def_pass_att"] = round(float(drow['pass_att']), 1)
            wk1["def_pass_ypa"] = float(drow['off_pass_ypa'])
            wk1["def_rush_att"] = round(float(drow['rush_att']), 1)
            wk1["def_rush_ypa"] = float(drow['off_rush_ypa'])
            wk1["def_pass_ypa_vs_opp"] = float(drow['oap_def_pass_cum'])
            wk1["def_rush_ypa_vs_opp"] = float(drow['oap_def_rush_cum'])

        stats['wk1'] = wk1

        top_list = []
        if t in top_vs['opp_norm'].values:
            t_rows = top_vs[top_vs['opp_norm'] == t]
            for _, r in t_rows.iterrows():
                pname = r.get('player_display_name', r.get('player_name', 'Unknown'))
                if pd.isna(pname): pname = "Unknown"
                top_list.append({
                    "name": str(pname),
                    "position": str(r.get('position', '')),
                    "team": str(r.get('team_norm', '')),
                    "ppr": float(r['ppr_fast']),
                    "tds": float(r['tds_fast'])
                })
        stats['vs_allowed_top'] = top_list
        team_stats_map[t] = stats

    return team_stats_map


def check_remote_is_newer(url: str, local_path: Path) -> bool:
    try:
        req = urllib.request.Request(url, method="HEAD")
        req.add_header("User-Agent", "Mozilla/5.0")
        with urllib.request.urlopen(req, timeout=5) as resp:
            last_mod_header = resp.headers.get("Last-Modified")
            if not last_mod_header: return False
            remote_time = parsedate_to_datetime(last_mod_header).timestamp()
            local_time = local_path.stat().st_mtime
            return remote_time > local_time
    except Exception:
        return False


def fetch_and_cache_year(year: int, force_download: bool = False) -> pd.DataFrame:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    csv_file = DATA_DIR / f"stats_player_week_{year}.csv"
    url = f"https://github.com/nflverse/nflverse-data/releases/download/stats_player/stats_player_week_{year}.csv"

    if year == 2025 and csv_file.exists() and csv_file.stat().st_size > 0 and not force_download:
        return pd.read_csv(csv_file, low_memory=False)

    needs_download = force_download or not csv_file.exists() or csv_file.stat().st_size == 0

    if not needs_download and csv_file.exists():
        file_age = time.time() - csv_file.stat().st_mtime
        if file_age > CACHE_TTL_SECONDS:
            if check_remote_is_newer(url, csv_file):
                needs_download = True
            else:
                os.utime(csv_file, None)

    if needs_download:
        try:
            df = pd.read_csv(url, low_memory=False)
            if not df.empty:
                df.to_csv(csv_file, index=False)
                return df
        except Exception:
            if csv_file.exists() and csv_file.stat().st_size > 0:
                return pd.read_csv(csv_file, low_memory=False)

    if csv_file.exists() and csv_file.stat().st_size > 0:
        return pd.read_csv(csv_file, low_memory=False)

    return pd.DataFrame()


def load_weekly_game_data(force_download: bool = False) -> pd.DataFrame:
    frames = []
    for yr in [2025, 2026]:
        df = fetch_and_cache_year(yr, force_download=force_download)
        if not df.empty:
            frames.append(df)

    if not frames:
        return pd.DataFrame()

    full_df = pd.concat(frames, ignore_index=True)
    if "season_type" in full_df.columns:
        full_df = full_df[full_df["season_type"] == "REG"].copy()

    team_col = "recent_team" if "recent_team" in full_df.columns else "team"
    full_df["team_norm"] = full_df[team_col].apply(nfl_norm_team)
    opp_col = "opponent_team" if "opponent_team" in full_df.columns else "opponent"
    full_df["opp_norm"] = full_df[opp_col].apply(nfl_norm_team)

    name_col = "player_display_name" if "player_display_name" in full_df.columns else "player_name"
    full_df["name_key"] = full_df[name_col].apply(name_key)

    return full_df


def build_priors(force_download: bool = False) -> tuple[dict[str, Any], dict[str, Any]]:
    if not BOARD_PATH.exists():
        return {}, {}

    board_data = json.loads(BOARD_PATH.read_text(encoding="utf-8"))
    board_players = board_data.get("players", [])
    if not board_players:
        return {}, {}

    weekly_df = load_weekly_game_data(force_download=force_download)
    if weekly_df.empty:
        return {}, {}

    team_stats_map = build_team_stats(weekly_df)

    priors_by_player_id: dict[str, Any] = {}
    for p in board_players:
        pid = str(p["id"])
        current_team = nfl_norm_team(p.get("team"))
        p_name = p.get("name", "")
        p_nk = name_key(p_name)
        pos = p.get("position", "")

        mask = (weekly_df["name_key"] == p_nk) & (weekly_df["team_norm"] == current_team)
        if "position" in weekly_df.columns:
            mask = mask & (weekly_df["position"] == pos)

        player_games = weekly_df[mask].sort_values(["season", "week"])
        if player_games.empty:
            continue

        game_logs = []
        scores_list = []

        for _, r in player_games.iterrows():
            pass_cmp = fnum(r, "completions")
            pass_att = fnum(r, "attempts")
            pass_yds = fnum(r, "passing_yards")
            pass_tds = fnum(r, "passing_tds")
            ints = fnum(r, "passing_interceptions", "interceptions")
            rush_att = fnum(r, "carries")
            rush_yds = fnum(r, "rushing_yards")
            rush_tds = fnum(r, "rushing_tds")
            rec_yds = fnum(r, "receiving_yards")
            rec_tds = fnum(r, "receiving_tds")
            receptions = fnum(r, "receptions")
            targets = fnum(r, "targets")
            fumbles_lost = fnum(r, "rushing_fumbles_lost") + fnum(r, "receiving_fumbles_lost") + fnum(r, "sack_fumbles_lost")
            twopt = fnum(r, "passing_2pt_conversions") + fnum(r, "rushing_2pt_conversions") + fnum(r, "receiving_2pt_conversions")

            has_activity = (
                pass_att > 0 or pass_yds != 0 or pass_tds != 0 or rush_att > 0
                or rush_yds != 0 or rush_tds != 0 or targets > 0 or receptions != 0 or rec_yds != 0
            )
            if not has_activity and pos != "QB":
                continue

            fpts = game_line_points(pass_yds, pass_tds, ints, rush_yds, rush_tds, rec_yds, rec_tds, receptions, fumbles_lost, twopt)
            scores_list.append(fpts)

            game_logs.append({
                "season": int(r.get("season", 0)),
                "week": int(r.get("week", 0)),
                "team": current_team,
                "opponent": nfl_norm_team(r.get("opp_norm")),
                "ppr": fpts,
                "tds": round(pass_tds + rush_tds + rec_tds, 1),
                "pass_cmp": int(pass_cmp),
                "pass_att": int(pass_att),
                "pass_yds": round(pass_yds, 1),
                "pass_td": int(pass_tds),
                "int": int(ints),
                "rush_att": int(rush_att),
                "rush_yds": round(rush_yds, 1),
                "rush_td": int(rush_tds),
                "rec": int(receptions),
                "tgt": int(targets),
                "rec_yds": round(rec_yds, 1),
                "rec_td": int(rec_tds),
            })

        if scores_list:
            priors_by_player_id[pid] = {
                "id": int(pid),
                "name": p_name,
                "team": current_team,
                "position": pos,
                "n_games": len(scores_list),
                "mean_pts": round(float(np.mean(scores_list)), 2),
                "min_pts": round(float(np.min(scores_list)), 2),
                "max_pts": round(float(np.max(scores_list)), 2),
                "scores": scores_list,
                "game_logs": game_logs,
            }

    PRIORS_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_players": len(priors_by_player_id),
        "byId": priors_by_player_id,
        "teams": team_stats_map,
    }
    PRIORS_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    return priors_by_player_id, team_stats_map


def load_priors(force_download: bool = False) -> tuple[dict[str, Any], dict[str, Any]]:
    return build_priors(force_download=force_download)


# ══════════════════════════════════════════════════════════════════════════════
# 6. PLAYER DISTRIBUTIONS / PDFs  (was generate_pdfs.py)
# ══════════════════════════════════════════════════════════════════════════════

N_KNOTS = 9
POS_CV = {"QB": 0.32, "RB": 0.42, "WR": 0.46, "TE": 0.50}
TEMPLATES = {
    "QB": [0.18, 0.35, 0.55, 0.78, 1.00, 0.82, 0.52, 0.28, 0.16],
    "RB": [0.28, 0.52, 0.82, 1.00, 0.80, 0.52, 0.30, 0.15, 0.10],
    "WR": [0.28, 0.50, 0.78, 1.00, 0.82, 0.55, 0.32, 0.16, 0.10],
    "TE": [0.34, 0.62, 1.00, 0.82, 0.52, 0.28, 0.14, 0.08, 0.06],
}


# ── Prior qualification ──

def has_sufficient_priors(p: dict) -> bool:
    """
    Checks if player has at least 8 games recorded across 2025 and 2026 with
    their current team that yielded MORE than 0 fantasy points.
    """
    fit = p.get("fit2025") or {}
    scores = fit.get("scores") or []
    same_team = fit.get("team") == p.get("team")
    if not same_team:
        return False
    pos_games = [s for s in scores if s > 0.0]
    return len(pos_games) >= 8


# ── Core math & PDF shapers ──

def summarize(mn, mx, knots):
    n = len(knots)
    dx = (mx - mn) / (n - 1)
    ys = [max(0.0, float(y)) for y in knots]
    if all(y <= 1e-12 for y in ys):
        ys = [1.0] * n
    mass = moment = m2 = 0.0
    for i in range(n - 1):
        x0 = mn + i * dx
        y0, y1 = ys[i], ys[i + 1]
        dy = y1 - y0
        mass += dx * (y0 + y1) / 2
        moment += dx * (x0 * y0 + (x0 * dy + dx * y0) / 2 + (dx * dy) / 3)
        m2 += dx * (
            x0 * x0 * y0
            + (x0 * x0 * dy + 2 * x0 * dx * y0) / 2
            + (2 * x0 * dx * dy + dx * dx * y0) / 3
            + (dx * dx * dy) / 4
        )
    if mass <= 1e-12:
        return None
    mean = moment / mass
    var = max(0.0, m2 / mass - mean * mean)
    return {"mean": mean, "sd": math.sqrt(var), "mass": mass}


def peak_norm(knots):
    pk = max(knots) if knots else 0
    if pk <= 1e-9:
        return [1.0] * len(knots)
    return [round(max(0.0, y) / pk, 3) for y in knots]


def tilt_to_mean(mn, mx, knots, target):
    n = len(knots)
    span = mx - mn
    xmid = (mn + mx) / 2
    grid = [mn + i * span / (n - 1) for i in range(n)]
    base = [max(0.0, y) for y in knots]
    if all(y <= 1e-12 for y in base):
        return [1.0] * n
    target = min(mx - span * 1e-4, max(mn + span * 1e-4, target))

    def tilted(lam):
        return [y * math.exp(lam * (x - xmid) / span) for y, x in zip(base, grid)]

    def mean_of(lam):
        s = summarize(mn, mx, tilted(lam))
        return None if s is None else s["mean"]

    untilted = mean_of(0)
    if untilted is None:
        return peak_norm(base)
    if abs(untilted - target) < 0.04:
        return peak_norm(base)
    lo, hi = -30.0, 30.0
    m_lo, m_hi = mean_of(lo), mean_of(hi)
    if m_lo is not None and target <= m_lo:
        return peak_norm(tilted(lo))
    if m_hi is not None and target >= m_hi:
        return peak_norm(tilted(hi))
    for _ in range(48):
        mid = (lo + hi) / 2
        m = mean_of(mid)
        if m is None:
            break
        if m < target:
            lo = mid
        else:
            hi = mid
    return peak_norm(tilted((lo + hi) / 2))


def smooth(knots, passes=2, strength=0.45):
    n = len(knots)
    cur = [max(0.0, y) for y in knots]
    for _ in range(passes):
        nxt = cur[:]
        for i in range(1, n - 1):
            nxt[i] = max(0.0, cur[i] + strength * ((cur[i - 1] + cur[i + 1]) / 2 - cur[i]))
        cur = nxt
    return [round(y, 3) for y in cur]


def silverman_h(values):
    n = len(values)
    if n < 2:
        return 1.0
    sd = statistics.stdev(values)
    sv = sorted(values)

    def q(p):
        pos = (len(sv) - 1) * p
        b = int(pos)
        r = pos - b
        return sv[b] + r * (sv[b + 1] - sv[b]) if b + 1 < len(sv) else sv[b]

    iqr = q(0.75) - q(0.25)
    spread = min(sd, iqr / 1.349) if iqr > 1e-6 else sd
    safe = spread if spread > 1e-6 else max(sd, 1e-6)
    return max(0.9 * safe * (n ** -0.2), 1e-3)


def kde_knots(scores, mn, mx, n=N_KNOTS):
    if not scores:
        return None
    h = silverman_h(scores)
    knots = []
    for i in range(n):
        x = mn + i * (mx - mn) / (n - 1)
        dens = sum(math.exp(-0.5 * ((x - s) / h) ** 2) for s in scores)
        knots.append(dens / (len(scores) * h * math.sqrt(2 * math.pi)))
    return knots


# ── Player evaluators ──

def num(x):
    return None if x is None or (isinstance(x, float) and math.isnan(x)) else float(x)


def proj_parts(p):
    espn_val = num(p.get("espn"))
    fp = num((p.get("fp") or {}).get("ppr"))

    # If early week override populated an ESPN score, average it with FP if available
    if espn_val is not None and espn_val > 0.0:
        if fp is not None and fp > 0.0:
            avg_pts = (espn_val + fp) / 2.0
            model = avg_pts
            fp = avg_pts
        else:
            model = espn_val
            fp = espn_val
    else:
        model = num((p.get("model") or {}).get("points"))

    # Extract combined 2025+2026 historical mean ONLY if priors qualify
    y = None
    if has_sufficient_priors(p):
        fit = p.get("fit2025") or {}
        y = num(fit.get("mean"))
        if y is None:
            y = num((p.get("y2025") or {}).get("ppr_g"))

    roto = num(p.get("projectedPoints"))
    if fp is not None and fp < 1.0:
        fp = None
    if model is not None and model < 1.0:
        model = None
    return model, fp, y, roto


def is_backup_qb(p, by_team):
    if p["position"] != "QB":
        return False
    mates = [x for x in by_team[p["team"]] if x["position"] == "QB"]
    if len(mates) < 2:
        return False
    def mu_est(x):
        m, f, y, r = proj_parts(x)
        vals = [v for v in (m, f) if v is not None]
        return max(vals) if vals else (y or r or 0)
    return mu_est(p) < max(mu_est(x) for x in mates) - 4


def injured(p):
    des = ((p.get("injury") or {}) or {}).get("designation")
    return des in ("Q", "O", "D", "IR")


def rush_per_game(p):
    """Computes rush attempts per game across the combined 2025+2026 dataset."""
    if has_sufficient_priors(p):
        fit = p.get("fit2025") or {}
        g = fit.get("n") or len(fit.get("scores") or [])
        rush_att = fit.get("rush_att")
        if rush_att is None:
            rush_att = (p.get("y2025") or {}).get("rush_att")
        if g and rush_att is not None:
            return float(rush_att) / float(g)

    fp = p.get("fp") or {}
    return fp.get("rush_att") or 0.0


def target_mean(p, backup_qb):
    """
    Blends 45% model, 45% FantasyPros, and 10% combined 2025+2026 historical average
    when priors qualify. Otherwise splits 50/50 model/FP.
    """
    model, fp, y, roto = proj_parts(p)
    vals, wts = [], []
    if model is not None:
        vals.append(model); wts.append(0.45)
    if fp is not None:
        vals.append(fp); wts.append(0.45)
    if y is not None and not backup_qb:
        vals.append(y); wts.append(0.10 if vals else 1.0)
    if not vals and roto is not None:
        vals.append(roto); wts.append(1.0)
    if not vals:
        vals.append(8.0); wts.append(1.0)
    mu = sum(v * w for v, w in zip(vals, wts)) / sum(wts)
    if backup_qb:
        mu = min(mu, 4.5)
    if injured(p):
        low = min(v for v in (model, fp, mu) if v is not None)
        mu = 0.65 * mu + 0.35 * low
    return mu


def hist_sd(p, mu, pos):
    """
    Computes empirical std from the full combined 2025+2026 set (including 0s)
    if qualified. Otherwise uses positional CV estimates.
    """
    if has_sufficient_priors(p):
        scores = (p.get("fit2025") or {}).get("scores") or []
        if len(scores) >= 2:
            return 0.80 * statistics.stdev(scores)
    return POS_CV.get(pos, 0.44) * max(mu, 4.0)


def hist_range(p):
    """
    Returns empirical min and max from the full combined set if qualified.
    """
    if has_sufficient_priors(p):
        scores = (p.get("fit2025") or {}).get("scores") or []
        if scores:
            return min(scores), max(scores)

    fit = p.get("fit2025") or {}
    rng = p.get("range") or {}
    worst = num(fit.get("min"))
    best = num(fit.get("max"))
    if worst is None:
        worst = num((rng.get("worst") or {}).get("ppr"))
    if best is None:
        best = num((rng.get("best") or {}).get("ppr"))
    return worst, best


def bounds(p, mu, sd, backup_qb, committee_backup, featured_rb):
    pos = p["position"]
    worst, best = hist_range(p)
    zmin = mu - 2.0 * sd
    zmax = mu + 2.6 * sd
    mn = zmin
    if worst is not None:
        mn = min(mn, worst)
    mn = max(0.0, mn)
    if pos == "QB" and not backup_qb and not injured(p) and mu >= 14:
        mn = max(mn, 4.0)
        mn = max(mn, mu - 2.5 * sd)
    if backup_qb or injured(p):
        mn = 0.0
    if committee_backup:
        mn = min(mn, 1.0)

    mx = zmax
    if best is not None:
        if best > mu + 3.2 * sd:
            mx = max(zmax, mu + 2.6 * sd)
        else:
            mx = max(mx, best)

    # Ceiling stretch based on the combined 2025+2026 mean
    ymean = None
    if has_sufficient_priors(p):
        fit = p.get("fit2025") or {}
        ymean = num(fit.get("mean"))
        if ymean is None:
            ymean = num((p.get("y2025") or {}).get("ppr_g"))

    if ymean is not None and mu - ymean > 3:
        mx = max(mx, mu + 2.8 * sd)
    if featured_rb:
        mx = max(mx, mu + 2.8 * sd)
    if backup_qb:
        mx = min(max(mx, 16.0), 22.0)
    if committee_backup:
        mx = min(mx, mu + 2.3 * sd)

    mn = round(max(0.0, mn) * 2) / 2  # 0.5 grid
    mx = round(max(mn + 8, mx))
    if mx > mn:
        loc = (mu - mn) / (mx - mn)
        if loc > 0.58:
            mx = round(mn + (mu - mn) / 0.45)
        if loc < 0.28 and pos == "QB" and not backup_qb:
            mn = max(0.0, round((mu - 0.48 * (mx - mn)) * 2) / 2)
    return mn, mx


def apply_role(knots, p, backup_qb, committee_backup, dual_threat, injured_flag):
    n = len(knots)
    out = knots[:]
    if dual_threat:
        out = [y * math.exp(0.45 * (i / (n - 1) - 0.35)) for i, y in enumerate(out)]
    if committee_backup:
        out = [y * math.exp(-1.05 * (i / (n - 1))) for i, y in enumerate(out)]
        out[0] = max(out[0], 0.65 * max(out))
    if backup_qb or (injured_flag and p["position"] == "QB"):
        out = [0.95, 0.55, 0.62, 0.88, 0.80, 0.62, 0.28, 0.12, 0.08]
    elif injured_flag:
        pk = max(out) or 1
        out[0] = max(out[0], 0.55 * pk)
    return out


def make_pdf(p, mu, sd, backup_qb, committee_backup, featured_rb, dual_threat):
    mn, mx = bounds(p, mu, sd, backup_qb, committee_backup, featured_rb)
    fit = p.get("fit2025") or {}
    scores = fit.get("scores") or []

    # Use Gaussian KDE over the combined set (including 0s) only if >= 8 games with > 0 points
    if has_sufficient_priors(p) and not backup_qb:
        knots = kde_knots(scores, mn, mx)
    else:
        knots = TEMPLATES.get(p["position"], TEMPLATES["WR"])[:]

    knots = apply_role(knots, p, backup_qb, committee_backup, dual_threat, injured(p))
    knots = tilt_to_mean(mn, mx, knots, mu)
    knots = smooth(knots)
    knots = peak_norm(knots)
    knots = tilt_to_mean(mn, mx, knots, mu)
    knots = [round(y, 3) for y in knots]
    s = summarize(mn, mx, knots)
    return mn, mx, knots, s


# ── Orchestration ──

def generate_all_pdfs(board: dict, user_by: dict = None) -> dict:
    if user_by is None:
        user_by = {}

    by_team = {}
    for p in board.get("players", []):
        by_team.setdefault(p["team"], []).append(p)

    rb_rank = {}
    for team, plist in by_team.items():
        rbs = [x for x in plist if x["position"] == "RB"]
        def rb_mu(x):
            return target_mean(x, False)
        rbs.sort(key=rb_mu, reverse=True)
        for i, r in enumerate(rbs):
            rb_rank[r["id"]] = (i, len(rbs), rb_mu(r))

    by_id = {}
    n_user = n_gen = n_kde = 0
    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    for p in board.get("players", []):
        pid = str(p["id"])

        if pid in user_by:
            rec = dict(user_by[pid])
            rec["source"] = rec.get("source") or "user"
            by_id[pid] = rec
            n_user += 1
            continue

        backup_qb = is_backup_qb(p, by_team)
        rr = rb_rank.get(p["id"])
        committee_backup = bool(rr and rr[1] >= 2 and rr[0] >= 1)
        featured_rb = False

        if p["position"] == "RB" and rr:
            if rr[1] == 1:
                featured_rb = True
            elif rr[0] == 0:
                others = [
                    rb_rank[x["id"]][2]
                    for x in by_team[p["team"]]
                    if x["position"] == "RB" and x["id"] != p["id"]
                ]
                if others and rr[2] >= max(others) + 3:
                    featured_rb = True

        qualified = has_sufficient_priors(p)
        dual = p["position"] == "QB" and rush_per_game(p) >= 5.5 and not backup_qb
        mu = target_mean(p, backup_qb)
        sd = hist_sd(p, mu, p["position"])
        mn, mx, knots, s = make_pdf(p, mu, sd, backup_qb, committee_backup, featured_rb, dual)

        if qualified and not backup_qb:
            n_kde += 1
            mode_tag = f"[KDE {len(p.get('fit2025', {}).get('scores', []))}g]"
        else:
            mode_tag = "[TMPL]"

        by_id[pid] = {
            "min": mn,
            "max": mx,
            "knots": knots,
            "name": p["name"],
            "team": p["team"],
            "position": p["position"],
            "updatedAt": now,
            "source": "algorithm",
        }
        n_gen += 1
        print(f"  GEN {p['position']:2} {p['team']:3} {p['name'][:22]:22} "
              f"μ→{s['mean']:.1f} (tgt {mu:.1f}) min={mn:.1f} max={mx:.1f} sd={s['sd']:.1f} {mode_tag}"
              f"{' Q' if injured(p) else ''}{' BQ' if backup_qb else ''}"
              f"{' CBup' if committee_backup else ''}{' feat' if featured_rb else ''}"
              f"{' DT' if dual else ''}")

    print(f"\nPDF Generation Summary: {n_kde} KDE fitted, {n_gen - n_kde} template generated, {n_user} user locked.")
    payload = {
        "version": 1,
        "season": board.get("season", datetime.now().year),
        "updatedAt": now,
        "note": "User PDFs combined with algorithm-generated priors. Load in the board UI to view/edit.",
        "byId": by_id,
    }
    return payload


def generate_pdfs_main():
    """Standalone PDF run from the existing board.json (the `pdfs` command)."""
    if not BOARD_PATH.exists():
        print(f"Error: Board file not found at {BOARD_PATH}")
        return

    board = json.loads(BOARD_PATH.read_text())

    user_by = {}
    if USER_PROJ_PATH.exists():
        try:
            user = json.loads(USER_PROJ_PATH.read_text())
            user_by = {str(k): v for k, v in user.get("byId", {}).items()}
        except json.JSONDecodeError:
            print(f"Warning: Could not parse user file at {USER_PROJ_PATH}. Treating as empty.")

    print(f"Starting PDF Generation...")
    payload = generate_all_pdfs(board, user_by)

    PROJECTIONS_PATH.parent.mkdir(parents=True, exist_ok=True)
    PROJECTIONS_PATH.write_text(json.dumps(payload, indent=2))

    print(f"\nWrote {PROJECTIONS_PATH}")
    print(f"  user-provided={len(user_by)} generated={len(payload['byId']) - len(user_by)} total={len(payload['byId'])}")


# ══════════════════════════════════════════════════════════════════════════════
# 7. BOARD BUILD / ORCHESTRATOR  (was build_board.py)
# ══════════════════════════════════════════════════════════════════════════════

def make_finder(recs):
    """Creates a robust lookup dictionary for merging player data sources."""
    lookup = {}
    for r in recs:
        key = (name_key(r['name']), r['position'])
        lookup[key] = r
    return lambda name, pos: lookup.get((name_key(name), pos))


def parse_opp_token(token: str, player_team: str):
    """Parses '@ BAL' or 'vs. SEA' into opponent abbreviation and home boolean."""
    if not token or str(token).strip() in {"", "—", "–", "-"}:
        return None, None
    s = str(token).replace("\x97", "").replace("—", "").strip()
    home = None
    if s.lower().startswith("vs"):
        home = True
        s = re.sub(r"^vs\.?\s*", "", s, flags=re.I)
    elif s.startswith("@"):
        home = False
        s = s[1:].strip()

    opp = norm_team(s)
    if opp not in TEAM_NAMES:
        return None, home
    return standardize_team(opp), home


def fp_line_points(row: dict) -> float:
    """League points for a FantasyPros projection line (no 2-pt conversions)."""
    if not row:
        return 0.0
    py = float(row.get("pass_yds") or 0)
    ptd = float(row.get("pass_td") or 0)
    ints = float(row.get("int") or 0)
    ry = float(row.get("rush_yds") or 0)
    rtd = float(row.get("rush_td") or 0)
    recy = float(row.get("rec_yds") or 0)
    rectd = float(row.get("rec_td") or 0)
    rec = float(row.get("rec") or 0)
    fl = float(row.get("fl") or 0)

    pts = (0.05 * py + 4 * ptd - ints +
           0.1 * ry + 6 * rtd +
           0.1 * recy + 6 * rectd +
           rec - fl)
    return round(pts, 1)


def format_fp_box(row: dict) -> dict:
    if not row:
        return None
    box = row.copy()
    box["ppr"] = fp_line_points(row)
    return box


def build_board(force_download: bool = False):
    print("Loading data sources...")
    config = load_player_config()
    early_wk = int(config.get("early_wk_ovrd") or 0)

    try:
        raw_roto = load_roto_projections()
    except Exception as e:
        print(f"Error loading RotoBaller data: {e}")
        return

    players = filter_and_rank_players(raw_roto, config)
    # Check if early week override is active
    espn_proj_map = {}
    if early_wk > 0:
        print(f"[Override Active] early_wk_ovrd is set to Week {early_wk}.")
        try:
            espn_proj_map = fetch_espn_projections(week=early_wk)
        except Exception as e:
            print(f"Warning: Failed to fetch ESPN projections: {e}")
    else:
        print("Standard run: early_wk_ovrd is 0. Using FFA and FantasyPros sources.")

    model_data = load_model_projections()
    fp_data = load_fp_projections()

    find_model = make_finder(model_data)
    find_fp = make_finder(fp_data)

    inferred_games = set()
    included_players = []

    print(f"Merging {len(players)} eligible players...")
    for p in players:
        team = standardize_team(norm_team(p.get("team")))
        opp, home = parse_opp_token(p.get("opponent"), team)

        if team and opp:
            away_t = opp if home else team
            home_t = team if home else opp
            inferred_games.add((away_t, home_t))

        inj = p.get("injury") if isinstance(p.get("injury"), dict) else None

        mrow = find_model(p["name"], p["position"])
        model_dict = None
        if mrow and mrow.get("points") is not None:
            model_dict = {
                "points": mrow["points"],
                "sd_points": mrow["sd_points"],
                "floor": mrow["floor"],
                "ceiling": mrow["ceiling"],
            }

        fprow = find_fp(p["name"], p["position"])
        fp_dict = format_fp_box(fprow)

        # ESPN score if early override is triggered
        espn_score = espn_proj_map.get(name_key(p["name"]))

        included_players.append({
            "id": p.get("id"),
            "name": clean_name(p["name"]),
            "team": team,
            "position": p["position"],
            "ranking": p.get("ranking"),
            "pos_rank": p.get("pos_rank"),
            "projectedPoints": round(float(p.get("projectedPoints") or 0.0), 1),
            "opponent": opp,
            "home": home,
            "injury": {"designation": inj.get("designation")} if inj and inj.get("designation") else None,
            "model": model_dict,
            "fp": fp_dict,
            "espn": espn_score,
            "y2025": None,
            "wk1": None,
            "range": None,
            "fit2025": None,
            "vs_opp": None
        })

    teams_out = {}
    for abbr, name in TEAM_NAMES.items():
        if abbr == "JAC":
            continue
        teams_out[abbr] = {
            "abbr": abbr,
            "name": name,
            "record": "0-0",
            "y2025": {},
            "wk1": None,
            "vs_allowed_top": []
        }

    games_out = []
    for i, (away, home) in enumerate(sorted(inferred_games)):
        games_out.append({
            "id": f"game_{i}",
            "away": away,
            "home": home,
            "gametime": "13:00",
            "weekday": "Sunday",
            "spread": 0.0,
            "favorite": None,
            "total": 45.0
        })

    payload = {
        "pos_limits": config.get("pos_limits", {}),
        "teams": teams_out,
        "games": games_out,
        "players": included_players,
    }

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    BOARD_PATH.write_text(json.dumps(payload, indent=2, allow_nan=False), encoding="utf-8")
    print(f"Wrote initial board to {BOARD_PATH.name} (Players: {len(included_players)})")

    # ── Step 2: Extract & Merge Historical Priors ──
    print("\nExtracting historical priors via get_priors.py...")
    priors_map, team_stats_map = build_priors(force_download=force_download)

    for abbr, team_dict in payload["teams"].items():
        ts = team_stats_map.get(abbr, {})
        team_dict["y2025"] = ts.get("y2025", {})
        team_dict["wk1"] = ts.get("wk1")
        team_dict["vs_allowed_top"] = ts.get("vs_allowed_top", [])

    n_priors_attached = 0
    for p in included_players:
        pid_str = str(p["id"])
        prior = priors_map.get(pid_str)
        if not prior:
            continue

        n_priors_attached += 1
        opp = p.get("opponent")

        game_logs = prior.get("game_logs", [])
        total_rush_att = sum(g.get("rush_att", 0) for g in game_logs)

        # Attach Current/Most Recent Boxscore
        if game_logs:
            p["wk1"] = game_logs[-1]

        p["fit2025"] = {
            "team": prior["team"],
            "scores": prior["scores"],
            "min": prior["min_pts"],
            "max": prior["max_pts"],
            "mean": prior["mean_pts"],
            "n": prior["n_games"],
            "rush_att": total_rush_att,
        }

        p["y2025"] = {
            "ppr_g": prior["mean_pts"],
            "games": prior["n_games"],
            "rush_att": total_rush_att,
        }

        if game_logs:
            best_game = max(game_logs, key=lambda g: g["ppr"])
            worst_game = min(game_logs, key=lambda g: g["ppr"])
            p["range"] = {
                "best": best_game,
                "worst": worst_game,
                "n": prior["n_games"],
            }
        else:
            p["range"] = None

        if opp:
            matchups = [g for g in game_logs if g["opponent"] == opp]
            if matchups:
                p["vs_opp"] = matchups

    BOARD_PATH.write_text(json.dumps(payload, indent=2, allow_nan=False), encoding="utf-8")
    print(f"Attached historical prior data to {n_priors_attached} players and re-saved {BOARD_PATH.name}.")

    # ── Step 3: Generate Algorithm PDFs ──
    print("\nTriggering PDF Generation...")
    user_by = {}
    if USER_PROJ_PATH.exists():
        try:
            user_by = json.loads(USER_PROJ_PATH.read_text()).get("byId", {})
        except Exception:
            pass

    pdf_payload = generate_all_pdfs(payload, user_by)
    PROJECTIONS_PATH.write_text(json.dumps(pdf_payload, indent=2))
    print("Pipeline complete.")


# ══════════════════════════════════════════════════════════════════════════════
# 8. LIVE DRAFT UPDATE  (was update_board.py)
# ══════════════════════════════════════════════════════════════════════════════

def strip_rtf(text: str) -> str:
    """Removes RTF formatting overhead to extract the raw HTML inside."""
    if "{\\rtf" not in text:
        return text

    # Extract hex escapes (e.g. \'<hex>)
    text = re.sub(r"\\'([0-9a-fA-F]{2})", lambda m: chr(int(m.group(1), 16)), text)
    # Strip RTF commands \command[optional_number][optional_space]
    text = re.sub(r"\\[a-zA-Z]+(-?\d+)?( )?", "", text)
    # Strip RTF braces
    text = text.replace("{", "").replace("}", "")
    # Unescape basic sequences
    text = text.replace("\\~", " ").replace("\\-", "-").replace("\\_", "-").replace("\\\\", "\\")
    return text


def parse_draft_html(html_str: str) -> dict[str, dict]:
    """
    Parses table rows from the live draft HTML.
    Returns a dict mapping draft_name_key -> { 'rank': int, 'proj': float }

    NOTE ON EXTENDING FOR SEASON AVERAGE:
    The cell immediately following the projection contains the season average points:
        <td class="... text-right text-muted-foreground">28.95</td>
    To extract season average in the future:
        avg_match = re.search(r'<span class="font-body text-sm text-foreground">[\d\.]+</span>\s*</td>\s*<td[^>]*text-muted-foreground[^>]*>([\d\.]+)</td>', row, re.I)
        if avg_match:
            season_avg = float(avg_match.group(1))
    """
    players_found = {}
    rows = re.findall(r'<tr[^>]*>(.*?)</tr>', html_str, flags=re.I | re.DOTALL)

    for row in rows:
        # 1. Extract Player Name
        name_match = re.search(
            r'<span class="font-bold[^"]*">([^<]+)</span>',
            row,
            flags=re.I
        )
        if not name_match:
            continue
        raw_name = html.unescape(name_match.group(1)).strip()
        key = draft_name_key(raw_name)

        # 2. Extract Draft Rank
        # Pattern: <td ... text-muted-foreground text-right">2</td>
        rank_match = re.search(
            r'<td[^>]*text-muted-foreground\s+text-right[^>]*>\s*(\d+)\s*</td>',
            row,
            flags=re.I
        )
        if not rank_match:
            # Fallback for reversed class order
            rank_match = re.search(
                r'<td[^>]*text-right\s+text-muted-foreground[^>]*>\s*(\d+)\s*</td>',
                row,
                flags=re.I
            )

        # 3. Extract Projected Points
        # Pattern: <span class="font-body text-sm text-foreground">27.2</span>
        proj_match = re.search(
            r'<span class="font-body\s+text-sm\s+text-foreground">([\d\.]+)</span>',
            row,
            flags=re.I
        )

        rank_val = int(rank_match.group(1)) if rank_match else None
        proj_val = round(float(proj_match.group(1)), 1) if proj_match else None

        if rank_val is not None or proj_val is not None:
            players_found[key] = {
                "name": raw_name,
                "rank": rank_val,
                "proj": proj_val,
            }

    return players_found


def update_board():
    if not BOARD_PATH.exists():
        print(f"Error: Board file not found at {BOARD_PATH}")
        return

    if not DRAFT_RTF_PATH.exists():
        print(f"Error: Draft HTML RTF not found at {DRAFT_RTF_PATH}")
        return

    print(f"Loading {BOARD_PATH.name}...")
    try:
        board = json.loads(BOARD_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        print(f"Error parsing board.json: {e}")
        return

    print(f"Parsing raw HTML from {DRAFT_RTF_PATH.name}...")
    raw_text = DRAFT_RTF_PATH.read_text(encoding="utf-8", errors="replace")
    html_content = strip_rtf(raw_text)
    scraped_data = parse_draft_html(html_content)
    print(f"Parsed {len(scraped_data)} players from draft page HTML.")

    players = board.get("players", [])
    updated_count = 0
    unchanged_count = 0
    missing_count = 0

    print("\nUpdating board players:")
    for p in players:
        key = draft_name_key(p.get("name", ""))
        scraped = scraped_data.get(key)

        if not scraped:
            missing_count += 1
            continue

        old_rank = p.get("ranking")
        old_proj = p.get("projectedPoints")
        new_rank = scraped.get("rank")
        new_proj = scraped.get("proj")

        rank_changed = new_rank is not None and new_rank != old_rank
        proj_changed = new_proj is not None and new_proj != old_proj

        if rank_changed or proj_changed:
            changes = []
            if rank_changed:
                changes.append(f"Rank: {old_rank} -> {new_rank}")
                p["ranking"] = new_rank
            if proj_changed:
                changes.append(f"Proj: {old_proj} -> {new_proj}")
                p["projectedPoints"] = new_proj

            print(f"  [UPDATED] {p['name']:<22} ({p['position']} - {p['team']}): {', '.join(changes)}")
            updated_count += 1
        else:
            unchanged_count += 1

    # Recalculate Positional Ranks (pos_rank) based on updated rankings
    by_pos = {}
    for p in players:
        by_pos.setdefault(p["position"], []).append(p)

    for pos, plist in by_pos.items():
        plist.sort(key=lambda x: x.get("ranking") if x.get("ranking") is not None else 9999)
        for i, p in enumerate(plist, start=1):
            p["pos_rank"] = i

    # Save back to board.json
    BOARD_PATH.write_text(json.dumps(board, indent=2, allow_nan=False), encoding="utf-8")
    print(f"\nDone! {updated_count} updated, {unchanged_count} unchanged, {missing_count} not in draft HTML (kept baseline).")
    print(f"Updated {BOARD_PATH}.")


# ══════════════════════════════════════════════════════════════════════════════
# 9. POST-DRAFT PORTFOLIO SIMULATION  (was project_results.py)
# ══════════════════════════════════════════════════════════════════════════════

# Sim constants (mirroring simCore.js / projDist.js)
MAX_TAIL_FRAC = 0.05
TAIL_WIDTH_CAP = 6.0
TAIL_WIDTH_SPAN_FRAC = 0.15
INV_CDF_STEPS = 256


# ── Config loaders ──

def load_sim_config() -> int:
    """Reads N_SIM_RESULTS from simConfig.js, falling back to 100,000."""
    if not SIM_CONFIG_PATH.exists():
        return 100_000
    text = SIM_CONFIG_PATH.read_text(encoding="utf-8")
    m = re.search(r"N_SIM_RESULTS\s*=\s*([0-9_]+)", text)
    if m:
        return int(m.group(1).replace("_", ""))
    return 100_000


def load_player_list_config() -> dict:
    """
    Extracts locked_scores (supporting player names or IDs) and exclusions
    directly from playerList.js.
    """
    default_cfg = {"locked_scores": {}, "exclude": []}
    if not PLAYER_LIST_CONFIG.exists():
        return default_cfg

    text = PLAYER_LIST_CONFIG.read_text(encoding="utf-8")

    locked = {}
    m_lock = re.search(r"locked_scores\s*:\s*\{([^}]+)\}", text, flags=re.DOTALL)
    if m_lock:
        # Match 'Player Name': 31.2 or "Player Name": 31.2 or 19801: 31.2
        entries = re.findall(r'["\']?([^"\'\n\r:]+?)["\']?\s*:\s*([0-9.]+)', m_lock.group(1))
        for k, v in entries:
            key_clean = k.strip()
            if key_clean:
                locked[key_clean] = float(v)

    exclude = []
    m_exc = re.search(r"exclude\s*:\s*\[([^\]]+)\]", text, flags=re.DOTALL)
    if m_exc:
        items = re.findall(r'["\']([^"\']+)["\']', m_exc.group(1))
        exclude = [item.strip() for item in items if item.strip()]

    return {"locked_scores": locked, "exclude": exclude}


# ── Correlation & copula math (mirroring simCore.js) ──

BASE_SAME = {"QB-WR": 0.15, "QB-TE": 0.15, "QB-RB": 0.05}
BASE_OPP = {"QB-QB": 0.20}

ROLE_DELTA = [
    ("QB", "PASS1", "same", 0.25),
    ("RUSH_QB", "PASS1", "same", 0.13),
    ("QB", "PASS2", "same", 0.15),
    ("RUSH_QB", "PASS2", "same", 0.15),
    ("RUSH_QB", "WR", "same", 0.05),
    ("PASS1", "PASS1", "opp", 0.18),
    ("QB", "PASS1", "opp", 0.08),
    ("RUSH_QB", "PASS1", "opp", 0.05),
]


def get_role_delta(pos_a: str, role_a: str | None, pos_b: str, role_b: str | None, scope: str) -> float:
    if role_a is None and role_b is None:
        return 0.0
    key_a = role_a or pos_a
    key_b = role_b or pos_b
    for ra, rb, sc, delta in ROLE_DELTA:
        if sc != scope:
            continue
        if (key_a == ra and key_b == rb) or (key_a == rb and key_b == ra):
            return delta
    return 0.0


def build_correlations(player_list: list[dict], team_to_opp: dict[str, str]) -> list[tuple[int, int, float]]:
    corr = {}

    def add_corr(i: int, j: int, rho: float):
        if i == j:
            return
        key = (min(i, j), max(i, j))
        prev = corr.get(key, 0.0)
        if abs(rho) >= abs(prev):
            corr[key] = rho

    by_team: dict[str, list[dict]] = {}
    for p in player_list:
        t = p.get("team") or ""
        by_team.setdefault(t, []).append(p)

    for plist in by_team.values():
        qbs = [p for p in plist if p.get("position") == "QB"]
        qbs.sort(key=lambda p: p.get("points", 0.0), reverse=True)
        recs = [p for p in plist if p.get("position") in {"WR", "TE"}]
        rbs = [p for p in plist if p.get("position") == "RB"]
        if not qbs:
            continue

        q = qbs[0]
        q_role = q.get("role")

        for r in recs:
            base = BASE_SAME.get(f"QB-{r['position']}", 0.0)
            delta = get_role_delta("QB", q_role, r["position"], r.get("role"), "same")
            rho = max(-0.95, min(0.95, base + delta))
            if rho != 0.0:
                add_corr(q["local_idx"], r["local_idx"], rho)

        for rb in rbs:
            base = BASE_SAME.get("QB-RB", 0.0)
            delta = get_role_delta("QB", q_role, "RB", rb.get("role"), "same")
            rho = max(-0.95, min(0.95, base + delta))
            if rho != 0.0:
                add_corr(q["local_idx"], rb["local_idx"], rho)

    seen_games = set()
    for team, opp in team_to_opp.items():
        game_key = tuple(sorted([team, opp]))
        if game_key in seen_games:
            continue
        seen_games.add(game_key)

        ti = by_team.get(team, [])
        oi = by_team.get(opp, [])

        ti_qbs = [p for p in ti if p.get("position") == "QB"]
        ti_qbs.sort(key=lambda p: p.get("points", 0.0), reverse=True)
        oi_qbs = [p for p in oi if p.get("position") == "QB"]
        oi_qbs.sort(key=lambda p: p.get("points", 0.0), reverse=True)

        ti_starter_idx = ti_qbs[0]["local_idx"] if ti_qbs else -1
        oi_starter_idx = oi_qbs[0]["local_idx"] if oi_qbs else -1

        for a in ti:
            for b in oi:
                base = 0.0
                if a["position"] == "QB" and b["position"] == "QB" and a["local_idx"] == ti_starter_idx and b["local_idx"] == oi_starter_idx:
                    base = BASE_OPP.get("QB-QB", 0.0)
                delta = get_role_delta(a["position"], a.get("role"), b["position"], b.get("role"), "opp")
                rho = max(-0.95, min(0.95, base + delta))
                if rho != 0.0:
                    add_corr(a["local_idx"], b["local_idx"], rho)

    return [(i, j, r) for (i, j), r in sorted(corr.items())]


def cholesky(A: np.ndarray, n: int) -> tuple[np.ndarray, float]:
    L = np.zeros((n, n), dtype=np.float64)
    min_d = float("inf")
    for i in range(n):
        for j in range(i + 1):
            s = np.dot(L[i, :j], L[j, :j])
            if i == j:
                v = A[i, i] - s
                val = math.sqrt(v) if v > 0.0 else 1e-9
                L[i, j] = val
                if val < min_d:
                    min_d = val
            else:
                Ljj = L[j, j]
                L[i, j] = (A[i, j] - s) / Ljj if Ljj > 1e-12 else 0.0
    return L, min_d


def corr_cholesky(n: int, correlations: list[tuple[int, int, float]]) -> np.ndarray:
    R = np.eye(n, dtype=np.float64)
    for i, j, rho in correlations:
        if i < n and j < n:
            r = max(-0.95, min(0.95, rho))
            R[i, j] = r
            R[j, i] = r

    scale = 1.0
    for _ in range(30):
        A = np.eye(n, dtype=np.float64) + (R - np.eye(n, dtype=np.float64)) * scale
        L, min_d = cholesky(A, n)
        if min_d >= 1e-5 or scale <= 0.3:
            return L
        scale *= 0.85

    return np.eye(n, dtype=np.float64)


def erf_approx_vec(x: np.ndarray) -> np.ndarray:
    sign = np.sign(x)
    ax = np.abs(x)
    t = 1.0 / (1.0 + 0.3275911 * ax)
    poly = (((((1.061405429 * t - 1.453152027) * t + 1.421413741) * t - 0.284496736) * t + 0.254829592) * t)
    y = 1.0 - poly * np.exp(-ax * ax)
    return sign * y


def norm_cdf_vec(z: np.ndarray) -> np.ndarray:
    return 0.5 * (1.0 + erf_approx_vec(z / math.sqrt(2.0)))


# ── Inverse CDF lookup ──

def summarize_vis(mn: float, mx: float, knots: list[float]):
    n = len(knots)
    dx = (mx - mn) / (n - 1)
    ys = [max(0.0, float(y)) for y in knots]
    if all(y <= 1e-12 for y in ys):
        ys = [1.0] * n

    mass = 0.0
    for i in range(n - 1):
        mass += dx * (ys[i] + ys[i + 1]) / 2.0
    if mass <= 1e-12:
        return None

    def inv(p):
        target = min(1.0, max(0.0, p)) * mass
        acc = 0.0
        for i in range(n - 1):
            x0 = mn + i * dx
            y0, y1 = ys[i], ys[i + 1]
            dy = y1 - y0
            area = dx * (y0 + y1) / 2.0
            if acc + area >= target - 1e-12:
                need = max(0.0, target - acc)
                if abs(dy) < 1e-12:
                    s = (need / dx) / y0 if y0 > 1e-12 else 0.0
                else:
                    a = dy / 2.0
                    b = y0
                    c = -need / dx
                    disc = max(0.0, b * b - 4 * a * c)
                    s = (-b + math.sqrt(disc)) / (2 * a)
                return x0 + min(1.0, max(0.0, s)) * dx
            acc += area
        return mx

    return {"inv": inv, "ys": ys}


def build_inv_cdf_table(mn: float, mx: float, knots: list[float], steps=INV_CDF_STEPS) -> np.ndarray:
    vis = summarize_vis(mn, mx, knots)
    if vis is None:
        return np.linspace(mn, mx, steps + 1, dtype=np.float32)

    peak = max(vis["ys"])
    tail_l = MAX_TAIL_FRAC * max(0.0, min(1.0, vis["ys"][0] / peak)) if peak > 1e-9 else 0.0
    tail_r = MAX_TAIL_FRAC * max(0.0, min(1.0, vis["ys"][-1] / peak)) if peak > 1e-9 else 0.0
    span = mx - mn
    cap = min(TAIL_WIDTH_CAP, max(0.0, TAIL_WIDTH_SPAN_FRAC * span))
    left_w = 0.0 if mn <= 0 else min(cap, mn)
    right_w = cap
    left_atom = tail_l > 0 and left_w <= 1e-9
    vis_share = max(0.0, 1.0 - tail_l - tail_r)

    table = np.zeros(steps + 1, dtype=np.float32)
    for k in range(steps + 1):
        u = k / steps
        if u < tail_l:
            if left_atom or left_w <= 1e-9:
                v = mn
            else:
                t = u / tail_l
                v = (mn - left_w) + left_w * math.sqrt(t)
        elif tail_r > 0 and u > 1.0 - tail_r:
            t = min(1.0, max(0.0, (u - (1.0 - tail_r)) / tail_r))
            v = mx + right_w * (1.0 - math.sqrt(1.0 - t))
        else:
            vp = (u - tail_l) / vis_share if vis_share > 1e-12 else 0.5
            v = vis["inv"](vp)
        table[k] = max(0.0, float(v))
    return table


# ── Best-ball lineup scoring ──

def compute_best_ball_totals(scores_by_player: dict[int, np.ndarray], roster: list[dict], n_sim: int) -> np.ndarray:
    by_pos = {"QB": [], "RB": [], "WR": [], "TE": []}
    for row in roster:
        p = row.get("player")
        if not p:
            continue
        pid = p["id"]
        pos = p["position"]
        if pos in by_pos and pid in scores_by_player:
            by_pos[pos].append(scores_by_player[pid])

    sorted_pos = {}
    for pos, arr_list in by_pos.items():
        if arr_list:
            stacked = np.stack(arr_list, axis=0)
            sorted_pos[pos] = np.sort(stacked, axis=0)[::-1]
        else:
            sorted_pos[pos] = np.zeros((0, n_sim), dtype=np.float32)

    total = np.zeros(n_sim, dtype=np.float32)

    def extract_top(pos: str, count: int) -> list[np.ndarray]:
        extracted = []
        avail = sorted_pos[pos].shape[0]
        take_n = min(avail, count)
        for i in range(take_n):
            extracted.append(sorted_pos[pos][i])
        sorted_pos[pos] = sorted_pos[pos][take_n:]
        return extracted

    # Mandatory starters
    for sc in extract_top("QB", 1): total += sc
    for sc in extract_top("RB", 2): total += sc
    for sc in extract_top("WR", 3): total += sc
    for sc in extract_top("TE", 1): total += sc

    # FLEX: Highest remaining RB, WR, or TE
    flex_positions = [pos for pos in ["RB", "WR", "TE"] if sorted_pos[pos].shape[0] > 0]
    if flex_positions:
        flex_pool = [sorted_pos[pos][0] for pos in flex_positions]
        flex_mat = np.stack(flex_pool, axis=0)
        best_flex_idx = np.argmax(flex_mat, axis=0)
        total += np.choose(best_flex_idx, flex_mat)

        for idx_k, pos in enumerate(flex_positions):
            col_mask = (best_flex_idx == idx_k)
            if np.any(col_mask):
                orig = sorted_pos[pos]
                shifted = np.empty_like(orig)
                shifted[:-1, col_mask] = orig[1:, col_mask]
                shifted[-1, col_mask] = 0.0
                shifted[:, ~col_mask] = orig[:, ~col_mask]
                sorted_pos[pos] = shifted

    # SUPERFLEX: Highest remaining player of any position
    sf_positions = [pos for pos in ["QB", "RB", "WR", "TE"] if sorted_pos[pos].shape[0] > 0]
    if sf_positions:
        sf_pool = [sorted_pos[pos][0] for pos in sf_positions]
        sf_mat = np.stack(sf_pool, axis=0)
        total += np.max(sf_mat, axis=0)

    return total


# ── Main simulation ──

def project_results():
    print("=" * 65)
    print("PROJECTING PORTFOLIO PERFORMANCE")
    print("=" * 65)

    n_sim = load_sim_config()
    cfg = load_player_list_config()
    raw_locked_scores = cfg.get("locked_scores", {})

    print(f"Scenarios per draft: {n_sim:,}")

    draft_files = sorted(RESULTS_DIR.glob("*.json"))
    if not draft_files:
        print(f"\nNo draft files found in {RESULTS_DIR}")
        return

    print(f"\nFound {len(draft_files)} draft result files.")

    proj_payload = json.loads(PROJECTIONS_PATH.read_text(encoding="utf-8"))
    projections = proj_payload.get("byId", proj_payload)

    board_meta = {}
    team_to_opp = {}
    name_to_board_pid = {}
    if BOARD_PATH.exists():
        board_data = json.loads(BOARD_PATH.read_text(encoding="utf-8"))
        for g in board_data.get("games", []):
            away = g.get("away")
            home = g.get("home")
            if away and home:
                team_to_opp[away] = home
                team_to_opp[home] = away
        for p in board_data.get("players", []):
            board_meta[p["id"]] = p
            name_to_board_pid[draft_name_key(p["name"])] = p["id"]
            if p.get("team") and p.get("opponent"):
                team_to_opp[p["team"]] = p["opponent"]

    all_drafts = []
    unique_player_ids = set()
    user_rostered_counts: dict[int, int] = {}
    player_info_map: dict[int, dict] = {}
    name_to_draft_pid: dict[str, int] = {}

    for f in draft_files:
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
            if "rosters" not in d or "myTeam" not in d:
                continue
            d["contest_id"] = f.stem
            all_drafts.append(d)
            my_team_idx = d["myTeam"]

            for t_idx, team in enumerate(d["rosters"]):
                for row in team:
                    p = row.get("player")
                    if p:
                        pid = p["id"]
                        unique_player_ids.add(pid)
                        p_name = p.get("name", f"Player {pid}")
                        name_to_draft_pid[draft_name_key(p_name)] = pid
                        player_info_map[pid] = {
                            "id": pid,
                            "name": p_name,
                            "team": p.get("team", ""),
                            "position": p.get("position", ""),
                        }
                        if t_idx == my_team_idx:
                            user_rostered_counts[pid] = user_rostered_counts.get(pid, 0) + 1
        except Exception as e:
            print(f"Skipping malformed file {f.name}: {e}")

    total_contests = len(all_drafts)
    if total_contests == 0:
        print("No valid draft data available.")
        return

    # Add all players on the board to ensure candidate hedge metrics are generated
    for pid, p in board_meta.items():
        unique_player_ids.add(pid)
        if pid not in player_info_map:
            player_info_map[pid] = {
                "id": pid,
                "name": p.get("name", f"Player {pid}"),
                "team": p.get("team", ""),
                "position": p.get("position", ""),
            }

    # Resolve locked_scores from names or IDs to canonical integer IDs
    resolved_locked_scores: dict[int, float] = {}
    if raw_locked_scores:
        print("\nResolving playerList.js locked_scores:")
        for raw_key, stat_val in raw_locked_scores.items():
            str_key = str(raw_key).strip()
            val = float(stat_val)

            matched_pid = None
            if str_key.isdigit() and int(str_key) in player_info_map:
                matched_pid = int(str_key)
            elif str_key.isdigit() and int(str_key) in board_meta:
                matched_pid = int(str_key)
            else:
                norm_key = draft_name_key(str_key)
                matched_pid = name_to_draft_pid.get(norm_key) or name_to_board_pid.get(norm_key)

            if matched_pid is not None:
                resolved_locked_scores[matched_pid] = val
                info = player_info_map.get(matched_pid) or board_meta.get(matched_pid, {})
                p_name = info.get("name", str_key)
                p_pos = info.get("position", "")
                p_team = info.get("team", "")
                print(f"  • Matched '{str_key}' -> {p_name} ({p_pos} - {p_team}, ID: {matched_pid}) = {val:.2f} pts")
            else:
                print(f"  [WARNING] Locked score entry '{str_key}' could not be matched to any player.")

    ordered_pids = sorted(list(unique_player_ids))
    N = len(ordered_pids)
    player_list_for_corr = []

    for idx, pid in enumerate(ordered_pids):
        info = player_info_map.get(pid, {})
        rec = projections.get(str(pid), {})
        bm = board_meta.get(pid, {})
        player_list_for_corr.append({
            "id": pid,
            "local_idx": idx,
            "position": info.get("position") or bm.get("position") or rec.get("position") or "",
            "team": info.get("team") or bm.get("team") or rec.get("team") or "",
            "role": rec.get("role") or bm.get("role") or None,
            "points": float(rec.get("points") or bm.get("projectedPoints") or 10.0),
        })

    print(f"\nBuilding Gaussian Copula correlation matrix across {N} unique players...")
    corr_pairs = build_correlations(player_list_for_corr, team_to_opp)
    print(f"Active correlation pairs: {len(corr_pairs)}")

    L = corr_cholesky(N, corr_pairs)

    print(f"\nPre-sampling {n_sim:,} correlated scenarios...")
    Z = np.random.standard_normal((N, n_sim)).astype(np.float32)
    scores_by_player: dict[int, np.ndarray] = {}

    for i, pid in enumerate(ordered_pids):
        pid_str = str(pid)
        info = player_info_map.get(pid, {})
        p_name = info.get("name", f"Player {pid}")
        p_pos = info.get("position", "")
        p_team = info.get("team", "")

        # Check TNF / Stat override
        if pid in resolved_locked_scores:
            stat_val = resolved_locked_scores[pid]
            scores_by_player[pid] = np.full(n_sim, stat_val, dtype=np.float32)
            print(f"  [OVERWRITTEN] {p_name:<20} ({p_pos} - {p_team}): Projection distribution overwritten with fixed stat value {stat_val:.2f} pts")
            continue

        yi = np.dot(L[i, : i + 1].astype(np.float32), Z[: i + 1, :])
        rec = projections.get(pid_str)
        if rec and rec.get("knots") and rec.get("min") is not None and rec.get("max") is not None:
            tbl = build_inv_cdf_table(rec["min"], rec["max"], rec["knots"])
            u = norm_cdf_vec(yi)
            u = np.clip(u, 1e-9, 1.0 - 1e-9)
            pos = u * INV_CDF_STEPS
            lo = np.floor(pos).astype(np.int32)
            hi = np.minimum(INV_CDF_STEPS, lo + 1)
            t = pos - lo
            scores_by_player[pid] = tbl[lo] * (1.0 - t) + tbl[hi] * t
        else:
            p_board = board_meta.get(pid, {})
            mu = float(p_board.get("projectedPoints", 10.0))
            sd = float(p_board.get("model", {}).get("sd_points", 4.0)) if p_board.get("model") else 4.0
            scores_by_player[pid] = np.maximum(0.0, mu + sd * yi)

    del Z

    print("\nScoring rosters and aggregating portfolio outcomes...")
    user_wins_matrix = np.zeros((total_contests, n_sim), dtype=np.bool_)
    contest_details = []

    for c_idx, draft in enumerate(all_drafts):
        my_team = draft["myTeam"]
        rosters = draft["rosters"]
        team_names = draft.get("teamNames", [f"Team {t+1}" for t in range(len(rosters))])

        team_scores = []
        for r in rosters:
            team_scores.append(compute_best_ball_totals(scores_by_player, r, n_sim))

        contest_scores = np.stack(team_scores, axis=0)  # (8, n_sim)
        best_scores = np.max(contest_scores, axis=0)

        teams_data = []
        for t_idx, r in enumerate(rosters):
            is_win = (contest_scores[t_idx] >= best_scores)
            if t_idx == my_team:
                user_wins_matrix[c_idx] = is_win

            roster_slots = []
            for slot_row in r:
                p = slot_row.get("player")
                if p:
                    roster_slots.append({
                        "slot": slot_row.get("slot", ""),
                        "id": p["id"],
                        "name": p.get("name", ""),
                        "team": p.get("team", ""),
                        "position": p.get("position", ""),
                    })

            teams_data.append({
                "team_index": t_idx,
                "team_name": team_names[t_idx] if t_idx < len(team_names) else f"Team {t_idx+1}",
                "is_user": (t_idx == my_team),
                "win_rate": round(float(np.mean(is_win) * 100), 2),
                "avg_score": round(float(np.mean(contest_scores[t_idx])), 2),
                "roster": roster_slots,
            })

        contest_details.append({
            "contest_id": draft["contest_id"],
            "contest_index": c_idx + 1,
            "my_team_index": my_team,
            "user_win_rate": teams_data[my_team]["win_rate"],
            "user_avg_score": teams_data[my_team]["avg_score"],
            "teams": teams_data,
        })

    # Portfolio metrics
    wins_per_sim = np.sum(user_wins_matrix, axis=0)
    avg_wins = float(np.mean(wins_per_sim))
    zero_win_pct = float(np.mean(wins_per_sim == 0) * 100)
    has_any_win = (wins_per_sim > 0)

    win_dist = {}
    max_wins = int(np.max(wins_per_sim))
    for w in range(max_wins + 1):
        pct = float(np.mean(wins_per_sim == w) * 100)
        if pct > 0.01:
            win_dist[str(w)] = round(pct, 2)

    # Downside & winning-scenario dependency metrics
    print("Computing player exposures and winning scenario dependencies...")
    exposures = []
    for pid, count in sorted(user_rostered_counts.items(), key=lambda x: x[1], reverse=True):
        info = player_info_map.get(pid, {})
        scores = scores_by_player[pid]
        median_sc = float(np.median(scores))

        worst_half_mask = scores <= median_sc
        if np.sum(worst_half_mask) > 0:
            cond_avg_wins = float(np.mean(wins_per_sim[worst_half_mask]))
            win_impact_pct = round(((cond_avg_wins - avg_wins) / avg_wins) * 100, 1) if avg_wins > 0 else 0.0
        else:
            cond_avg_wins = avg_wins
            win_impact_pct = 0.0

        if np.sum(has_any_win) > 0:
            win_scenario_beat_median_pct = round(float(np.mean(scores[has_any_win] > median_sc) * 100), 1)
        else:
            win_scenario_beat_median_pct = 50.0

        exposures.append({
            "id": pid,
            "name": info.get("name"),
            "team": info.get("team"),
            "position": info.get("position"),
            "drafts_rostered": count,
            "exposure_pct": round((count / total_contests) * 100, 1),
            "median_pts": round(median_sc, 1),
            "cond_avg_wins": round(cond_avg_wins, 2),
            "downside_impact_pct": win_impact_pct,
            "win_scenario_beat_median_pct": win_scenario_beat_median_pct,
            "is_locked": pid in resolved_locked_scores,
        })

    winning_cornerstones = sorted(
        [e for e in exposures if e["exposure_pct"] >= 20.0],
        key=lambda x: x["win_scenario_beat_median_pct"],
        reverse=True,
    )

    # Hedge metrics
    low_win_threshold = math.floor(total_contests * 0.25)
    bad_sims_mask = wins_per_sim <= low_win_threshold
    num_bad_sims = np.sum(bad_sims_mask)

    print(f"Computing hedge metrics across {num_bad_sims:,} scenarios where <= {low_win_threshold} contests are won...")
    hedge_metrics = {}
    for pid in ordered_pids:
        scores = scores_by_player[pid]
        p75 = float(np.percentile(scores, 75))
        if num_bad_sims > 0:
            val = float(np.mean(scores[bad_sims_mask] >= p75) * 100)
        else:
            val = 25.0
        hedge_metrics[str(pid)] = round(val, 1)

    PORTFOLIO_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "total_contests": total_contests,
        "n_sim": n_sim,
        "summary": {
            "avg_wins": round(avg_wins, 2),
            "expected_win_pct": round((avg_wins / total_contests) * 100, 1),
            "shutout_pct": round(zero_win_pct, 2),
            "win_distribution": win_dist,
            "top_rostered": exposures[:5],
            "key_winning_cornerstones": winning_cornerstones[:5],
        },
        "exposures": exposures,
        "contests": contest_details,
        "hedge_metrics": hedge_metrics,
    }

    PORTFOLIO_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    print("\n" + "=" * 65)
    print("PORTFOLIO PROJECTION SUMMARY")
    print("=" * 65)
    print(f"Total Contests         : {total_contests}")
    print(f"Avg 1st Place Finishes : {avg_wins:.2f} of {total_contests} ({payload['summary']['expected_win_pct']}%)")
    print(f"Shutout Probability    : {zero_win_pct:.2f}% (0 wins in a sim)")
    print("\nTop Rostered Players:")
    for exp in exposures[:5]:
        print(f"  {exp['name']:<20} ({exp['position']} - {exp['team']}): {exp['drafts_rostered']}/{total_contests} ({exp['exposure_pct']}%)")
    print("\nKey Winning Scenario Cornerstones (> Median in User Wins):")
    for exp in winning_cornerstones[:5]:
        print(f"  {exp['name']:<20} ({exp['position']} - {exp['team']}): beats median in {exp['win_scenario_beat_median_pct']}% of winning worlds")
    print(f"\nSaved portfolio results to: {PORTFOLIO_PATH.name}")


# ══════════════════════════════════════════════════════════════════════════════
# 10. COMMAND LINE
# ══════════════════════════════════════════════════════════════════════════════

def main(argv: list[str] | None = None):
    parser = argparse.ArgumentParser(
        prog="ffb_pipeline.py",
        description="NFL weekly fantasy pipeline: build board -> priors -> PDFs -> post-draft sim.",
    )
    sub = parser.add_subparsers(dest="cmd", metavar="command")

    p_build = sub.add_parser("build", help="full pre-draft build: board.json, priors, all_projections.json")
    p_build.add_argument("--refresh-stats", "--force", dest="refresh", action="store_true",
                         help="re-download nflverse box scores (including the 2025 cache)")

    p_priors = sub.add_parser("priors", help="rebuild priors.json from the existing board.json")
    p_priors.add_argument("--refresh-stats", "--force", dest="refresh", action="store_true",
                          help="re-download nflverse box scores (including the 2025 cache)")

    sub.add_parser("pdfs", help="regenerate all_projections.json from the existing board.json")
    sub.add_parser("update", help="refresh ranks/projections in board.json from the saved draft-page HTML")
    sub.add_parser("results", help="simulate every draft in results/ and write portfolio.json")

    p_espn = sub.add_parser("espn", help="test the ESPN projections fetch")
    p_espn.add_argument("--week", type=int, default=5)
    p_espn.add_argument("--player", default="Joe Burrow")

    sub.add_parser("config", help="print the parsed playerList.js config")

    args = parser.parse_args(argv)

    if args.cmd == "build":
        build_board(force_download=args.refresh)
    elif args.cmd == "priors":
        build_priors(force_download=args.refresh)
    elif args.cmd == "pdfs":
        generate_pdfs_main()
    elif args.cmd == "update":
        update_board()
    elif args.cmd == "results":
        project_results()
    elif args.cmd == "espn":
        res = fetch_espn_projections(args.week)
        print(f"{args.player} Week {args.week}: {res.get(name_key(args.player), 'N/A')} FPTS")
    elif args.cmd == "config":
        print("Testing Pipeline Ingestion...")
        cfg = load_player_config()
        print(f"Loaded config: limits={cfg.get('pos_limits')}, excludes={len(cfg.get('exclude', []))}")
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
