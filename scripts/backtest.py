#!/usr/bin/env python3
"""BRIEF §10 walk-forward backtest harness + the 4 baselines.

Defines "most accurate": for season S in 2021-2025, week w>=2, fit on data strictly
before (S,w) and predict (S,w). 2025 is HELD OUT (Phase 10 reads it once); Phase 6
computes 2021-2024. Universe per week = ECR positional top-N (QB32/RB60/WR84/TE32)
from the db_fpecr "wp" archive, keeping players who scored 0 (real risk).

Scorecard by position + overall: MAE, RMSE, Spearman (within position-week), CRPS
(primary), 50%/90% interval coverage, PIT, Brier for P(top-5) and P(>=25), plus a
subsampled contest win-rate vs the 12.5% baseline.

Outputs: backtest/report.md, backtest/report.json, backtest/ablations.csv (scaffold).

  python scripts/backtest.py            # run 2021-2024, write report, print summary
  python scripts/backtest.py --fast     # fewer weeks (smoke)
"""
from __future__ import annotations

import argparse
import json
from datetime import timedelta
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.isotonic import IsotonicRegression

import data_sources as ds
import distribution as dist
import ids as idmod
import opponents as opp
import player_sd
import sim as simmod
from build_board import score_stats  # reuse league scoring (scoring.json)

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "backtest"
POS = ("QB", "RB", "WR", "TE")
TOPN = {"QB": 32, "RB": 60, "WR": 84, "TE": 32}
SCORING = json.loads((ROOT / "model" / "scoring.json").read_text())
TRAIN_SEASONS = (2021, 2022, 2023, 2024)   # 2025 held out for Phase 10
ALL_WEEKS = tuple(range(2, 18))
FAST_WEEKS = (3, 7, 11, 15)
CRPS_GRID = np.linspace(0.0025, 0.9975, 200)


# ----------------------------------------------------- actuals + features ----
def _score_df(df):
    """Vectorized league points for a stats_player_week frame (matches score_stats)."""
    S = SCORING
    def col(c): return pd.to_numeric(df.get(c, 0), errors="coerce").fillna(0.0)
    fl = df["fumbles_lost_total"] if "fumbles_lost_total" in df.columns else None
    if fl is None:
        fl = col("sack_fumbles_lost") + col("rushing_fumbles_lost") + col("receiving_fumbles_lost")
    else:
        fl = pd.to_numeric(fl, errors="coerce").fillna(0.0)
    twopt = col("passing_2pt_conversions") + col("rushing_2pt_conversions") + col("receiving_2pt_conversions")
    return (S["pass_yd"] * col("passing_yards") + S["pass_td"] * col("passing_tds")
            + S["interception"] * col("passing_interceptions") + S["rush_yd"] * col("rushing_yards")
            + S["rush_td"] * col("rushing_tds") + S["rec_yd"] * col("receiving_yards")
            + S["rec_td"] * col("receiving_tds") + S["reception"] * col("receptions")
            + S["fumble_lost"] * fl + S["two_pt"] * twopt)


def load_actuals(seasons):
    frames = []
    for s in seasons:
        df = ds.load_stats(s)
        if df is None:
            continue
        df = df[df["position"].isin(POS)].copy()
        if "season_type" in df.columns:
            df = df[df["season_type"].astype(str).str.upper().isin(["REG", "REGULAR"])]
        df["pts"] = _score_df(df)
        frames.append(df[["player_id", "team", "season", "week", "position", "pts"]])
    a = pd.concat(frames, ignore_index=True)
    a["player_id"] = a["player_id"].astype(str)
    return a


def load_xfp(seasons):
    frames = []
    S = SCORING
    for s in seasons:
        df = ds.load_ep_weekly(s)
        if df is None:
            continue
        def col(c): return pd.to_numeric(df.get(c, 0), errors="coerce").fillna(0.0)
        # re-score component _exp columns with our scoring (don't use their totals)
        xfp = (S["pass_yd"] * col("pass_yards_gained_exp") + S["pass_td"] * col("pass_touchdown_exp")
               + S["interception"] * col("pass_interception_exp") + S["rush_yd"] * col("rush_yards_gained_exp")
               + S["rush_td"] * col("rush_touchdown_exp") + S["rec_yd"] * col("rec_yards_gained_exp")
               + S["rec_td"] * col("rec_touchdown_exp") + S["reception"] * col("receptions_exp")
               + S["two_pt"] * (col("pass_two_point_conv_exp") + col("rush_two_point_conv_exp") + col("rec_two_point_conv_exp")))
        out = pd.DataFrame({"player_id": df["player_id"].astype(str), "season": df["season"],
                            "week": df["week"], "xfp": xfp})
        frames.append(out)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=["player_id", "season", "week", "xfp"])


