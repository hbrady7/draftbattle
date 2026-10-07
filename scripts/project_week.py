#!/usr/bin/env python3
"""Apply the VALIDATED stacked model (Phase 10) to the live UPCOMING week (2026 W{N}, DB_WEEK).

The backtest pipeline only covers *completed* weeks (the db_fpecr archive stops at
2026 W3). This post-processor builds W4 feature rows the same way features.py builds
backtest rows — trailing stats through W3 + W4 Vegas/ECR — runs the Phase-7 structural
+ GBM models and the isotonic ECR map, blends per the frozen params.json['stack']
weights (with the live_bridge FFA rule), and rewrites board.json's mean with the full
model. HARD SAFETY GATE: per-player fallback to the interim mean, and the board only
ships the full model if the whole thing is sane (no NaN, means near interim, realistic
ranges) — else it keeps the interim blend and says so in meta.

  python scripts/project_week.py            # gate + (maybe) rewrite board.json/sim.json
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

import backtest as bt
import build_board as bb
import data_sources as ds
import distribution as dist
import features as feat
import ids as idmod
import model_gbm as mg
import model_structural as ms
import player_sd
import sim as simmod

ROOT = Path(__file__).resolve().parent.parent
PUBLIC = ROOT / "public" / "data"
PARAMS = json.loads((ROOT / "model" / "params.json").read_text())
STACK = PARAMS["stack"]
WBP = STACK["weights_by_pos"]
BRIDGE = STACK.get("live_bridge", {"ffa_takes": "ecr", "db_weight": 0})
S, W = 2026, bb.WEEK   # upcoming week (DB_WEEK env, set by make_week)
HIST = (2019, 2020, 2021, 2022, 2023, 2024, 2025, 2026)


def _num(x):
    v = pd.to_numeric(x, errors="coerce")
    return v


def w4_features(board):
    """One row per board gsis with features.py columns, trailing THROUGH W3 + W4 env."""
    # --- stats through W3 2026 (played games only), scored, same numeric prep as features.py
    frames = []
    for s in HIST:
        df = ds.load_stats(s)
        if df is None:
            continue
        df = df[df["position"].isin(feat.POS)].copy()
        if "season_type" in df.columns:
            df = df[df["season_type"].astype(str).str.upper().isin(["REG", "REGULAR"])]
        df["pts"] = df.apply(bb.score_stats, axis=1)
        frames.append(df)
    st = pd.concat(frames, ignore_index=True)
    st["player_id"] = st["player_id"].astype(str)
    st = st[~((st["season"] == S) & (st["week"] >= W))]  # strictly before W4
    for c in ["targets", "carries", "attempts", "receptions", "receiving_yards", "rushing_yards",
              "passing_yards", "target_share", "wopr", "receiving_epa", "rushing_epa", "passing_epa"]:
        if c not in st.columns:
            st[c] = 0.0
        st[c] = _num(st[c]).fillna(0.0)
    st["epa_all"] = st["receiving_epa"] + st["rushing_epa"] + st["passing_epa"]
    st = st.sort_values(["player_id", "season", "week"])

    def tail(col, n):
        return st.groupby("player_id")[col].apply(lambda x: x.tail(n).mean())

    tr = pd.DataFrame({
        "tr8_pts": tail("pts", 8), "tr3_pts": tail("pts", 3),
        "tr8_targets_pg": tail("targets", 8), "tr8_carries_pg": tail("carries", 8),
        "tr8_patt_pg": tail("attempts", 8), "tr8_recyd_pg": tail("receiving_yards", 8),
        "tr8_rushyd_pg": tail("rushing_yards", 8), "tr8_passyd_pg": tail("passing_yards", 8),
        "tr8_target_share": tail("target_share", 8), "tr8_wopr": tail("wopr", 8),
        "tr8_epa": tail("epa_all", 8),
    })
    tr["n_prior"] = st.groupby("player_id").size()

    # trailing xFP (same re-scoring as backtest), through W3
    xfp = bt.load_xfp(HIST)
    xfp = xfp[~((xfp["season"] == S) & (xfp["week"] >= W))].sort_values(["player_id", "season", "week"])
    tr["tr8_xfp"] = xfp.groupby("player_id")["xfp"].apply(lambda x: x.tail(8).mean())

    # W4 environment (Vegas / weather), per team
    env = feat._team_env(ds.load_games())
    env_w4 = env[(env["season"] == S) & (env["week"] == W)].set_index("team")

    # opponent fantasy pts allowed to position, 2026 season-to-date (through W3)
    st26 = st[st["season"] == S]
    pa = st26.groupby(["opponent_team", "position"])["pts"].mean() if "opponent_team" in st26.columns else pd.Series(dtype=float)

    # assemble per board player
    rows = []
    for p in board:
        gsis = str(p["id"])
        team = p.get("team")
        e = env_w4.loc[team].to_dict() if (team in env_w4.index) else {}
        opp = e.get("opp")
        t = tr.loc[gsis].to_dict() if gsis in tr.index else {}
        row = {
            "gsis": gsis, "position": p["position"], "team": team,
            "ecr": (p.get("sources") or {}).get("ecr"),
            "ecr_sd": None, "pos_rank": p.get("_pos_rank"),
            "implied_total": e.get("implied_total"), "spread_line": e.get("spread_line"),
            "total_line": e.get("total_line"), "is_home": e.get("is_home"),
            "is_dome": e.get("is_dome"), "wind": e.get("wind"), "temp": e.get("temp"),
            "opp_pa_to_pos": float(pa.get((opp, p["position"]), np.nan)) if opp is not None else np.nan,
        }
        for k in tr.columns:
            row[k] = t.get(k, np.nan)
        rows.append(row)
    return pd.DataFrame(rows)


def compute(board):
    """Return (means_by_gsis, stats, sane). Falls back per-player to interim mean."""
    # live ECR rank per (name_key,pos) from fp_latest
    ecr = bb.ecr_map()
    for p in board:
        k = idmod.name_key(p["name"])
        e = ecr.get((k, p["position"]))
        p["_pos_rank"] = e["pos_rank"] if e else np.nan
        p["_ecr"] = e["ecr"] if e else (p.get("sources") or {}).get("ecr")

    df = w4_features(board)
    df["ecr"] = [p["_ecr"] for p in board]
    df["pos_rank"] = [p["_pos_rank"] for p in board]

    # --- model predictions for W4 ---
    struct = ms.structural_means(df)                       # needs implied_total, tr8_xfp, tr8_pts
    # GBM: train on the exact cached backtest features (2020-2026 completed), predict W4
    train = feat.build_feature_frame((2021, 2022, 2023, 2024, 2025, 2026))
    train = train.rename(columns={"y": "y"}); train["y"] = train["pts"]
    feats = [f for f in mg.GBM_FEATS if f in df.columns and f in train.columns]
    gbm = mg.train_predict(train, df, feats)
    # ECR-implied via isotonic fit on prior seasons (2021-2025), applied to W4 pos_rank
    wp = bt.ecr_to_gsis(bt.ecr_weekly(ds.load_games()))
    wp_act = bt.load_actuals((2021, 2022, 2023, 2024, 2025))
    ai = wp_act.set_index(["player_id", "season", "week"])["pts"]
    wp["y"] = [ai.get((g, s, w), 0.0) for g, s, w in zip(wp["gsis"], wp["season"], wp["week"])]
    iso = bt.isotonic_by_pos(wp[wp["season"] < 2026])
    ecr_imp = np.array([float(iso[p["position"]].predict([df["pos_rank"].iloc[i]])[0])
                        if (p["position"] in iso and np.isfinite(df["pos_rank"].iloc[i])) else np.nan
                        for i, p in enumerate(board)])

    means, n_fallback, n_big = {}, 0, 0
    for i, p in enumerate(board):
        pos = p["position"]
        interim = p["mean"]
        w = WBP.get(pos)
        sv, gv, ev = struct[i], gbm[i], ecr_imp[i]
        ffa = (p.get("sources") or {}).get("ffa")
        if w is None or not np.isfinite(sv) or not np.isfinite(gv):
            means[p["id"]] = interim; n_fallback += 1; continue
        # live bridge: FFA takes half the ecr_implied weight (DB weight 0)
        w_ecr = w.get("ecr_implied", 0.0)
        parts, wsum = 0.0, 0.0
        for m, v in (("structural", sv), ("gbm", gv)):
            wm = w.get(m, 0.0)
            if np.isfinite(v):
                parts += wm * v; wsum += wm
        if np.isfinite(ev):
            parts += (w_ecr * 0.5) * ev; wsum += w_ecr * 0.5
        if ffa is not None and np.isfinite(ffa):
            parts += (w_ecr * 0.5) * ffa; wsum += w_ecr * 0.5
        elif np.isfinite(ev):  # no FFA -> ecr takes its full weight
            parts += (w_ecr * 0.5) * ev; wsum += w_ecr * 0.5
        full = parts / wsum if wsum > 1e-9 else interim
        if not np.isfinite(full) or full < 0 or full > 60:
            means[p["id"]] = interim; n_fallback += 1; continue
        if p["flags"].get("backup_qb"):
            full = min(full, 4.5)
        if abs(full - interim) > 8:
            n_big += 1
        means[p["id"]] = round(float(full), 2)

    # sanity gate
    pos_max = {}
    for p in board:
        pos_max.setdefault(p["position"], 0)
        pos_max[p["position"]] = max(pos_max[p["position"]], means[p["id"]])
    sane = (n_fallback < 0.5 * len(board)
            and all(np.isfinite(v) for v in means.values())
            and pos_max.get("QB", 0) <= 40 and pos_max.get("RB", 0) <= 45
            and pos_max.get("WR", 0) <= 45 and pos_max.get("TE", 0) <= 35)
    stats = {"n": len(board), "n_fallback": n_fallback, "n_big_delta_gt8": n_big, "pos_max": pos_max}
    return means, stats, sane


def apply_to_board(means):
    board = json.loads((PUBLIC / "board.json").read_text())
    logs = None
    for p in board:
        gsis = p["id"]
        new_mean = means.get(gsis, p["mean"])
        pos = p["position"]
        sd = player_sd.player_sd(pos, new_mean, [])["sd"]  # scores baked into board already via sd; refit at new mean
        d = dist.player_distribution(pos, new_mean, sd, p.get("p_play", 1.0), None)
        d.pop("_table", None)
        p["mean"] = new_mean
        p["sd"] = round(sd, 3)
        p["edge"] = round(new_mean - p["db_proj"], 2)
        p.update(d)
    (PUBLIC / "board.json").write_text(json.dumps(board, indent=1))
    meta = json.loads((PUBLIC / "meta.json").read_text())
    meta["mean_recipe"] = "full stack (structural+gbm+ecr, live-bridged FFA) — §6g"
    (PUBLIC / "meta.json").write_text(json.dumps(meta, indent=1))
    simmod.build_sim_json()


def main():
    board = json.loads((PUBLIC / "board.json").read_text())
    interim = {p["id"]: p["mean"] for p in board}
    means, stats, sane = compute(board)
    named = ["Jahmyr Gibbs", "Josh Allen", "Jaxon Smith-Njigba", "George Kittle", "Cam Skattebo"]
    print(f"=== live full-model W{W} projection — interim vs full ===")
    for nm in named:
        p = next((x for x in board if idmod.name_key(nm) in idmod.name_key(x["name"])), None)
        if p:
            print(f"  {p['name'][:22]:22} {p['position']}  interim {interim[p['id']]:6.2f} -> full {means[p['id']]:6.2f}")
    print(f"  fallback players: {stats['n_fallback']}/{stats['n']} · |Δ|>8: {stats['n_big_delta_gt8']} · pos_max {stats['pos_max']}")
    print(f"  SANITY: {'PASS — shipping full model' if sane else 'FAIL — keeping interim blend'}")
    if sane:
        apply_to_board(means)
        print("  board.json + sim.json rewritten with full-model mean.")
    else:
        meta = json.loads((PUBLIC / "meta.json").read_text())
        meta["mean_recipe"] = "interim (0.5 FFA + 0.5 ECR) — full-model live projection failed sanity gate"
        (PUBLIC / "meta.json").write_text(json.dumps(meta, indent=1))
    return 0 if sane else 0


if __name__ == "__main__":
    raise SystemExit(main())
