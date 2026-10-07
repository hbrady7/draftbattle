#!/usr/bin/env python3
"""Conditional spread model — can we NARROW the 90% interval without losing coverage?

The shipped SD (player_sd.py) is a function of position + projected mean (+ QB rush
share); the player's own history barely moves it (K=512 for QB/WR). This script asks
whether a richer set of factors predicts game-to-game spread better:

  expert disagreement (ecr_sd), Vegas env (implied total, |spread|, total, dome, wind),
  role (target share, WOPR, carries, pass att, xFP), own volatility (weighted SD of last
  8 games, CV), sample size (n_prior), projection level.

Contenders, all walk-forward (fit 2021-24, scored ONCE on held-out 2025, played games
only — DNP risk is the separate availability mass):
  base   shipped player_sd + shipped shape (player_distribution)
  var    GBM on squared residual -> SD, same shipped shape, scale c set by
         leave-one-season-out on train so 90% coverage holds
  cqr    conformalized quantile GBMs for q05/q95 directly (asymmetric, distribution-free)

Scored on: coverage90, mean width, interval (Winkler) score = width + 20*miss distance
(lower is better; it's the proper score that rewards narrow AND calibrated).

  python scripts/sd_model.py              # build/caches backtest/sd_matrix.parquet, evaluate
  python scripts/sd_model.py --freeze     # + fit on 2021-25 and freeze params.json['sd_model']
"""
from __future__ import annotations

import argparse
import json
import pickle
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor

import backtest as bt
import distribution as dist
import features as feat
import player_sd
import stack

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / "backtest" / "sd_matrix.parquet"
PARAMS = ROOT / "model" / "params.json"
MODEL_PKL = ROOT / "model" / "sd_model.pkl"
POS = bt.POS
ALPHA = 0.10
FEATS = ["mu", "pos_code", "ecr_sd", "ecr_sd_rel", "implied_total", "abs_spread", "total_line",
         "is_dome", "wind", "tr8_target_share", "tr8_wopr", "tr8_targets_pg", "tr8_carries_pg",
         "tr8_patt_pg", "tr8_xfp", "own_sd", "own_cv", "n_prior", "base_sd"]
POS_CODE = {"QB": 0, "RB": 1, "WR": 2, "TE": 3}


def wsd(xs):
    """recency-weighted SD (weights 1..n), same as player_sd's raw step."""
    x = np.asarray(xs, float)
    if len(x) < 2:
        return np.nan
    w = np.arange(1, len(x) + 1, dtype=float)
    m = (w * x).sum() / w.sum()
    v1, v2 = w.sum(), (w * w).sum()
    return float(np.sqrt(max(0.0, (w * (x - m) ** 2).sum() / (v1 - v2 / v1))))


def build_matrix():
    if CACHE.exists():
        return pd.read_parquet(CACHE)
    stack.WEEKS = tuple(range(3, 18))   # all weeks, not the 4-week tractable sample
    df = stack.build_means_matrix()
    weights = json.loads(PARAMS.read_text())["stack"]["weights_by_pos"]
    df["mu"] = [max(0.0, float(stack.stack_pred(r, weights))) for _, r in df.iterrows()]
    act = bt.load_actuals(stack.SEASONS)
    played = set(zip(act["player_id"], act["season"], act["week"]))
    df["played"] = [(g, s, w) in played for g, s, w in zip(df["gsis"], df["season"], df["week"])]
    df["own_sd"] = df["scores"].map(lambda s: wsd(list(s)) if s is not None else np.nan)
    df["n_scores"] = df["scores"].map(lambda s: 0 if s is None else len(s))
    df["base_sd"] = [player_sd.player_sd(p, m, list(s) if s is not None else [])["sd"]
                     for p, m, s in zip(df["pos"], df["mu"], df["scores"])]
    df = df.drop(columns=["scores"])
    ff = feat.build_feature_frame(tuple(range(2020, 2026))).rename(columns={"player_id": "gsis"})
    keep = ["gsis", "season", "week", "ecr_sd", "implied_total", "spread_line", "total_line",
            "is_dome", "wind", "tr8_target_share", "tr8_wopr", "tr8_targets_pg", "tr8_carries_pg",
            "tr8_patt_pg", "tr8_xfp", "n_prior", "tr8_pts", "ecr"]
    df = df.merge(ff[keep].drop_duplicates(["gsis", "season", "week"]), on=["gsis", "season", "week"], how="left")
    CACHE.parent.mkdir(exist_ok=True)
    df.to_parquet(CACHE)
    return df


def prep(df):
    d = df[df["played"]].copy()
    d["pos_code"] = d["pos"].map(POS_CODE)
    d["abs_spread"] = d["spread_line"].abs()
    d["ecr_sd_rel"] = d["ecr_sd"] / d["ecr"].clip(lower=1) if "ecr" in d else np.nan
    d["own_cv"] = d["own_sd"] / d["tr8_pts"].clip(lower=1)
    for c in ["is_dome"]:
        d[c] = pd.to_numeric(d[c], errors="coerce")
    return d.reset_index(drop=True)


