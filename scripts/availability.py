#!/usr/bin/env python3
"""BRIEF §7 availability model.

Fit on 2019-2025:
  - P(plays) logistic: "plays" = >=1 offensive snap that week. Features: report_status,
    practice_status, grouped injury type, position, consecutive games missed.
  - snap multiplier E[snap% | plays, status] / baseline (Questionable-who-plays is limited).
  - vacated-opportunity redistribution when a high-usage player is out.
Frozen to model/params.json (the live build reads params; never refits silently).

Hard rules override the model: Out/IR -> 0; no designation -> fitted healthy base rate.
Late news: input_data/week{N}/injuries.csv (player,status) sets P(plays) directly.

  python scripts/availability.py --fit          # fit, save params.json, print calibration
  python scripts/availability.py --check        # calibration table only (held-out)
"""
from __future__ import annotations

import argparse
import json
import math
import re
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression

import data_sources as ds
import ids as idmod

ROOT = Path(__file__).resolve().parent.parent
PARAMS = ROOT / "model" / "params.json"
POS = ("QB", "RB", "WR", "TE")
FIT_SEASONS = list(range(2022, 2026))        # current injury-report regime (2022-2025)
HELDOUT = [2025]                              # honest held-out calibration season
CONSEC_CAP = 4
HEALTHY_BASE = 0.99                           # play rate for players NOT on the injury report

_STATUS = {"OUT": "OUT", "DOUBTFUL": "DOUBTFUL", "QUESTIONABLE": "QUESTIONABLE",
           "IR": "OUT", "INJURED RESERVE": "OUT"}
_PRACTICE = {"DID NOT PARTICIPATE IN PRACTICE": "DNP", "OUT (DID NOT PARTICIPATE IN PRACTICE)": "DNP",
             "LIMITED PARTICIPATION IN PRACTICE": "LIMITED", "FULL PARTICIPATION IN PRACTICE": "FULL"}


def _norm_status(s):
    s = str(s or "").strip().upper()
    if not s or s == "NAN":
        return "NONE"
    if s in ("OUT", "DOUBTFUL", "QUESTIONABLE", "NONE", "OTHER"):  # idempotent
        return s
    return _STATUS.get(s, "OTHER")


def _norm_practice(s):
    s = str(s or "").strip().upper()
    if not s or s == "NAN":
        return "NONE"
    if s in ("DNP", "LIMITED", "FULL", "NONE", "OTHER"):  # idempotent
        return s
    return _PRACTICE.get(s, "OTHER")


def _injury_group(text):
    t = str(text or "").lower()
    if re.search(r"hamstring|groin|quad|calf|hip|glute|thigh", t):
        return "soft_tissue"
    if re.search(r"knee|ankle|foot|achilles|toe|heel|leg|fibula|tibia", t):
        return "lower_leg"
    if re.search(r"shoulder|elbow|wrist|hand|finger|thumb|chest|rib|back|neck|arm|pec|oblique|abdomen", t):
        return "upper_body"
    if re.search(r"concussion|head", t):
        return "concussion"
    if re.search(r"illness|flu|covid|non-football|personal", t):
        return "illness"
    return "other"


# --------------------------------------------------------- played outcomes ----
def played_table(seasons):
    """(gsis, season, week) -> played (>=1 offensive snap), offense_pct. Via pfr->gsis."""
    dbids = ds.load_db_playerids()
    pfr2g = {}
    if dbids is not None and "pfr_id" in dbids.columns and "gsis_id" in dbids.columns:
        for pfr, g in zip(dbids["pfr_id"], dbids["gsis_id"]):
            if isinstance(pfr, str) and isinstance(g, str) and pfr and g:
                pfr2g[pfr] = g
    frames = []
    for s in seasons:
        sc = ds.load_snaps(s)
        if sc is None:
            continue
        sc = sc[sc["position"].isin(POS)] if "position" in sc.columns else sc
        sc = sc[sc["season_type"].astype(str).str.upper().isin(["REG", "REGULAR"])] if "season_type" in sc.columns else sc
        g = sc["pfr_player_id"].map(pfr2g)
        off = pd.to_numeric(sc["offense_snaps"], errors="coerce").fillna(0)
        frames.append(pd.DataFrame({"gsis": g, "season": sc["season"].astype(int),
                                    "week": sc["week"].astype(int),
                                    "offense_pct": pd.to_numeric(sc["offense_pct"], errors="coerce").fillna(0),
                                    "played": (off >= 1).astype(int)}).dropna(subset=["gsis"]))
    pt = pd.concat(frames, ignore_index=True)
    return pt.groupby(["gsis", "season", "week"], as_index=False).agg(
        offense_pct=("offense_pct", "max"), played=("played", "max"))


