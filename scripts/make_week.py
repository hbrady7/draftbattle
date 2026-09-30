#!/usr/bin/env python3
"""BRIEF §11/§18 — weekly command.

  python scripts/make_week.py --week 4            # build board/sim/opponents, log, scoring check
  python scripts/make_week.py --week 4 --refresh  # + re-download sources first
  python scripts/make_week.py --week 3 --score    # score a PLAYED week vs actuals -> scorecard.json

Build: rebuilds public/data/{board,sim,opponents,meta}.json, copies the frozen
analytical outputs (backtest.json, params.json) into public/data for the Model tab,
logs per-player projections to logs/week{N}/projections.csv, and runs the §11
scoring check (does FFA look like 4- or 6-pt passing TDs?).

NOTE (D5.5): the board build is Week-4-fixed for now; --week is recorded/echoed.
The live board mean is the Phase-2 interim blend — the validated full stacked model
(model/params.json) is applied to *completed* weeks via the backtest; projecting the
*upcoming* week with structural+GBM needs a live-week feature builder (the ECR
archive + features only cover played weeks) — deferred, see DECISIONS.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
PUB = ROOT / "public" / "data"
LOGS = ROOT / "logs"
SCORING = json.loads((ROOT / "model" / "scoring.json").read_text())
sys.path.insert(0, str(ROOT / "scripts"))


def build(week, refresh):
    import build_board, sim as simmod, opponents as opp, data_sources as ds
    if refresh:
        print("… refreshing sources"); ds.main(["--summary", "--refresh"])
    print(f"=== make_week {week}: building board / sim / opponents ===")
    build_board.main([])                      # board.json + meta.json (unit test + sanity)
    simmod.build_sim_json()                   # sim.json (empirical corr + DNP)
    opp.write_profiles()                      # opponents.json (synthetic fallback)
    # copy frozen analytical outputs into the served dir (Model tab reads these)
    for src, dst in [(ROOT / "backtest" / "report.json", PUB / "backtest.json"),
                     (ROOT / "model" / "params.json", PUB / "params.json")]:
        if src.exists():
            shutil.copyfile(src, dst)
    log_projections(week)
    scoring_check()
    print(f"\nWeek {week} built → public/data/*.json. Open localhost:5175 (npm run dev).")


def log_projections(week):
    board = json.loads((PUB / "board.json").read_text())
    out = LOGS / f"week{week}"
    out.mkdir(parents=True, exist_ok=True)
    rows = []
    for p in board:
        s = p.get("sources", {})
        rows.append({"id": p["id"], "name": p["name"], "pos": p["position"], "team": p.get("team"),
                     "mean": p["mean"], "sd": p["sd"], "p_play": p["p_play"],
                     "p05": p["p05"], "p50": p["p50"], "p95": p["p95"],
                     "ffa": s.get("ffa"), "ecr_implied": s.get("ecr_implied"),
                     "db_rank": p["db_rank"], "db_proj": p["db_proj"]})
    pd.DataFrame(rows).to_csv(out / "projections.csv", index=False)
    (out / "built_at.txt").write_text(datetime.now(timezone.utc).isoformat())
    print(f"  logged {len(rows)} projections → {out/'projections.csv'}")


def scoring_check():
    """§11: do FFA's QB points look like 4- or 6-pt passing TDs? Compare FFA to each
    top-24 QB's recent stat line scored both ways. Flag if FFA matches 6 (mismatch)."""
    ffa = pd.read_csv(ROOT / "input_data" / "week4" / "ffa.csv")
    import ids as idmod, build_board as bb, data_sources as ds
    qbs = ffa[ffa["position"].astype(str).str.upper() == "QB"].nlargest(24, "points")
    stats = pd.concat([d for d in (ds.load_stats(2025), ds.load_stats(2026)) if d is not None], ignore_index=True)
    stats["nk"] = stats["player_display_name"].map(idmod.name_key)
    hit4 = hit6 = n = 0
    for _, q in qbs.iterrows():
        nk = idmod.name_key(q["player"])
        g = stats[stats["nk"] == nk].tail(8)
        if g.empty:
            continue
        def m(c): return pd.to_numeric(g.get(c, 0), errors="coerce").fillna(0).mean()
        base = (0.05 * m("passing_yards") - 1 * m("passing_interceptions") + 0.1 * m("rushing_yards")
                + 6 * m("rushing_tds") + 0.1 * m("receiving_yards") + 6 * m("receiving_tds") + 1 * m("receptions"))
        s4 = base + 4 * m("passing_tds")
        s6 = base + 6 * m("passing_tds")
        n += 1
        hit4 += abs(q["points"] - s4) <= abs(q["points"] - s6)
        hit6 += abs(q["points"] - s6) < abs(q["points"] - s4)
    verdict = "4-pt (matches scoring.json)" if hit4 >= hit6 else "6-pt — MISMATCH vs scoring.json!"
    print(f"\n=== §11 scoring check: top-24 QBs — FFA matches {verdict} ({hit4}/{n} closer to 4-pt) ===")
    meta = json.loads((PUB / "meta.json").read_text())
    meta["scoring_check"] = {"ffa_matches": "4pt" if hit4 >= hit6 else "6pt", "n": n, "hit4": int(hit4), "hit6": int(hit6),
                             "ok": bool(hit4 >= hit6)}
    (PUB / "meta.json").write_text(json.dumps(meta, indent=1))