GRID = ROOT / "backtest" / "interval_grid.npz"
MU_G, SD_G = np.arange(0.0, 45.01, 0.5), np.arange(0.5, 22.01, 0.5)
_interp = {}


def _grid():
    """p05/p95 of the shipped shape on a (mu, sd) grid per position (12ms/build -> cache once)."""
    if not _interp:
        from scipy.interpolate import RegularGridInterpolator
        if GRID.exists():
            z = np.load(GRID)
        else:
            z = {}
            for p in POS:
                lo = np.zeros((len(MU_G), len(SD_G))); hi = np.zeros_like(lo)
                for i, m in enumerate(MU_G):
                    for j, sd in enumerate(SD_G):
                        dd = dist.player_distribution(p, max(m, 0.05), sd, 1.0, None)
                        lo[i, j], hi[i, j] = dd["p05"], dd["p95"]
                z[f"{p}_lo"], z[f"{p}_hi"] = lo, hi
            np.savez(GRID, **z)
        for p in POS:
            _interp[p] = (RegularGridInterpolator((MU_G, SD_G), z[f"{p}_lo"]),
                          RegularGridInterpolator((MU_G, SD_G), z[f"{p}_hi"]))
    return _interp


def shipped_intervals(pos, mu, sd):
    """vectorized shipped-shape 90% interval for arrays (pos, mu, sd)."""
    g = _grid()
    pos, mu, sd = np.asarray(pos), np.clip(np.asarray(mu, float), 0, 45), np.clip(np.asarray(sd, float), 0.5, 22)
    lo, hi = np.zeros(len(mu)), np.zeros(len(mu))
    for p in POS:
        m = pos == p
        if m.any():
            pts = np.column_stack([mu[m], sd[m]])
            lo[m], hi[m] = g[p][0](pts), g[p][1](pts)
    return lo, hi


def interval_score(y, lo, hi, a=ALPHA):
    return (hi - lo) + (2 / a) * np.clip(lo - y, 0, None) + (2 / a) * np.clip(y - hi, 0, None)


def summarize(y, lo, hi, pos):
    out = {}
    for p in list(POS) + ["ALL"]:
        m = np.ones(len(y), bool) if p == "ALL" else (pos == p)
        if m.sum() == 0:
            continue
        cov = float(((y[m] >= lo[m]) & (y[m] <= hi[m])).mean())
        out[p] = {"n": int(m.sum()), "cov90": round(cov, 3), "width": round(float((hi[m] - lo[m]).mean()), 2),
                  "iscore": round(float(interval_score(y[m], lo[m], hi[m]).mean()), 2)}
    return out


def gbm(loss, **kw):
    return HistGradientBoostingRegressor(loss=loss, max_iter=300, learning_rate=0.04, max_leaf_nodes=15,
                                         min_samples_leaf=80, l2_regularization=1.0, random_state=0, **kw)


def fit_var(train):
    """GBM for E[resid^2 | x] (poisson loss = positive mean, allows 0 targets)."""
    m = gbm("poisson")
    m.fit(train[FEATS], (train["y"] - train["mu"]) ** 2)
    return m


def var_intervals(model, d, c_by_pos):
    sd = np.sqrt(np.clip(model.predict(d[FEATS]), 0.25, None))
    sd = sd * d["pos"].map(c_by_pos).to_numpy()
    lo, hi = shipped_intervals(d["pos"], d["mu"], sd)
    return lo, hi, sd


def calibrate_scale(train, grid=np.arange(0.70, 1.40, 0.02)):
    """leave-one-season-out: per-position scale c whose OOF coverage is closest to 0.90."""
    oof = []
    for S in sorted(train["season"].unique()):
        tr, te = train[train["season"] != S], train[train["season"] == S].copy()
        te["raw_sd"] = np.sqrt(np.clip(fit_var(tr).predict(te[FEATS]), 0.25, None))
        oof.append(te)
    oof = pd.concat(oof)
    c_by = {}
    for p in POS:
        o = oof[oof["pos"] == p]
        best = None
        for c in grid:
            lo, hi = shipped_intervals(o["pos"], o["mu"], o["raw_sd"] * c)
            cov = float(((o["y"].to_numpy() >= lo) & (o["y"].to_numpy() <= hi)).mean())
            if best is None or abs(cov - 0.90) < best[1]:
                best = (float(c), abs(cov - 0.90))
        c_by[p] = round(best[0], 2)
    return c_by