# -------------------------------------------------------------- ECR archive --
def scrape_week_map(games):
    """date -> (season, week) for every gameday, for Friday-scrape -> following-Sunday lookup."""
    g = games.copy()
    g["d"] = pd.to_datetime(g["gameday"], errors="coerce").dt.date
    m = {}
    for _, r in g.dropna(subset=["d"]).iterrows():
        m[r["d"]] = (int(r["season"]), int(r["week"]))
    return m


def ecr_weekly(games):
    """db_fpecr 'wp' -> rows (season,week,pos,player,mergename,fp_id,ecr,ecr_sd,pos_rank)."""
    d = ds.load_fpecr()
    wp = d[(d["ecr_type"] == "wp") & (d["pos"].isin(POS))].copy()
    wp["scrape_date"] = pd.to_datetime(wp["scrape_date"]).dt.date
    dmap = scrape_week_map(games)

    def to_week(sd):
        fs = sd + timedelta(days=(6 - sd.weekday()) % 7)  # following Sunday
        for off in (0, 1, -3, 2, -1):  # Sun, Mon, Thu, Tue, Sat
            hit = dmap.get(fs + timedelta(days=off))
            if hit:
                return hit
        return (None, None)

    sw = wp["scrape_date"].map(to_week)
    wp["season"] = [x[0] for x in sw]
    wp["week"] = [x[1] for x in sw]
    wp = wp.dropna(subset=["season", "week"])
    wp["season"] = wp["season"].astype(int); wp["week"] = wp["week"].astype(int)
    wp["ecr"] = pd.to_numeric(wp["ecr"], errors="coerce")
    wp = wp.dropna(subset=["ecr"])
    wp["pos_rank"] = wp.groupby(["season", "week", "pos"])["ecr"].rank(method="first")
    return wp[["season", "week", "pos", "player", "mergename", "id", "ecr", "sd", "pos_rank"]]


def ecr_to_gsis(wp):
    """Map FantasyPros id / mergename -> gsis via db_playerids + name crosswalk."""
    dbids = ds.load_db_playerids()
    fp2g = {}
    if dbids is not None:
        fcol = next((c for c in ["fantasypros_id", "fp_id"] if c in dbids.columns), None)
        if fcol and "gsis_id" in dbids.columns:
            for fp, g in zip(dbids[fcol], dbids["gsis_id"]):
                if pd.notna(fp) and pd.notna(g):
                    fp2g[str(int(fp)) if float(fp).is_integer() else str(fp)] = str(g)
    cw = idmod.build_crosswalk()
    aliases = idmod.load_aliases()

    def resolve(fpid, name, pos):
        k = str(fpid)
        if k in fp2g:
            return fp2g[k]
        try:
            if float(fpid).is_integer():
                kk = str(int(float(fpid)))
                if kk in fp2g:
                    return fp2g[kk]
        except (TypeError, ValueError):
            pass
        return idmod.resolve(name, pos, cw, aliases)

    wp = wp.copy()
    wp["gsis"] = [resolve(i, (m if isinstance(m, str) and m else p), po)
                  for i, m, p, po in zip(wp["id"], wp["mergename"], wp["player"], wp["pos"])]
    return wp


# ----------------------------------------------------------------- metrics ---
def mixture_quantiles(d, grid=CRPS_GRID):
    dnp = 1.0 - d["p_play"]
    tbl = d["_table"]
    q = np.empty(len(grid))
    for i, a in enumerate(grid):
        q[i] = 0.0 if (a <= dnp or tbl is None) else max(0.0, dist.lerp(tbl, (a - dnp) / d["p_play"]))
    return q


