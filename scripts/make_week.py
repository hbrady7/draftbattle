#!/usr/bin/env python3
"""BRIEF §11/§18 — weekly command.

  python scripts/make_week.py --week 4            # build board/sim/opponents, log, scoring check
  python scripts/make_week.py --week 4 --refresh  # + re-download sources first
  python scripts/make_week.py --week 3 --score    # score a PLAYED week vs actuals -> scorecard.json

Build: rebuilds public/data/{board,sim,opponents,meta}.json, copies the frozen
analytical outputs (backtest.json, params.json) into public/data for the Model tab,
logs per-player projections to logs/week{N}/projections.csv, and runs the §11
scoring check (does FFA look like 4- or 6-pt passing TDs?).

--week N reads input_data/week{N}/ (ffa.csv + draft_battle_week{N}_projections.csv,
optional injuries.csv), builds that week's slate, then project_week applies the
validated full stack to the board mean (sanity-gated, interim fallback).
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
    import os
    os.environ["DB_WEEK"] = str(week)   # read by build_board/ids/project_week at import
    inp = ROOT / "input_data" / f"week{week}"
    need = [inp / "ffa.csv", inp / f"draft_battle_week{week}_projections.csv"]
    missing = [str(p.relative_to(ROOT)) for p in need if not p.exists()]
    if missing:
        sys.exit(f"missing week-{week} inputs: {', '.join(missing)}")
    import project_week, build_board, sim as simmod, opponents as opp, data_sources as ds
    if refresh:
        print("… refreshing sources"); ds.main(["--summary", "--refresh"])
    print(f"=== make_week {week}: building board / sim / opponents ===")
    build_board.main([])                      # board.json + meta.json (unit test + sanity)
    simmod.build_sim_json()                   # sim.json (empirical corr + DNP)
    project_week.main()                       # full validated stack -> board mean (gated)
    opp.write_profiles()                      # opponents.json (synthetic fallback)
    # copy frozen analytical outputs into the served dir (Model tab reads these)
    for src, dst in [(ROOT / "backtest" / "report.json", PUB / "backtest.json"),
                     (ROOT / "model" / "params.json", PUB / "params.json")]:
        if src.exists():
            shutil.copyfile(src, dst)
    log_projections(week)
    shutil.copyfile(PUB / "board.json", LOGS / f"week{week}" / "board.json")  # snapshot for --score
    scoring_check(week)
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


def scoring_check(week):
    """§11: do FFA's QB points look like 4- or 6-pt passing TDs? Compare FFA to each
    top-24 QB's recent stat line scored both ways. Flag if FFA matches 6 (mismatch)."""
    ffa = pd.read_csv(ROOT / "input_data" / f"week{week}" / "ffa.csv")
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