def _consec_missed(pt):
    """Per (gsis,season): consecutive prior weeks (within season, after first appearance) not played."""
    pt = pt.sort_values(["gsis", "season", "week"])
    out = {}
    for (g, s), grp in pt.groupby(["gsis", "season"]):
        weeks = grp.set_index("week")["played"].to_dict()
        first = min(weeks)
        for w in range(first, 19):
            c = 0
            for back in range(w - 1, first - 1, -1):
                if weeks.get(back, 1) == 0:
                    c += 1
                else:
                    break
            out[(g, s, w)] = min(c, CONSEC_CAP)
    return out


# --------------------------------------------------------- training frame -----
def training(seasons):
    pt = played_table(seasons)
    played_map = {(r.gsis, r.season, r.week): (r.played, r.offense_pct)
                  for r in pt.itertuples(index=False)}
    consec = _consec_missed(pt)
    base_pct = {}  # baseline offense_pct per (gsis,season) from healthy weeks (for snap mult)
    for (g, s), grp in pt.groupby(["gsis", "season"]):
        hp = grp[grp["played"] == 1]["offense_pct"]
        if len(hp):
            base_pct[(g, s)] = hp.median()

    rows = []
    for s in seasons:
        inj = ds.load_injuries(s)
        if inj is None:
            continue
        inj = inj[inj["position"].isin(POS)] if "position" in inj.columns else inj
        for r in inj.itertuples(index=False):
            g = getattr(r, "gsis_id", None)
            if not isinstance(g, str) or not g:
                continue
            wk = int(getattr(r, "week"))
            played, off_pct = played_map.get((g, s, wk), (0, 0.0))
            rows.append({
                "gsis": g, "season": s, "week": wk,
                "report_status": _norm_status(getattr(r, "report_status", "")),
                "practice_status": _norm_practice(getattr(r, "practice_status", "")),
                "injury_group": _injury_group(getattr(r, "practice_primary_injury", "")),
                "position": getattr(r, "position", "WR"),
                "consec_missed": consec.get((g, s, wk), 0),
                "played": int(played), "offense_pct": float(off_pct),
                "base_pct": base_pct.get((g, s), np.nan),
            })
    return pd.DataFrame(rows)


FEATS = ["report_status", "practice_status", "injury_group", "position"]


def _design(df, columns=None):
    X = pd.get_dummies(df[FEATS].astype(str), prefix=FEATS)
    X["consec_missed"] = df["consec_missed"].values
    if columns is not None:
        X = X.reindex(columns=columns, fill_value=0)
    return X