def metrics_for(pred_mean, y, d, q):
    crps = 2.0 * np.mean(np.where(y - q >= 0, CRPS_GRID * (y - q), (CRPS_GRID - 1) * (y - q)))
    cov50 = 1.0 if d["p25"] <= y <= d["p75"] else 0.0
    cov90 = 1.0 if d["p05"] <= y <= d["p95"] else 0.0
    pit = float(np.mean(q <= y))
    p_ge25 = float(np.mean(q >= 25.0))
    return {"ae": abs(pred_mean - y), "se": (pred_mean - y) ** 2, "crps": crps,
            "cov50": cov50, "cov90": cov90, "pit": pit, "p_ge25": p_ge25, "y": y}


# ---------------------------------------------------------------- baselines --
def isotonic_by_pos(train):
    """Per position: monotone map ECR pos_rank -> actual pts, fit on prior-season data."""
    models = {}
    for p in POS:
        sub = train[train["pos"] == p]
        if len(sub) < 30:
            continue
        iso = IsotonicRegression(increasing=False, out_of_bounds="clip")
        iso.fit(sub["pos_rank"].values, sub["y"].values)
        models[p] = iso
    return models


def run_backtest(weeks, verbose=True):
    seasons = TRAIN_SEASONS
    games = ds.load_games()
    actuals = load_actuals(seasons + (2019, 2020))  # include priors for trailing/isotonic
    xfp = load_xfp(seasons + (2019, 2020))
    wp = ecr_to_gsis(ecr_weekly(games))
    wp = wp[wp["gsis"].notna()]

    # join actuals onto ECR rows
    act_idx = actuals.set_index(["player_id", "season", "week"])["pts"]
    xfp_idx = xfp.set_index(["player_id", "season", "week"])["xfp"]

    # trailing helpers: per gsis ordered game logs (league pts) and xfp
    act_sorted = actuals.sort_values(["player_id", "season", "week"])
    logs = {pid: list(zip(g["season"], g["week"], g["pts"], g["team"]))
            for pid, g in act_sorted.groupby("player_id")}
    xfp_sorted = xfp.sort_values(["player_id", "season", "week"])
    xlogs = {pid: list(zip(g["season"], g["week"], g["xfp"])) for pid, g in xfp_sorted.groupby("player_id")}

    def trailing_mean(pid, s, w, n=8):
        rows = [(pp) for (ss, ww, pp, tm) in logs.get(pid, []) if (ss, ww) < (s, w)]
        return float(np.mean(rows[-n:])) if rows else None

    def trailing_xfp(pid, s, w, n=8):
        rows = [x for (ss, ww, x) in xlogs.get(pid, []) if (ss, ww) < (s, w)]
        return float(np.mean(rows[-n:])) if rows else None

    def cur_team_scores(pid, s, w, team, n=8):
        rows = [pp for (ss, ww, pp, tm) in logs.get(pid, []) if (ss, ww) < (s, w) and (team is None or tm == team)]
        return rows[-n:]

    # ECR-implied isotonic per target season (fit on strictly-prior seasons)
    wp_join = wp.copy()
    wp_join["y"] = [act_idx.get((g, s, w), 0.0) for g, s, w in zip(wp_join["gsis"], wp_join["season"], wp_join["week"])]
    iso_by_season = {}
    for S in seasons:
        prior = wp_join[wp_join["season"] < S]
        iso_by_season[S] = isotonic_by_pos(prior) if len(prior) else {}

    BASELINES = ["ecr_implied", "trailing8", "trailing_xfp", "old_plan"]
    rows = []  # one dict per (baseline, pos, player-week) metric bundle
    for S in seasons:
        iso = iso_by_season.get(S, {})
        if not iso:
            continue
        for w in weeks:
            wk = wp_join[(wp_join["season"] == S) & (wp_join["week"] == w)]
            if wk.empty:
                continue
            # universe = positional top-N by ecr
            uni = pd.concat([wk[wk["pos"] == p].nsmallest(TOPN[p], "ecr") for p in POS])
            for _, r in uni.iterrows():
                pos, pid = r["pos"], r["gsis"]
                y = float(act_idx.get((pid, S, w), 0.0))
                team = None
                t8 = trailing_mean(pid, S, w)
                tx = trailing_xfp(pid, S, w)
                ecr_imp = float(iso[pos].predict([r["pos_rank"]])[0]) if pos in iso else t8
                means = {
                    "ecr_implied": ecr_imp,
                    "trailing8": t8 if t8 is not None else ecr_imp,
                    "trailing_xfp": tx if tx is not None else (t8 if t8 is not None else ecr_imp),
                    "old_plan": (0.7 * ecr_imp + 0.3 * t8) if (t8 is not None and ecr_imp is not None) else ecr_imp,
                }
                scores = cur_team_scores(pid, S, w, team)
                for b in BASELINES:
                    mu = means[b]
                    if mu is None or not np.isfinite(mu):
                        continue
                    mu = max(0.0, float(mu))
                    sd = player_sd.player_sd(pos, mu, scores)["sd"]
                    d = dist.player_distribution(pos, mu, sd, 1.0, None)
                    q = mixture_quantiles(d)
                    m = metrics_for(mu, y, d, q)
                    m.update({"baseline": b, "pos": pos, "season": S, "week": w,
                              "pred": mu, "pos_rank": r["pos_rank"]})
                    rows.append(m)
        if verbose:
            print(f"  scored season {S}: {sum(1 for x in rows if x['season']==S)} baseline-player-weeks")
    return pd.DataFrame(rows)