def score(week, season=2026, universe=200):
    """Score a PLAYED week: the board we actually shipped (logs/week{N}/board.json)
    vs actuals, injury-aware. Universe = board players with db_rank <= `universe`.

    Each player is classed played / injury_dnp (final report Out/Doubtful/IR, or
    Questionable and didn't play) / other_dnp (no designation, didn't play).
    - coverage90_shipped: actual inside the shipped mixture interval (incl. DNP mass)
    - coverage90 / mae: PLAYED players only, vs the conditional-on-playing interval
      and mean -- the talent model, not penalised for injuries it can't see
    - availability: expected DNPs (sum 1-p_play) vs actual, and every injury DNP
    """
    import backtest as bt, data_sources as ds, ids as idmod, distribution as dist
    snap = LOGS / f"week{week}" / "board.json"
    if not snap.exists():
        sys.exit(f"no board snapshot at {snap.relative_to(ROOT)} -- can't score W{week}")
    board = [p for p in json.loads(snap.read_text()) if p.get("db_rank", 999) <= universe]
    act = bt.load_actuals((season,))
    act = act[act["week"] == week].groupby("player_id")["pts"].sum()
    if act.empty:
        print(f"no box scores for {season} W{week} yet -- nothing to score."); return
    # played = box-score row or offensive snaps (catches 0-stat games)
    sn = ds.load_snaps(season)
    sn = sn[(sn["week"] == week) & (pd.to_numeric(sn["offense_snaps"], errors="coerce") > 0)]
    snapped = {(idmod.name_key(n), t) for n, t in zip(sn["player"], sn["team"])}
    inj = ds.load_injuries(season)
    inj = inj[inj["week"] == week].dropna(subset=["gsis_id"])
    final = {g: str(r).upper() for g, r in zip(inj["gsis_id"], inj["report_status"]) if isinstance(r, str)}
    ros = ds.load_rosters(season)
    ros = ros[ros["week"] == week].dropna(subset=["gsis_id"])
    rstat = dict(zip(ros["gsis_id"], ros["status"]))

    rows = []
    for p in board:
        pid, pos = str(p["id"]), p["position"]
        played = pid in act.index or (idmod.name_key(p["name"]), p.get("team")) in snapped
        y = float(act.get(pid, 0.0))
        status = final.get(pid) or ("IR" if rstat.get(pid) == "RES" else None)
        if played:
            cls = "played"
        elif status in ("OUT", "DOUBTFUL", "IR", "QUESTIONABLE") or rstat.get(pid) in ("RES", "INA"):
            cls = "injury_dnp"
        else:
            cls = "other_dnp"
        tab = dist.build_inv_cdf_table(p["min"], p["max"], p["knots"])
        c05, c95 = (max(0.0, dist.lerp(tab, .05)), dist.lerp(tab, .95)) if tab else (p["p05"], p["p95"])
        rows.append({"id": pid, "name": p["name"], "position": pos, "team": p.get("team"),
                     "db_rank": p["db_rank"], "mean": p["mean"], "sd": p["sd"], "p_play": p["p_play"],
                     "p05": p["p05"], "p95": p["p95"], "c05": round(c05, 2), "c95": round(c95, 2),
                     "actual": round(y, 2), "status": status, "class": cls,
                     "abs_err": round(abs(y - p["mean"]), 2) if played else None,
                     "err": round(y - p["mean"], 2) if played else None,
                     "in_ci": bool(c05 <= y <= c95) if played else None,
                     "in_ci_shipped": bool(p["p05"] <= y <= p["p95"])})
    df = pd.DataFrame(rows)
    pl = df[df["class"] == "played"]

    def summ(d):
        return {"n": int(len(d)), "coverage90": round(float(d["in_ci"].mean()), 3),
                "mae": round(float(d["abs_err"].mean()), 2),
                "bias": round(float(d["err"].mean()), 2),
                "below": round(float((d["actual"] < d["c05"]).mean()), 3),
                "above": round(float((d["actual"] > d["c95"]).mean()), 3),
                "width90": round(float((d["c95"] - d["c05"]).mean()), 2)}
    by_pos = {pos: summ(pl[pl["position"] == pos]) for pos in bt.POS if (pl["position"] == pos).any()}
    dnp = df[df["class"] != "played"]
    sc = {"season": season, "week": week, "scored_at": datetime.now(timezone.utc).isoformat(),
          "model": json.loads((PUB / "meta.json").read_text()).get("mean_recipe") if week == json.loads((PUB / "meta.json").read_text()).get("week") else "shipped board snapshot",
          "universe": f"board db_rank <= {universe}", "n": int(len(df)),
          "played": summ(pl), "by_pos": by_pos,
          "coverage90": summ(pl)["coverage90"], "coverage90_by_pos": {k: v["coverage90"] for k, v in by_pos.items()},
          "mae_by_pos": {k: v["mae"] for k, v in by_pos.items()},
          "coverage90_shipped": round(float(df["in_ci_shipped"].mean()), 3),
          "availability": {"expected_dnp": round(float((1 - df["p_play"]).sum()), 1),
                           "injury_dnp": int((df["class"] == "injury_dnp").sum()),
                           "other_dnp": int((df["class"] == "other_dnp").sum()),
                           "dnp_players": dnp.sort_values("db_rank")[["name", "position", "team", "db_rank", "p_play", "status", "class"]].to_dict("records")},
          "my_results": df.sort_values("db_rank").to_dict("records")}
    sc = json.loads(json.dumps(sc, default=lambda o: None if o != o else o).replace("NaN", "null"))
    LOGS.mkdir(exist_ok=True)
    (LOGS / "scorecard.json").write_text(json.dumps(sc, indent=1))
    (PUB / "scorecard.json").write_text(json.dumps(sc, indent=1))
    P = sc["played"]
    print(f"=== scored {season} W{week} (top-{universe} board): played n={P['n']} · 90% cov {P['coverage90']} "
          f"(below {P['below']}, above {P['above']}) · MAE {P['mae']} · bias {P['bias']:+} · width {P['width90']}")
    for k, v in by_pos.items():
        print(f"  {k}: n={v['n']:3d} cov {v['coverage90']:.3f}  MAE {v['mae']:5.2f}  bias {v['bias']:+5.2f}  width {v['width90']:5.1f}")
    a = sc["availability"]
    print(f"  availability: expected DNP {a['expected_dnp']} vs actual {a['injury_dnp']} injury + {a['other_dnp']} other")
    print(f"  shipped-interval coverage (all, incl. DNP mass): {sc['coverage90_shipped']}")


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