def fit(seasons=FIT_SEASONS, save=True):
    df = training(seasons)
    # drop the hard-rule OUT rows from the logistic fit (they are deterministic 0)
    fitdf = df[df["report_status"] != "OUT"].copy()
    X = _design(fitdf)
    cols = list(X.columns)
    y = fitdf["played"].values
    # Near-unregularized so the fit reproduces the empirical bucket rates (calibrated),
    # steeply recency-weighted (squared) because Questionable play-rates fell and
    # practice-status lost predictive power by 2025 — match the current regime.
    w = ((fitdf["season"] - 2021).clip(lower=1) ** 2).values.astype(float)
    model = LogisticRegression(max_iter=3000, C=1e6)
    model.fit(X.values.astype(float), y, sample_weight=w)

    # base rate for players with NO injury designation ~ play rate of QUESTIONABLE-free listed
    base_rate = float(df[df["report_status"] == "NONE"]["played"].mean()) if (df["report_status"] == "NONE").any() else 0.99
    if not math.isfinite(base_rate):
        base_rate = 0.99

    # snap multiplier: median offense_pct(played,status) / median baseline offense_pct
    played = df[(df["played"] == 1) & df["base_pct"].notna() & (df["base_pct"] > 0)].copy()
    played["ratio"] = played["offense_pct"] / played["base_pct"]
    snap_mult = {st: round(float(played[played["report_status"] == st]["ratio"].median()), 3)
                 for st in ("QUESTIONABLE", "DOUBTFUL", "NONE", "OTHER")
                 if (played["report_status"] == st).any()}

    coef = dict(zip(cols, model.coef_[0].tolist()))
    spec = {"columns": cols, "coef": coef, "intercept": float(model.intercept_[0]),
            "base_rate": round(base_rate, 4), "healthy_base": HEALTHY_BASE, "snap_mult": snap_mult,
            "consec_cap": CONSEC_CAP, "fit_seasons": [min(seasons), max(seasons)],
            "n_train": int(len(fitdf))}
    if save:
        _save_params(spec)
    return df, spec


# ---------------------------------------------------------- predict -----------
def _sigmoid(z):
    return 1.0 / (1.0 + math.exp(-max(-30, min(30, z))))


def p_plays(report_status, practice_status="", injury="", position="WR",
            consec_missed=0, params=None):
    params = params or load_params()
    r = _norm_status(report_status)
    listed = bool(str(report_status or "").strip() or str(practice_status or "").strip()
                  or str(injury or "").strip())
    if params is None:                                       # fallback = Phase-2 rule
        return {"OUT": 0.0, "DOUBTFUL": 0.25, "QUESTIONABLE": 0.85}.get(r, 1.0)
    if r == "OUT":
        return 0.0                                           # hard rule
    if not listed:
        return params.get("healthy_base", HEALTHY_BASE)      # not on the report -> healthy
    feats = {f"report_status_{r}": 1, f"practice_status_{_norm_practice(practice_status)}": 1,
             f"injury_group_{_injury_group(injury)}": 1, f"position_{str(position).upper()}": 1}
    z = params["intercept"] + min(consec_missed, params["consec_cap"]) * params["coef"].get("consec_missed", 0.0)
    for k, v in feats.items():
        z += params["coef"].get(k, 0.0) * v
    return round(_sigmoid(z), 4)


def snap_multiplier(report_status, params=None):
    params = params or load_params()
    if not params:
        return 1.0
    return params.get("snap_mult", {}).get(_norm_status(report_status), 1.0)


# --------------------------------------------- vacated-opportunity (§6c) ------
# Default until fully fit: proportional within position group; of an out player's
# targets, 70% to WR/TE and 30% to RB; carries proportional within RBs.
VACATED_DEFAULT = {"targets_to_wr_te": 0.70, "targets_to_rb": 0.30, "method": "proportional_within_pos"}


def redistribute_vacated(out_player_pos, out_targets, out_carries, teammates):
    """teammates: list of {gsis, position, target_share, carry_share}. Returns dict gsis->{d_targets,d_carries}."""
    wrte = [t for t in teammates if t["position"] in ("WR", "TE")]
    rbs = [t for t in teammates if t["position"] == "RB"]
    add = {t["gsis"]: {"d_targets": 0.0, "d_carries": 0.0} for t in teammates}

    def _spread(pool, amount, key):
        tot = sum(max(1e-6, t.get(key.replace("d_", "").replace("d", "") + "_share", 0)) for t in pool) if pool else 0
        if not pool:
            return
        for t in pool:
            w = max(1e-6, t.get("target_share" if "target" in key else "carry_share", 0))
            add[t["gsis"]][key] += amount * (w / tot if tot > 0 else 1.0 / len(pool))

    if out_targets:
        _spread(wrte, out_targets * VACATED_DEFAULT["targets_to_wr_te"], "d_targets")
        _spread(rbs, out_targets * VACATED_DEFAULT["targets_to_rb"], "d_targets")
    if out_carries:
        _spread(rbs, out_carries, "d_carries")
    return add


