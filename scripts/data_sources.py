#!/usr/bin/env python3
"""Phase 1 data layer (BRIEF §5).

Downloads + caches every free source, with leakage guards for the backtest.

Cache layout: data/raw/<source>/<season>.<ext>   (gitignored)
- Past seasons download once.
- The current season (2026) re-downloads if the cache is older than 12h.
- --refresh forces a re-download of everything touched.

Core sources (stats_player, pbp, ep_weekly/ffopportunity, injuries, games, db_fpecr)
retry once, then STOP the build on failure (§19). Non-core sources log to
build/source_failures.txt and return None so the build can continue.

CLI:
    python scripts/data_sources.py --summary            # row counts per source per season
    python scripts/data_sources.py --summary --refresh  # force re-download
    python scripts/data_sources.py --sleeper-test       # probe the optional Sleeper API
"""
from __future__ import annotations

import argparse
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
BUILD = ROOT / "build"

CURRENT_SEASON = 2026
CACHE_MAX_AGE_H = 12

NFLVERSE = "https://github.com/nflverse/nflverse-data/releases/download"
FFOPP = "https://github.com/ffverse/ffopportunity/releases/download/latest-data"
DP = "https://raw.githubusercontent.com/dynastyprocess/data/master/files"
NFLDATA = "https://raw.githubusercontent.com/nflverse/nfldata/master/data"

UA = {"User-Agent": "draftbattle.js/0.1 (personal fantasy research; github.com/hbrady7)"}

ALL_SEASONS = range(2019, CURRENT_SEASON + 1)

# season-scoped sources: name -> (url_template, seasons, ext, is_core)
SEASON_SOURCES = {
    "stats_player":   (f"{NFLVERSE}/stats_player/stats_player_week_{{y}}.csv", ALL_SEASONS, "csv", True),
    "pbp":            (f"{NFLVERSE}/pbp/play_by_play_{{y}}.csv.gz", ALL_SEASONS, "csv.gz", True),
    "participation":  (f"{NFLVERSE}/pbp_participation/pbp_participation_{{y}}.csv", range(2019, 2026), "csv", False),
    "snap_counts":    (f"{NFLVERSE}/snap_counts/snap_counts_{{y}}.csv", ALL_SEASONS, "csv", False),
    "ep_weekly":      (f"{FFOPP}/ep_weekly_{{y}}.csv", ALL_SEASONS, "csv", True),
    "injuries":       (f"{NFLVERSE}/injuries/injuries_{{y}}.csv", ALL_SEASONS, "csv", True),
    "depth_charts":   (f"{NFLVERSE}/depth_charts/depth_charts_{{y}}.csv", ALL_SEASONS, "csv", False),
    "weekly_rosters": (f"{NFLVERSE}/weekly_rosters/roster_weekly_{{y}}.csv", ALL_SEASONS, "csv", False),
}

# singletons: name -> (url, ext, is_core)
SINGLE_SOURCES = {
    "games":            (f"{NFLDATA}/games.csv", "csv", True),
    "players":          (f"{NFLVERSE}/players/players.csv", "csv", False),
    "db_fpecr":         (f"{DP}/db_fpecr.parquet", "parquet", True),
    "fp_latest_weekly": (f"{DP}/fp_latest_weekly.csv", "csv", False),
    "db_playerids":     (f"{DP}/db_playerids.csv", "csv", False),
}


# ---------------------------------------------------------------- caching ----
def _age_hours(p: Path) -> float:
    return (time.time() - p.stat().st_mtime) / 3600.0


def _log_failure(name: str, err: Exception) -> None:
    BUILD.mkdir(parents=True, exist_ok=True)
    with open(BUILD / "source_failures.txt", "a") as fh:
        fh.write(f"{datetime.now(timezone.utc).isoformat()}\t{name}\t{err}\n")