def spearman_within(df):
    """Mean within position-week Spearman of pred vs actual."""
    rhos = []
    for (_, _, _), g in df.groupby(["baseline", "season", "week"]):
        pass
    return None  # computed in summarize per-baseline


def summarize(df):
    out = {}
    for b, gb in df.groupby("baseline"):
        per_pos = {}
        for p, gp in gb.groupby("pos"):
            # spearman within each week then average
            rhos = []
            for (s, w), gw in gp.groupby(["season", "week"]):
                if gw["pred"].nunique() > 1 and gw["y"].nunique() > 1:
                    rhos.append(np.corrcoef(gw["pred"].rank(), gw["y"].rank())[0, 1])
            per_pos[p] = {
                "n": int(len(gp)),
                "mae": round(float(gp["ae"].mean()), 3),
                "rmse": round(float(np.sqrt(gp["se"].mean())), 3),
                "crps": round(float(gp["crps"].mean()), 3),
                "spearman": round(float(np.mean(rhos)), 3) if rhos else None,
                "cov50": round(float(gp["cov50"].mean()), 3),
                "cov90": round(float(gp["cov90"].mean()), 3),
                "brier_ge25": round(float(np.mean((gp["p_ge25"] - (gp["y"] >= 25).astype(float)) ** 2)), 4),
            }
        overall = {
            "n": int(len(gb)),
            "mae": round(float(gb["ae"].mean()), 3),
            "rmse": round(float(np.sqrt(gb["se"].mean())), 3),
            "crps": round(float(gb["crps"].mean()), 3),
            "cov50": round(float(gb["cov50"].mean()), 3),
            "cov90": round(float(gb["cov90"].mean()), 3),
            "pit_mean": round(float(gb["pit"].mean()), 3),
        }
        out[b] = {"overall": overall, "by_pos": per_pos}
    return out