def fit_cqr(train):
    """quantile GBMs + split-conformal correction from leave-one-season-out residuals."""
    qs = {}
    for q in (ALPHA / 2, 1 - ALPHA / 2):
        qs[q] = gbm("quantile", quantile=q).fit(train[FEATS], train["y"])
    # conformal: per-position E = max(lo - y, y - hi) on OOF; correction = 90% quantile of E
    oof = []
    for S in sorted(train["season"].unique()):
        tr, te = train[train["season"] != S], train[train["season"] == S].copy()
        lo = gbm("quantile", quantile=ALPHA / 2).fit(tr[FEATS], tr["y"]).predict(te[FEATS])
        hi = gbm("quantile", quantile=1 - ALPHA / 2).fit(tr[FEATS], tr["y"]).predict(te[FEATS])
        te["E"] = np.maximum(lo - te["y"], te["y"] - hi)
        oof.append(te)
    oof = pd.concat(oof)
    corr = {p: float(np.quantile(oof.loc[oof["pos"] == p, "E"], 1 - ALPHA)) for p in POS}
    return qs, corr


def cqr_intervals(qs, corr, d):
    k = d["pos"].map(corr).to_numpy()
    lo = np.clip(qs[ALPHA / 2].predict(d[FEATS]) - k, 0, None)
    hi = qs[1 - ALPHA / 2].predict(d[FEATS]) + k
    return lo, np.maximum(hi, lo + 0.5)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--freeze", action="store_true")
    args = ap.parse_args(argv)
    d = prep(build_matrix())
    train, test = d[d["season"] < 2025], d[d["season"] == 2025].copy()
    print(f"played rows: {len(d)} (train 2021-24 {len(train)}, held-out 2025 {len(test)})")
    y, pos = test["y"].to_numpy(), test["pos"].to_numpy()

    lo_b, hi_b = shipped_intervals(test["pos"], test["mu"], test["base_sd"])
    res = {"base": summarize(y, lo_b, hi_b, pos)}

    c_by = calibrate_scale(train)
    vm = fit_var(train)
    lo_v, hi_v, _ = var_intervals(vm, test, c_by)
    res["var"] = summarize(y, lo_v, hi_v, pos)

    qs, corr = fit_cqr(train)
    lo_q, hi_q = cqr_intervals(qs, corr, test)
    res["cqr"] = summarize(y, lo_q, hi_q, pos)

    print(f"\nvar-model scale c by pos (LOSO): {c_by} · CQR conformal widen by pos: "
          + str({p: round(v, 2) for p, v in corr.items()}))
    print("\nheld-out 2025 (played games) — cov90 / mean width / interval score (lower better)")
    print(f"  {'pos':4} " + "".join(f"{k:>26}" for k in res))
    for p in list(POS) + ["ALL"]:
        print(f"  {p:4} " + "".join(f"{res[k][p]['cov90']:>9.3f} {res[k][p]['width']:>6.1f} {res[k][p]['iscore']:>8.2f}" for k in res))

    # which factors drive spread (permutation importance on the var model, held-out)
    from sklearn.inspection import permutation_importance
    pi = permutation_importance(vm, test[FEATS], (test["y"] - test["mu"]) ** 2, n_repeats=3, random_state=0,
                                scoring="neg_mean_poisson_deviance")
    imp = sorted(zip(FEATS, pi.importances_mean), key=lambda t: -t[1])
    print("\nvar-model factor importance (held-out Poisson deviance drop):")
    for f, v in imp[:12]:
        print(f"  {f:18} {v:8.3f}")

    report = {"results": res, "var_scale": c_by, "cqr_corr": corr, "importance": {f: float(v) for f, v in imp},
              "n_train": len(train), "n_test": len(test)}
    (ROOT / "backtest" / "sd_model_report.json").write_text(json.dumps(report, indent=1))

    if args.freeze:
        winner = min(("base", "var", "cqr"), key=lambda k: res[k]["ALL"]["iscore"])
        print(f"\nwinner on held-out interval score: {winner}")
        if winner == "base":
            print("  base wins — nothing frozen."); return 0
        allp = d  # refit on 2021-25
        if winner == "var":
            c_all = calibrate_scale(allp)
            obj = {"kind": "var", "model": fit_var(allp), "scale": c_all, "feats": FEATS}
        else:
            q_all, corr_all = fit_cqr(allp)
            obj = {"kind": "cqr", "q": q_all, "corr": corr_all, "feats": FEATS}
        MODEL_PKL.write_bytes(pickle.dumps(obj))
        params = json.loads(PARAMS.read_text())
        params["sd_model"] = {"kind": obj["kind"], "pickle": "model/sd_model.pkl", "feats": FEATS,
                              "held_out_2025": res, "scale": obj.get("scale"),
                              "corr": obj.get("corr")}
        PARAMS.write_text(json.dumps(params, indent=1))
        print(f"  froze {obj['kind']} -> model/sd_model.pkl + params.json['sd_model']")
    return 0


if __name__ == "__main__":
    sys.exit(main())