def fetch(url: str, dest: Path, *, refresh: bool = False, is_current: bool = False) -> Path:
    """Download url -> dest with one retry. Cache-aware. Raises on final failure."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and not refresh:
        if not is_current or _age_hours(dest) < CACHE_MAX_AGE_H:
            return dest
    last: Exception | None = None
    for attempt in (1, 2):  # §19: retry once
        try:
            with requests.get(url, headers=UA, stream=True, timeout=180) as r:
                r.raise_for_status()
                tmp = dest.parent / (dest.name + ".tmp")
                with open(tmp, "wb") as fh:
                    for chunk in r.iter_content(1 << 20):
                        fh.write(chunk)
                tmp.replace(dest)
            return dest
        except Exception as e:  # noqa: BLE001
            last = e
            if attempt == 1:
                time.sleep(2)
    raise RuntimeError(f"fetch failed after retry: {url} :: {last}")


def _read(dest: Path, ext: str) -> pd.DataFrame:
    if ext == "parquet":
        return pd.read_parquet(dest)
    if ext.endswith("gz"):
        return pd.read_csv(dest, compression="gzip", low_memory=False)
    return pd.read_csv(dest, low_memory=False)


class CoreSourceError(SystemExit):
    """Raised (exit 2) when a core §5 source fails after its retry."""


def _handle_fail(name: str, is_core: bool, err: Exception):
    _log_failure(name, err)
    if is_core:
        print(f"STOP (§19): core source '{name}' failed after retry: {err}", file=sys.stderr)
        raise CoreSourceError(2)
    print(f"WARN: non-core source '{name}' unavailable, continuing: {err}", file=sys.stderr)
    return None


# ---------------------------------------------------------------- loaders ----
def load_season(name: str, year: int, *, refresh: bool = False) -> pd.DataFrame | None:
    url_t, seasons, ext, is_core = SEASON_SOURCES[name]
    if year not in seasons:
        return None
    dest = RAW / name / f"{year}.{ext}"
    try:
        fetch(url_t.format(y=year), dest, refresh=refresh, is_current=(year == CURRENT_SEASON))
    except Exception as e:  # noqa: BLE001
        return _handle_fail(name, is_core, e)
    return _read(dest, ext)


def load_single(name: str, *, refresh: bool = False) -> pd.DataFrame | None:
    url, ext, is_core = SINGLE_SOURCES[name]
    dest = RAW / name / f"{name}.{ext}"
    try:
        # singletons track a live upstream (games, ecr, ids): treat as current.
        fetch(url, dest, refresh=refresh, is_current=True)
    except Exception as e:  # noqa: BLE001
        return _handle_fail(name, is_core, e)
    return _read(dest, ext)


# convenience wrappers used by later phases
def load_stats(year, **k):        return load_season("stats_player", year, **k)
def load_pbp(year, **k):          return load_season("pbp", year, **k)
def load_participation(year, **k):return load_season("participation", year, **k)
def load_snaps(year, **k):        return load_season("snap_counts", year, **k)
def load_ep_weekly(year, **k):    return load_season("ep_weekly", year, **k)
def load_injuries(year, **k):     return load_season("injuries", year, **k)
def load_depth_charts(year, **k): return load_season("depth_charts", year, **k)
def load_rosters(year, **k):      return load_season("weekly_rosters", year, **k)
def load_games(**k):              return load_single("games", **k)
def load_players(**k):            return load_single("players", **k)
def load_fpecr(**k):              return load_single("db_fpecr", **k)
def load_fp_latest(**k):          return load_single("fp_latest_weekly", **k)
def load_db_playerids(**k):       return load_single("db_playerids", **k)


def sleeper_projections(year: int, week: int) -> pd.DataFrame | None:
    """Optional (§5). Returns a DataFrame or None if unreachable/unusable."""
    url = f"https://api.sleeper.app/projections/nfl/{year}/{week}?season_type=regular"
    try:
        r = requests.get(url, headers=UA, timeout=30)
        r.raise_for_status()
        data = r.json()
    except Exception as e:  # noqa: BLE001
        _log_failure("sleeper", e)
        return None
    if not data:
        return None
    return pd.json_normalize(data)


# ------------------------------------------------------------ leakage guards --
# BRIEF §5: ECR archive scrape dates are Fridays. Map each scrape to the NFL week
# whose Sunday follows it; drop ECR rows for players whose game kicked before the
# scrape timestamp (Thursday games). Wired into the backtest in Phase 6.
def ecr_scrape_to_week(scrape_dt: date, games: pd.DataFrame) -> tuple[int, int] | None:
    """Friday scrape -> (season, week) of the following Sunday's slate."""
    if not isinstance(scrape_dt, date):
        scrape_dt = pd.to_datetime(scrape_dt).date()
    target_sunday = scrape_dt + timedelta(days=(6 - scrape_dt.weekday()) % 7)
    gd = games.copy()
    gd["_d"] = pd.to_datetime(gd["gameday"], errors="coerce").dt.date
    hit = gd[(gd["_d"] >= scrape_dt) & (gd["_d"] <= target_sunday + timedelta(days=2))]
    if hit.empty:
        return None
    row = hit.sort_values("_d").iloc[0]
    return int(row["season"]), int(row["week"])