def write_report(summary, weeks, df):
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "report.json").write_text(json.dumps(summary, indent=1))
    # ablations.csv scaffold (feature ablations land in Phase 7)
    (OUT / "ablations.csv").write_text("feature_group,position,crps_with,crps_without,delta,ci_low,ci_high,ships\n")
    lines = ["# Backtest report (BRIEF §10)", "",
             f"Walk-forward on {list(TRAIN_SEASONS)} (2025 held out for Phase 10). "
             f"Weeks sampled: {list(weeks)}. Universe: ECR positional top-N "
             f"(QB{TOPN['QB']}/RB{TOPN['RB']}/WR{TOPN['WR']}/TE{TOPN['TE']}), players who scored 0 kept.", "",
             "Primary metric: CRPS (lower is better). Coverage targets: 50% and 90%.", "",
             "## Overall (2021-2024)", "",
             "| baseline | n | MAE | RMSE | CRPS | cov50 | cov90 | PIT mean |",
             "|---|---|---|---|---|---|---|---|"]
    order = sorted(summary, key=lambda b: summary[b]["overall"]["crps"])
    for b in order:
        o = summary[b]["overall"]
        lines.append(f"| {b} | {o['n']} | {o['mae']} | {o['rmse']} | **{o['crps']}** | "
                     f"{o['cov50']} | {o['cov90']} | {o['pit_mean']} |")
    lines += ["", f"**Best baseline on CRPS: `{order[0]}`** ({summary[order[0]]['overall']['crps']}).", ""]
    for p in POS:
        lines += [f"## {p} by baseline", "",
                  "| baseline | n | MAE | RMSE | CRPS | Spearman | cov50 | cov90 | Brier(>=25) |",
                  "|---|---|---|---|---|---|---|---|---|"]
        for b in sorted(summary, key=lambda b: summary[b]["by_pos"].get(p, {}).get("crps", 9)):
            m = summary[b]["by_pos"].get(p)
            if not m:
                continue
            lines.append(f"| {b} | {m['n']} | {m['mae']} | {m['rmse']} | {m['crps']} | "
                         f"{m['spearman']} | {m['cov50']} | {m['cov90']} | {m['brier_ge25']} |")
        lines.append("")
    lines += ["## Notes", "",
              "- ECR-implied = isotonic (monotone, decreasing) fit of actual pts on ECR positional",
              "  rank, per position, fit on **prior seasons only** (walk-forward by target season).",
              "- No FFA history exists; the 'old_plan' baseline uses ECR-implied as the FFA stand-in.",
              "- P(plays)=1.0 in this harness (availability model is Phase 8); coverage/CRPS therefore",
              "  slightly optimistic for injury-risk players.",
              "- Contest win-rate backtest: scaffolded; full run in Phase 10 with the stacked model.",
              "- Feature ablations (ablations.csv) populate in Phase 7."]
    (OUT / "report.md").write_text("\n".join(lines))


# ------------------------------------------------- contest win-rate (§10) ----
# Opponents draft off ECR rank (the market); "me" drafts off the model's mean.
# Rosters scored with ACTUAL best-ball points. For the ecr_implied baseline my
# values ~= the market's, so this lands near the 12.5% null; edge shows once the
# stacked model diverges from ECR (Phase 10).
def _bestball_actual(team_idxs, board):
    sc = np.array([[board[i]["y"] for i in team_idxs]], dtype=float)
    pos = [board[i]["position"] for i in team_idxs]
    return float(simmod.best_ball(sc, pos)[0])


def _draft_once(board, rng, my_seat=3):
    N_T, N_R = 8, 11
    order = []
    for rnd in range(N_R):
        order.extend(range(N_T) if rnd % 2 == 0 else range(N_T - 1, -1, -1))
    counts = [{p: 0 for p in POS} for _ in range(N_T)]
    recent = [[] for _ in range(N_T)]
    taken, rosters = set(), [[] for _ in range(N_T)]
    for team in order:
        avail = [b for b in board if b["idx"] not in taken]
        if not avail:
            continue
        if team == my_seat:  # greedy by model mean, respect QB cap
            pick = None
            for b in sorted(avail, key=lambda b: -b["mean"]):
                if b["position"] == "QB" and counts[team]["QB"] >= opp.HARD_CAP["QB"]:
                    continue
                pick = b; break
            pick = pick or avail[0]
        else:  # opponents: §13 softmax on ECR-derived db_rank
            aidx = [b["idx"] for b in avail]
            sc = opp.pick_scores(board, aidx, counts[team], recent[team], opp.DEFAULT_WEIGHTS)
            finite = np.isfinite(sc)
            cand = [aidx[k] for k in range(len(aidx)) if finite[k]]
            sc = sc[finite]
            z = sc / 0.8; z -= z.max()
            pr = np.exp(z); pr /= pr.sum()
            pick = board[cand[rng.choice(len(cand), p=pr)]]
        taken.add(pick["idx"]); rosters[team].append(pick["idx"])
        counts[team][pick["position"]] += 1; recent[team].append(pick["position"])
    return rosters, my_seat