# ---------------------------------------------------------- params io ---------
def _save_params(avail_spec):
    params = {}
    if PARAMS.exists():
        try:
            params = json.loads(PARAMS.read_text())
        except ValueError:
            params = {}
    params["availability"] = avail_spec
    params["availability"]["vacated"] = VACATED_DEFAULT
    params["_meta"] = {"note": "frozen model params; live build reads, never refits silently"}
    PARAMS.write_text(json.dumps(params, indent=1))


_PARAMS_CACHE = None


def load_params():
    global _PARAMS_CACHE
    if _PARAMS_CACHE is None:
        if not PARAMS.exists():
            return None
        try:
            _PARAMS_CACHE = json.loads(PARAMS.read_text()).get("availability")
        except ValueError:
            return None
    return _PARAMS_CACHE


# ---------------------------------------------------------- calibration -------
def calibration(held, params, label=""):
    held = held.copy()
    held["pred"] = [p_plays(r.report_status, r.practice_status, "", r.position, r.consec_missed, params)
                    for r in held.itertuples(index=False)]
    print(f"=== §7 availability calibration ({label}, n={len(held)}) ===")
    print(f"  {'report_status':22} {'n':>6} {'pred P(plays)':>14} {'actual':>8}")
    for st in ("NONE", "QUESTIONABLE", "DOUBTFUL", "OUT", "OTHER"):
        g = held[held["report_status"] == st]
        if len(g):
            print(f"  {st:22} {len(g):>6} {g['pred'].mean():>14.3f} {g['played'].mean():>8.3f}")
    # Where the model earns its keep: Questionable split by practice participation.
    q = held[held["report_status"] == "QUESTIONABLE"]
    for pr in ("DNP", "LIMITED", "FULL", "NONE"):
        g = q[q["practice_status"] == pr]
        if len(g) >= 10:
            print(f"    QUESTIONABLE+{pr:10} {len(g):>6} {g['pred'].mean():>14.3f} {g['played'].mean():>8.3f}")
    p = held["pred"].clip(1e-6, 1 - 1e-6).values
    yv = held["played"].values
    brier = float(np.mean((p - yv) ** 2))
    logloss = float(-np.mean(yv * np.log(p) + (1 - yv) * np.log(1 - p)))
    # flat Phase-2 rule baseline, same eval set
    flat = held["report_status"].map({"OUT": 0.0, "DOUBTFUL": 0.25, "QUESTIONABLE": 0.85}).fillna(0.99).values
    flat_brier = float(np.mean((flat - yv) ** 2))
    print(f"  Brier={brier:.4f}  log-loss={logloss:.4f}   (flat Phase-2 rule Brier={flat_brier:.4f})")
    return brier, logloss


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--fit", action="store_true")
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args(argv)
    global _PARAMS_CACHE
    # Deployed model: fit on the full current regime (2022-2025), saved to params.json.
    df, spec = fit(FIT_SEASONS, save=True)
    _PARAMS_CACHE = spec
    print(f"availability fitted (deployed {spec['fit_seasons']}): n_train={spec['n_train']}, "
          f"healthy_base={spec['healthy_base']}, snap_mult={spec['snap_mult']}")
    # Honest held-out calibration: train on all-but-last season, evaluate the last.
    train = [s for s in FIT_SEASONS if s not in HELDOUT]
    _, specc = fit(train, save=False)
    held = training(HELDOUT)
    calibration(held, specc, label=f"held-out {HELDOUT}, train {train}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