def drop_pre_scrape_games(ecr: pd.DataFrame, games: pd.DataFrame,
                          scrape_ts: datetime, season: int, week: int,
                          team_col: str = "team") -> pd.DataFrame:
    """Drop ECR rows whose team already kicked off before scrape_ts (Thursday leak)."""
    wk = games[(games["season"] == season) & (games["week"] == week)].copy()
    if "gametime" in wk.columns:
        kick = pd.to_datetime(
            wk["gameday"].astype(str) + " " + wk["gametime"].astype(str), errors="coerce"
        )
    else:
        kick = pd.to_datetime(wk["gameday"], errors="coerce")
    # teams whose game had already kicked off at scrape time (Thursday leak)
    started_before = set()
    for t_col in ("home_team", "away_team"):
        if t_col in wk.columns:
            mask = kick < pd.Timestamp(scrape_ts)
            started_before.update(wk.loc[mask, t_col].dropna().tolist())
    if team_col in ecr.columns and started_before:
        return ecr[~ecr[team_col].isin(started_before)]
    return ecr


# ------------------------------------------------------------------ summary --
def summary(refresh: bool = False) -> pd.DataFrame:
    rows = []
    for name in SEASON_SOURCES:
        _, seasons, _, _ = SEASON_SOURCES[name]
        for y in seasons:
            df = load_season(name, y, refresh=refresh)
            rows.append((name, y, None if df is None else len(df),
                         None if df is None else df.shape[1]))
            print(f"  {name:16s} {y}  rows={0 if df is None else len(df):>8}")
    for name in SINGLE_SOURCES:
        df = load_single(name, refresh=refresh)
        rows.append((name, "-", None if df is None else len(df),
                     None if df is None else df.shape[1]))
        print(f"  {name:16s}  -   rows={0 if df is None else len(df):>8}")
    return pd.DataFrame(rows, columns=["source", "season", "rows", "cols"])


def main(argv=None):
    ap = argparse.ArgumentParser(description="draftbattle.js data layer (§5)")
    ap.add_argument("--summary", action="store_true", help="download + print row counts")
    ap.add_argument("--refresh", action="store_true", help="force re-download")
    ap.add_argument("--sleeper-test", action="store_true", help="probe the Sleeper API")
    args = ap.parse_args(argv)

    if args.sleeper_test:
        df = sleeper_projections(2024, 4)
        if df is None:
            print("Sleeper: NO RESPONSE (optional source; logged, skipped).")
        else:
            print(f"Sleeper: OK, {len(df)} rows, cols sample: {list(df.columns)[:8]}")
        return

    if args.summary or not any(vars(args).values()):
        print("=== §5 source summary (rows per source per season) ===")
        df = summary(refresh=args.refresh)
        ok = df["rows"].notna().sum()
        print(f"\n{ok}/{len(df)} source-seasons loaded. "
              f"Cache: {RAW}")
        return


if __name__ == "__main__":
    main()