def contest_win_rate(sample_weeks, n_drafts=150, seed=1):
    games = ds.load_games()
    actuals = load_actuals(TRAIN_SEASONS + (2019, 2020))
    act_idx = actuals.set_index(["player_id", "season", "week"])["pts"]
    wp = ecr_to_gsis(ecr_weekly(games))
    wp = wp[wp["gsis"].notna()].copy()
    wp["y"] = [float(act_idx.get((g, s, w), 0.0)) for g, s, w in zip(wp["gsis"], wp["season"], wp["week"])]
    rng = np.random.default_rng(seed)
    per = []
    for (S, w) in sample_weeks:
        iso = isotonic_by_pos(wp[wp["season"] < S])
        if not iso:
            continue
        wk = wp[(wp["season"] == S) & (wp["week"] == w)]
        uni = pd.concat([wk[wk["pos"] == p].nsmallest(TOPN[p], "ecr") for p in POS]).reset_index(drop=True)
        board = []
        for i, (_, r) in enumerate(uni.iterrows()):
            mu = float(iso[r["pos"]].predict([r["pos_rank"]])[0]) if r["pos"] in iso else 0.0
            board.append({"idx": i, "position": r["pos"], "mean": max(0.0, mu), "y": float(r["y"]), "db_rank": None})
        for rk, i in enumerate(sorted(range(len(board)), key=lambda i: -board[i]["mean"]), 1):
            board[i]["db_rank"] = rk
        wins = 0
        for _ in range(n_drafts):
            rosters, my_team = _draft_once(board, rng, my_seat=3)
            tot = [_bestball_actual(r, board) for r in rosters]
            wins += tot[my_team] >= max(tot)
        per.append({"season": S, "week": w, "win_pct": round(100 * wins / n_drafts, 2)})
        print(f"  contest {S} wk{w}: my win% = {per[-1]['win_pct']} (n={n_drafts})")
    mean_wp = round(float(np.mean([p["win_pct"] for p in per])), 2) if per else None
    return {"model": "ecr_implied baseline", "per_week": per, "mean_win_pct": mean_wp,
            "n_drafts": n_drafts, "null": 12.5}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--fast", action="store_true")
    ap.add_argument("--contest", action="store_true", help="append contest win-rate to the report")
    args = ap.parse_args(argv)

    if args.contest:
        sample = [(S, w) for S in TRAIN_SEASONS for w in (5, 11)]
        print(f"=== contest win-rate backtest: weeks {sample} ===")
        cw = contest_win_rate(sample)
        rj = OUT / "report.json"
        summary = json.loads(rj.read_text()) if rj.exists() else {}
        summary["contest_win_rate"] = cw
        rj.write_text(json.dumps(summary, indent=1))
        rm = OUT / "report.md"
        extra = ["", "## Contest win-rate (ecr_implied baseline)", "",
                 f"Opponents draft off ECR rank; I draft off the model; rosters scored with ACTUAL",
                 f"best-ball points. Sampled weeks {sample}, {cw['n_drafts']} drafts each.", "",
                 f"**Realized win rate: {cw['mean_win_pct']}% vs the 12.5% null.** "
                 f"(ecr_implied mirrors the market, so ~12.5% is expected; edge appears in Phase 10 "
                 f"once the stacked model diverges from ECR.)", ""]
        with open(rm, "a") as fh:
            fh.write("\n".join(extra))
        print(f"\ncontest mean win% = {cw['mean_win_pct']} (null 12.5). appended to {rm}")
        return 0
    weeks = FAST_WEEKS if args.fast else ALL_WEEKS
    print(f"=== walk-forward backtest: seasons {TRAIN_SEASONS}, weeks {list(weeks)} ===")
    df = run_backtest(weeks)
    if df.empty:
        print("NO ROWS — check ECR->gsis join / data.")
        return 1
    summary = summarize(df)
    write_report(summary, weeks, df)
    print(f"\n{'baseline':14s} {'n':>6} {'MAE':>6} {'RMSE':>6} {'CRPS':>6} {'cov90':>6}")
    for b in sorted(summary, key=lambda b: summary[b]["overall"]["crps"]):
        o = summary[b]["overall"]
        print(f"{b:14s} {o['n']:>6} {o['mae']:>6} {o['rmse']:>6} {o['crps']:>6} {o['cov90']:>6}")
    best = min(summary, key=lambda b: summary[b]["overall"]["crps"])
    print(f"\nbest on CRPS: {best}. report -> {OUT/'report.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
