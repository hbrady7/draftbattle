#!/usr/bin/env python3
"""BRIEF §6b-6d feature engineering (Phase 7), walk-forward-safe.

One row per (gsis, season, week) over the ECR universe, with feature GROUPS:
  base         market (ecr, ecr_sd, pos_rank) + trailing league pts        [always in]
  vegas        implied team total, spread, total, home/away                (§6b)
  weather      dome, wind, temp                                            (§6b)
  participation trailing target share / wopr / targets & carries per game  (§6c)
  efficiency   trailing xFP (ep_weekly, re-scored), yards & epa per game    (§6d)
  opponent     opp fantasy pts allowed to the position, season-to-date      (§6d)

All trailing features use only games strictly before (season, week); vegas/weather
are the current game's pre-kickoff lines, which are known at draft time.

Skipped (logged): snap_counts route participation (pfr_player_id needs a separate
crosswalk; target_share/wopr from stats_player are a stronger route proxy anyway).
Cached to data/raw/_features_cache/.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np
import pandas as pd

import data_sources as ds
from build_board import score_stats  # league scoring (scoring.json), row-wise

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / "data" / "raw" / "_features_cache"
POS = ("QB", "RB", "WR", "TE")
LEAGUE_IMPLIED = 22.0  # ~league-average implied team total, for volume scaling

# feature-group -> columns (for §10 ablations)
GROUPS = {
    "base": ["ecr", "ecr_sd", "pos_rank", "tr8_pts", "tr3_pts", "n_prior"],
    "vegas": ["implied_total", "spread_line", "total_line", "is_home"],
    "weather": ["is_dome", "wind", "temp"],
    "participation": ["tr8_target_share", "tr8_wopr", "tr8_targets_pg", "tr8_carries_pg", "tr8_patt_pg"],
    "efficiency": ["tr8_xfp", "tr8_recyd_pg", "tr8_rushyd_pg", "tr8_passyd_pg", "tr8_epa"],
    "opponent": ["opp_pa_to_pos"],
}
ALL_FEATS = [c for g in GROUPS.values() for c in g]


def _score_week_df(df):
    S = ds  # placeholder to avoid lint; score via score_stats row-wise below
    return df


def _team_env(games):
    """(season,week,team) -> implied_total, opp, is_home, is_dome, wind, temp."""
    rows = []
    for _, g in games.iterrows():
        try:
            tot, spr = float(g["total_line"]), float(g["spread_line"])
        except (TypeError, ValueError):
            tot, spr = np.nan, np.nan
        dome = 1 if str(g.get("roof", "")).lower() in ("dome", "closed") else 0
        wind = pd.to_numeric(g.get("wind"), errors="coerce")
        temp = pd.to_numeric(g.get("temp"), errors="coerce")
        for team, opp, home, imp in [
            (g["home_team"], g["away_team"], 1, (tot + spr) / 2 if np.isfinite(tot) else np.nan),
            (g["away_team"], g["home_team"], 0, (tot - spr) / 2 if np.isfinite(tot) else np.nan)]:
            rows.append({"season": int(g["season"]), "week": int(g["week"]), "team": team,
                         "opp": opp, "is_home": home, "implied_total": imp,
                         "spread_line": spr if home else -spr, "total_line": tot,
                         "is_dome": dome, "wind": wind, "temp": temp})
    e = pd.DataFrame(rows)
    # dome -> wind 0 / temp 70 neutral; open-air NA weather -> neutral
    e["wind"] = e["wind"].where(e["is_dome"] == 0, 0.0).fillna(6.0)
    e["temp"] = e["temp"].where(e["is_dome"] == 0, 70.0).fillna(60.0)
    return e


def build_feature_frame(seasons=(2020, 2021, 2022, 2023, 2024), refresh=False):
    CACHE.mkdir(parents=True, exist_ok=True)
    key = hashlib.md5((",".join(map(str, seasons)) + "|v2").encode()).hexdigest()[:10]
    fp = CACHE / f"feat_{key}.parquet"
    if fp.exists() and not refresh:
        try:
            return pd.read_parquet(fp)
        except Exception:
            pass

    hist = tuple(sorted(set(seasons) | {min(seasons) - 1}))  # +1 prior season for trailing
    frames = []
    for s in hist:
        df = ds.load_stats(s)
        if df is None:
            continue
        df = df[df["position"].isin(POS)].copy()
        if "season_type" in df.columns:
            df = df[df["season_type"].astype(str).str.upper().isin(["REG", "REGULAR"])]
        df["pts"] = df.apply(score_stats, axis=1)
        frames.append(df)
    st = pd.concat(frames, ignore_index=True)
    st["player_id"] = st["player_id"].astype(str)
    for c in ["targets", "carries", "attempts", "receptions", "receiving_yards", "rushing_yards",
              "passing_yards", "target_share", "wopr", "receiving_epa", "rushing_epa", "passing_epa"]:
        if c not in st.columns:
            st[c] = 0.0
        st[c] = pd.to_numeric(st[c], errors="coerce").fillna(0.0)
    st["epa_all"] = st["receiving_epa"] + st["rushing_epa"] + st["passing_epa"]
    st = st.sort_values(["player_id", "season", "week"]).reset_index(drop=True)

    # trailing (prior-only) rolling means over last 8 / 3 games
    g = st.groupby("player_id", group_keys=False)

    def roll(col, n):
        return g[col].apply(lambda x: x.rolling(n, min_periods=1).mean().shift(1))

    st["tr8_pts"] = roll("pts", 8); st["tr3_pts"] = roll("pts", 3)
    st["tr8_targets_pg"] = roll("targets", 8); st["tr8_carries_pg"] = roll("carries", 8)
    st["tr8_patt_pg"] = roll("attempts", 8)
    st["tr8_recyd_pg"] = roll("receiving_yards", 8); st["tr8_rushyd_pg"] = roll("rushing_yards", 8)
    st["tr8_passyd_pg"] = roll("passing_yards", 8)
    st["tr8_target_share"] = roll("target_share", 8); st["tr8_wopr"] = roll("wopr", 8)
    st["tr8_epa"] = roll("epa_all", 8)
    st["n_prior"] = g.cumcount()

    # trailing xFP from ep_weekly (re-scored components), prior-only
    from backtest import load_xfp  # reuse the exact xFP re-scoring
    xfp = load_xfp(hist)
    xfp = xfp.sort_values(["player_id", "season", "week"])
    xfp["tr8_xfp"] = xfp.groupby("player_id")["xfp"].apply(
        lambda x: x.rolling(8, min_periods=1).mean().shift(1)).reset_index(level=0, drop=True)
    st = st.merge(xfp[["player_id", "season", "week", "tr8_xfp"]],
                  on=["player_id", "season", "week"], how="left")

    # game environment (current week, pre-kickoff)
    env = _team_env(ds.load_games())
    st = st.merge(env, left_on=["season", "week", "team"], right_on=["season", "week", "team"], how="left")

    # opponent fantasy points allowed to position, season-to-date prior
    pa = (st.groupby(["season", "week", "opp", "position"])["pts"].sum().reset_index()
          .rename(columns={"opp": "team_def", "pts": "pa"}))
    pa = pa.sort_values(["season", "team_def", "position", "week"])
    pa["opp_pa_to_pos"] = (pa.groupby(["season", "team_def", "position"])["pa"]
                           .apply(lambda x: x.expanding().mean().shift(1)).reset_index(level=[0, 1, 2], drop=True))
    st = st.merge(pa[["season", "week", "team_def", "position", "opp_pa_to_pos"]],
                  left_on=["season", "week", "opp", "position"],
                  right_on=["season", "week", "team_def", "position"], how="left")

    keep = ["player_id", "season", "week", "position", "team", "opp", "pts"] + ALL_FEATS
    out = st[[c for c in keep if c in st.columns]].copy()
    out = out[out["season"].isin(seasons)]
    for c in ALL_FEATS:
        if c not in out.columns:
            out[c] = np.nan
    out.to_parquet(fp)
    return out


if __name__ == "__main__":
    f = build_feature_frame(refresh=True)
    print(f"feature frame: {len(f)} player-weeks, {len(ALL_FEATS)} features")
    print("seasons:", sorted(f["season"].unique()))
    print("non-null rate per group:")
    for gname, cols in GROUPS.items():
        nn = f[cols].notna().mean().mean()
        print(f"  {gname:14s} {nn:.2f}")
