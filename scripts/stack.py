#!/usr/bin/env python3
"""BRIEF §6g/§10 — stack fit + single held-out 2025 evaluation (Phase 10), plus the
Phase-9 shape A/B contest and 90% coverage checks. Reuses the Phase-6/7 harness
(scripts/backtest.py) so scoring, universe, and leakage guards are identical.

Walk-forward: per-position NNLS weights fit on 2021-2024, applied ONCE to 2025.
Freezes model/params.json['stack'].

  python scripts/stack.py            # build matrix, fit, held-out eval, freeze params
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.optimize import nnls
from scipy.stats import gamma as _gamma

import backtest as bt
import distribution as dist
import player_sd

ROOT = Path(__file__).resolve().parent.parent
PARAMS = ROOT / "model" / "params.json"
MODELS = ["structural", "gbm", "ecr_implied", "trailing8", "trailing_xfp"]
SEASONS = (2021, 2022, 2023, 2024, 2025)   # 2025 held out
WEEKS = (3, 7, 11, 15)                       # tractable sample (logged)
POS = bt.POS


# ------------------------------------------------- means matrix (all models) --
def build_means_matrix():
    games = bt.ds.load_games()
    actuals = bt.load_actuals(SEASONS + (2019, 2020))
    xfp = bt.load_xfp(SEASONS + (2019, 2020))
    wp = bt.ecr_to_gsis(bt.ecr_weekly(games))
    wp = wp[wp["gsis"].notna()].copy()
    act_idx = actuals.set_index(["player_id", "season", "week"])["pts"]

    act_sorted = actuals.sort_values(["player_id", "season", "week"])
    logs = {pid: list(zip(g["season"], g["week"], g["pts"], g["team"]))
            for pid, g in act_sorted.groupby("player_id")}
    xfp_sorted = xfp.sort_values(["player_id", "season", "week"])
    xlogs = {pid: list(zip(g["season"], g["week"], g["xfp"])) for pid, g in xfp_sorted.groupby("player_id")}

    def t8(pid, s, w, n=8):
        r = [p for (ss, ww, p, tm) in logs.get(pid, []) if (ss, ww) < (s, w)]
        return float(np.mean(r[-n:])) if r else None

    def tx(pid, s, w, n=8):
        r = [x for (ss, ww, x) in xlogs.get(pid, []) if (ss, ww) < (s, w)]
        return float(np.mean(r[-n:])) if r else None

    def scores(pid, s, w, n=8):
        return [p for (ss, ww, p, tm) in logs.get(pid, []) if (ss, ww) < (s, w)][-n:]

    wp["y"] = [act_idx.get((g, s, w), 0.0) for g, s, w in zip(wp["gsis"], wp["season"], wp["week"])]
    print("  building structural + GBM lookups (walk-forward, 2021-2025)…")
    struct_by, gbm_by, _ = bt.build_model_lookups(wp, SEASONS, verbose=True)
    iso_by = {S: bt.isotonic_by_pos(wp[wp["season"] < S]) for S in SEASONS}

    rows = []
    for S in SEASONS:
        iso = iso_by.get(S, {})
        if not iso:
            continue
        for w in WEEKS:
            wk = wp[(wp["season"] == S) & (wp["week"] == w)]
            if wk.empty:
                continue
            uni = pd.concat([wk[wk["pos"] == p].nsmallest(bt.TOPN[p], "ecr") for p in POS])
            for _, r in uni.iterrows():
                pos, pid = r["pos"], r["gsis"]
                a, x = t8(pid, S, w), tx(pid, S, w)
                ecr = float(iso[pos].predict([r["pos_rank"]])[0]) if pos in iso else a
                rows.append({
                    "pos": pos, "season": int(S), "week": int(w), "gsis": pid,
                    "y": float(act_idx.get((pid, S, w), 0.0)),
                    "structural": struct_by.get((pid, S, w)), "gbm": gbm_by.get((pid, S, w)),
                    "ecr_implied": ecr, "trailing8": a if a is not None else ecr,
                    "trailing_xfp": x if x is not None else (a if a is not None else ecr),
                    "scores": scores(pid, S, w),
                })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------- stack fit ---
def fit_stack(train, pos):
    sub = train[train["pos"] == pos].dropna(subset=MODELS + ["y"])
    if len(sub) < 40:
        return {m: (1.0 / len(MODELS)) for m in MODELS}
    X = sub[MODELS].astype(float).values
    y = sub["y"].astype(float).values
    w, _ = nnls(X, y)
    w = w / w.sum() if w.sum() > 1e-9 else np.ones(len(MODELS)) / len(MODELS)
    return dict(zip(MODELS, [round(float(v), 4) for v in w]))


def stack_pred(r, weights):
    w = weights[r["pos"]]
    s = tot = 0.0
    for m in MODELS:
        v = r[m]
        if v is not None and np.isfinite(v):
            s += w[m] * v
            tot += w[m]
    return s / tot if tot > 1e-9 else np.nan


# ------------------------------------------------------------- distributions --
def gamma_quantiles(mu, sd, grid=bt.CRPS_GRID):
    mu = max(0.05, mu); sd = max(0.5, sd)
    k = (mu / sd) ** 2
    theta = sd * sd / mu
    return _gamma.ppf(grid, k, scale=theta)


def eval_col(df, col, shape="A"):
    """Per-position {crps,mae,cov90,cov50,n} using shape A (knots) or B (gamma)."""
    rec = {p: [] for p in POS}
    for _, r in df.iterrows():
        mu = r[col]
        if mu is None or not np.isfinite(mu):
            continue
        mu = max(0.0, float(mu)); pos = r["pos"]; y = r["y"]
        sd = player_sd.player_sd(pos, mu, r.get("scores") or [])["sd"]
        if shape == "B":
            q = gamma_quantiles(mu, sd)
            cov90 = 1.0 if q[int(0.05 * len(q))] <= y <= q[int(0.95 * len(q))] else 0.0
            cov50 = 1.0 if q[int(0.25 * len(q))] <= y <= q[int(0.75 * len(q))] else 0.0
            crps = 2.0 * np.mean(np.where(y - q >= 0, bt.CRPS_GRID * (y - q), (bt.CRPS_GRID - 1) * (y - q)))
            m = {"crps": crps, "ae": abs(mu - y), "cov90": cov90, "cov50": cov50}
        else:
            d = dist.player_distribution(pos, mu, sd, 1.0, None)
            q = bt.mixture_quantiles(d)
            m = bt.metrics_for(mu, y, d, q)
        rec[pos].append(m)
    out = {}
    for p in POS:
        if rec[p]:
            out[p] = {"crps": round(float(np.mean([x["crps"] for x in rec[p]])), 3),
                      "mae": round(float(np.mean([x["ae"] for x in rec[p]])), 3),
                      "cov90": round(float(np.mean([x["cov90"] for x in rec[p]])), 3),
                      "cov50": round(float(np.mean([x["cov50"] for x in rec[p]])), 3),
                      "n": len(rec[p])}
    return out


def main():
    print("=== Phase 10 stack + held-out 2025 (weeks", WEEKS, ") ===")
    df = build_means_matrix()
    df.to_parquet(ROOT / "backtest" / "means_matrix.parquet") if False else None
    train = df[df["season"] < 2025].copy()
    test = df[df["season"] == 2025].copy()
    print(f"  matrix: {len(df)} rows ({len(train)} train 2021-24, {len(test)} held-out 2025)")

    weights = {pos: fit_stack(train, pos) for pos in POS}
    print("\n  per-position stack weights (NNLS, sum=1):")
    for pos in POS:
        print(f"   {pos}: " + " ".join(f"{m}={weights[pos][m]:.2f}" for m in MODELS))

    test["stack"] = [stack_pred(r, weights) for _, r in test.iterrows()]

    # Phase 9: shape A vs B contest on the stack means (held-out)
    print("\n  Phase 9 — shape A (knots) vs B (gamma) CRPS on held-out stack means:")
    evA, evB = eval_col(test, "stack", "A"), eval_col(test, "stack", "B")
    shape_by = {}
    for p in POS:
        if p in evA and p in evB:
            win = "A" if evA[p]["crps"] <= evB[p]["crps"] else "B"
            shape_by[p] = win
            print(f"   {p}: A={evA[p]['crps']} B={evB[p]['crps']} -> shape {win}")

    # Phase 10 held-out: stack vs ecr_implied vs best single model, per position
    print("\n  Phase 10 — held-out 2025 CRPS by position (shape A):")
    ev = {c: eval_col(test, c, "A") for c in (["stack"] + MODELS)}
    header = f"   {'pos':4} {'stack':>16} {'ecr_implied':>16} {'best-single':>22}"
    print(header)
    verdict = {}
    for p in POS:
        if p not in ev["stack"] or p not in ev["ecr_implied"]:
            continue
        sc, ec = ev["stack"][p], ev["ecr_implied"][p]
        singles = {m: ev[m][p] for m in MODELS if p in ev[m]}
        best_m = min(singles, key=lambda m: singles[m]["crps"])
        beats = sc["crps"] < ec["crps"] and sc["mae"] < ec["mae"]
        verdict[p] = {"stack_crps": sc["crps"], "ecr_crps": ec["crps"], "stack_mae": sc["mae"],
                      "ecr_mae": ec["mae"], "beats_ecr": bool(beats), "best_single": best_m,
                      "best_single_crps": singles[best_m]["crps"], "cov90_stack": sc["cov90"]}
        print(f"   {p:4} CRPS={sc['crps']:.3f}/MAE={sc['mae']:.2f}  "
              f"CRPS={ec['crps']:.3f}/MAE={ec['mae']:.2f}  "
              f"{best_m}={singles[best_m]['crps']:.3f}   {'BEATS ECR' if beats else 'no'}")

    # Phase 9: player 90% coverage on held-out (stack, shape A)
    cov = {p: ev["stack"][p]["cov90"] for p in POS if p in ev["stack"]}
    print("\n  Phase 9 — held-out player 90% coverage (target 0.90 ±0.03):", cov)

    n_beat = sum(1 for p in verdict if verdict[p]["beats_ecr"])
    print(f"\n  VERDICT: stack beats ECR (CRPS+MAE) at {n_beat}/{len(verdict)} positions.")
    if n_beat == 0:
        print("  *** §19 STOP CONDITION: stack loses to ECR at EVERY position. ***")

    # freeze params.json['stack']
    params = json.loads(PARAMS.read_text()) if PARAMS.exists() else {}
    params["stack"] = {
        "weights_by_pos": weights, "models": MODELS,
        "fit_window": "2021-2024 walk-forward", "held_out": "2025",
        "weeks_sampled": list(WEEKS), "shape_by_pos": shape_by,
        "live_bridge": {"until_logged_weeks": 6, "ffa_takes": "ecr_implied weight, 50/50 with ecr", "db_weight": 0},
        "held_out_verdict": verdict, "player_cov90": cov, "metric": "CRPS (primary), MAE",
    }
    PARAMS.write_text(json.dumps(params, indent=1))
    print(f"\n  froze model/params.json['stack'] ({len(weights)} positions).")
    return verdict


if __name__ == "__main__":
    main()