def score(week, season=2026):
    """Score a PLAYED week: our board-style projection (ECR-implied) vs actuals,
    per position + overall, into logs/scorecard.json + public/data/scorecard.json."""
    import backtest as bt
    games = bt.ds.load_games()
    wp = bt.ecr_to_gsis(bt.ecr_weekly(games))
    wp = wp[(wp["season"] == season) & (wp["week"] == week) & wp["gsis"].notna()]
    if wp.empty:
        print(f"no ECR universe for {season} W{week} (archive may lag) — nothing to score."); return
    # actuals for the FULL history the isotonic trains on (not just 2 seasons) + target week
    act = bt.load_actuals(tuple(range(2020, season + 1))).set_index(["player_id", "season", "week"])["pts"]
    iso = bt.isotonic_by_pos(bt.ecr_to_gsis(bt.ecr_weekly(games)).assign(
        y=lambda d: [act.get((g, s, w), 0.0) for g, s, w in zip(d["gsis"], d["season"], d["week"])]
    ).query("season < @season"))
    import player_sd, distribution as dist
    per = {p: {"in": 0, "n": 0, "ae": [], "crps": []} for p in bt.POS}
    my_results = []
    for _, r in wp.iterrows():
        pos, pid = r["pos"], r["gsis"]
        if pos not in iso:
            continue
        mu = float(iso[pos].predict([r["pos_rank"]])[0])
        y = float(act.get((pid, season, week), 0.0))
        sd = player_sd.player_sd(pos, mu, [])["sd"]
        d = dist.player_distribution(pos, mu, sd, 1.0, None)
        p05, p95 = d["p05"], d["p95"]
        inci = p05 <= y <= p95
        per[pos]["n"] += 1; per[pos]["in"] += inci; per[pos]["ae"].append(abs(mu - y))
        my_results.append({"name": r.get("player"), "position": pos, "actual": round(y, 1),
                           "p05": p05, "p95": p95, "in_ci": bool(inci)})
    cov = {p: round(per[p]["in"] / per[p]["n"], 3) for p in bt.POS if per[p]["n"]}
    mae = {p: round(float(np.mean(per[p]["ae"])), 2) for p in bt.POS if per[p]["ae"]}
    alln = sum(per[p]["n"] for p in bt.POS); alli = sum(per[p]["in"] for p in bt.POS)
    sc = {"season": season, "week": week, "scored_at": datetime.now(timezone.utc).isoformat(),
          "coverage90": round(alli / alln, 3) if alln else None, "coverage90_by_pos": cov,
          "mae_by_pos": mae, "n": alln, "model": "ecr_implied (shippable market+); full stack validated on held-out (Model tab)",
          "my_results": sorted(my_results, key=lambda x: -x["actual"])[:60]}
    LOGS.mkdir(exist_ok=True)
    (LOGS / "scorecard.json").write_text(json.dumps(sc, indent=1))
    (PUB / "scorecard.json").write_text(json.dumps(sc, indent=1))
    print(f"=== scored {season} W{week}: 90% coverage {sc['coverage90']} (n={alln}); by pos {cov} → scorecard.json ===")


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--week", type=int, default=4)
    ap.add_argument("--refresh", action="store_true")
    ap.add_argument("--score", action="store_true")
    args = ap.parse_args(argv)
    if args.score:
        score(args.week)
    else:
        build(args.week, args.refresh)


if __name__ == "__main__":
    main()
