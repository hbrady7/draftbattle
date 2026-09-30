#!/usr/bin/env python3
"""BRIEF §9 empirical player-pair correlations for the Gaussian copula.

For 2019-2025 we form each player-game's standardized residual z = (actual - pred)/sd
(a Gaussian-copula PIT approximation; pred = recency-weighted trailing mean, sd =
player_sd curve). Within each team-game we rank by pred to roles (QB1, RB1/2, WR1/2/3,
TE1) and accumulate residual pairs by role-pair CATEGORY (same-team and opponent).
Correlation per category is shrunk toward 0 by its standard error; categories with
< MIN_PAIRS fall back to the skeleton's 4 constants. Frozen to model/params.json.

  python scripts/correlations.py --fit
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd

import data_sources as ds
import player_sd
from build_board import score_stats

ROOT = Path(__file__).resolve().parent.parent
PARAMS = ROOT / "model" / "params.json"
POS = ("QB", "RB", "WR", "TE")
SEASONS = list(range(2019, 2026))
MIN_PAIRS = 500
SHRINK_K = 120                      # pairs; pulls thin categories toward 0
TRAIL = 8

# skeleton fallback constants (§0 / simCore BASE_SAME / BASE_OPP)
CONST = {"QB1-WR1": 0.15, "QB1-WR2": 0.15, "QB1-WR3": 0.15, "QB1-TE1": 0.15,
         "QB1-RB1": 0.05, "QB1-RB2": 0.05, "QB1-QB1_opp": 0.20}

SAME_CATS = ["QB1-WR1", "QB1-WR2", "QB1-WR3", "QB1-TE1", "QB1-RB1", "QB1-RB2",
             "WR1-WR2", "WR1-TE1", "RB1-RB2", "RB1-WR1"]
OPP_CATS = ["QB1-QB1_opp", "QB1-WR1_opp", "WR1-WR1_opp", "RB1-QB1_opp", "RB1-RB1_opp"]


def role_label(pos, rank):  # rank 1-based within position within team-week
    if pos == "QB":
        return "QB1" if rank == 1 else None
    if pos == "TE":
        return "TE1" if rank == 1 else None
    if pos == "RB":
        return {1: "RB1", 2: "RB2"}.get(rank)
    if pos == "WR":
        return {1: "WR1", 2: "WR2", 3: "WR3"}.get(rank)
    return None


def build_residuals(seasons):
    """Return long df: (season, week, team, opp, gsis, pos, role, z)."""
    frames = []
    for s in seasons:
        df = ds.load_stats(s)
        if df is None:
            continue
        df = df[df["position"].isin(POS)].copy()
        if "season_type" in df.columns:
            df = df[df["season_type"].astype(str).str.upper().isin(["REG", "REGULAR"])]
        df["pts"] = [score_stats(r) for r in df.to_dict("records")]
        frames.append(df[["player_id", "team", "opponent_team", "season", "week", "position", "pts"]])
    a = pd.concat(frames, ignore_index=True).rename(columns={"player_id": "gsis", "opponent_team": "opp"})
    a = a.sort_values(["gsis", "season", "week"])
    # recency-weighted trailing mean (exclude current week)
    rows = []
    for g, grp in a.groupby("gsis"):
        pts = grp["pts"].tolist()
        recs = grp.to_dict("records")
        for i, r in enumerate(recs):
            hist = pts[max(0, i - TRAIL):i]
            if len(hist) < 3:
                continue
            w = np.arange(1, len(hist) + 1, dtype=float)
            pred = float(np.dot(w, hist) / w.sum())
            sd = player_sd.curve_sd(r["position"], max(pred, 1.0))
            z = (r["pts"] - pred) / sd if sd > 1e-6 else 0.0
            rows.append({**{k: r[k] for k in ("season", "week", "team", "opp", "gsis", "position")},
                         "pred": pred, "z": float(np.clip(z, -4, 4))})
    res = pd.DataFrame(rows)
    # assign roles within (season,week,team) by pred desc, per position
    res["rank"] = res.groupby(["season", "week", "team", "position"])["pred"].rank(ascending=False, method="first")
    res["role"] = [role_label(p, int(k)) for p, k in zip(res["position"], res["rank"])]
    return res[res["role"].notna()]


def fit(seasons=SEASONS):
    res = build_residuals(seasons)
    by_tw = {(s, w, t): {r["role"]: r["z"] for _, r in g.iterrows()}
             for (s, w, t), g in res.groupby(["season", "week", "team"])}
    same = {c: [] for c in SAME_CATS}
    opp = {c: [] for c in OPP_CATS}

    for (s, w, t), roles in by_tw.items():
        for c in SAME_CATS:
            a, b = c.split("-")
            if a in roles and b in roles:
                same[c].append((roles[a], roles[b]))
        # opponent pairs: this team's role vs opp team's role
        opp_team = res[(res["season"] == s) & (res["week"] == w) & (res["team"] == t)]["opp"]
        if len(opp_team) == 0:
            continue
        ot = opp_team.iloc[0]
        oroles = by_tw.get((s, w, ot))
        if not oroles:
            continue
        for c in OPP_CATS:
            a, b = c.replace("_opp", "").split("-")
            if a in roles and b in oroles:
                opp[c].append((roles[a], oroles[b]))

    def corr_shrunk(pairs):
        n = len(pairs)
        if n < 3:
            return None, n
        arr = np.array(pairs)
        r = float(np.corrcoef(arr[:, 0], arr[:, 1])[0, 1])
        if not math.isfinite(r):
            return None, n
        r *= n / (n + SHRINK_K)                     # shrink toward 0
        return round(r, 4), n

    out = {}
    for cat, pairs in {**same, **opp}.items():
        r, n = corr_shrunk(pairs)
        fallback = CONST.get(cat, 0.0)
        # opponent QB-QB fallback / same-team fallbacks
        if cat == "QB1-QB1_opp":
            fallback = CONST["QB1-QB1_opp"]
        use = r if (r is not None and n >= MIN_PAIRS) else fallback
        out[cat] = {"r": round(float(use), 4), "n": n, "empirical": r,
                    "source": "empirical" if (r is not None and n >= MIN_PAIRS) else "constant"}
    _save(out)
    return out


def _save(cats):
    params = json.loads(PARAMS.read_text()) if PARAMS.exists() else {}
    params["correlations"] = {"categories": cats, "fit_seasons": [min(SEASONS), max(SEASONS)],
                              "min_pairs": MIN_PAIRS, "shrink_k": SHRINK_K}
    PARAMS.write_text(json.dumps(params, indent=1))


def load_categories():
    if not PARAMS.exists():
        return None
    try:
        return json.loads(PARAMS.read_text()).get("correlations", {}).get("categories")
    except ValueError:
        return None


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--fit", action="store_true")
    ap.parse_args(argv)
    cats = fit()
    print("=== §9 empirical role-pair correlations (2019-2025) ===")
    print(f"  {'category':16} {'r_used':>8} {'empirical':>10} {'n_pairs':>8} {'source':>10}")
    for c, d in cats.items():
        emp = "-" if d["empirical"] is None else f"{d['empirical']:+.3f}"
        print(f"  {c:16} {d['r']:>+8.3f} {emp:>10} {d['n']:>8} {d['source']:>10}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
