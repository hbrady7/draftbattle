#!/usr/bin/env python3
"""Ingest the user's Week-4 AI Draft Prediction workbook into a data-driven
opponent model (BRIEF §13 / §20 "real AI strategies").

From 25 observed Draft Battle rooms (2,200 picks) it builds, per named AI:
  - position-by-round distribution  P(pos | AI, round)
  - player-targeting priors          share = rooms the AI drafted a player / rooms faced
  - archetype + round script (from the AI PROFILES sheet)
plus a global ADP / draft-rate table. Players key on name_key so they join the
board. Writes public/data/ai_opponents.json.

  python scripts/ingest_ai_data.py [path-to-xlsx]
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

import ids as idmod

ROOT = Path(__file__).resolve().parent.parent
PUBLIC = ROOT / "public" / "data"
DEFAULT_XLSX = Path.home() / "Downloads" / "Week4_AI_Draft_Prediction_Model.xlsx"
POS = ("QB", "RB", "WR", "TE")
N_ROUNDS = 11
# Live rooms exported from the Draft Room (input_data/week*/ai_rooms_live.csv, seat→AI
# inferred from position sequences). They reflect the CURRENT bot behaviour, so
# each live room counts LIVE_WEIGHT× a workbook room. Leave-one-room-out on the
# 3 live rooms: round-position accuracy 172/231 (profile scripts) → 200/231.
LIVE_WEIGHT = 100.0
LIVE_GLOB = "input_data/week*/ai_rooms_live.csv"


def _seq_medoid(seqs):
    """The observed full position sequence with the least weighted Hamming
    distance to all observed sequences — always a real (valid) roster build."""
    full = [(s, w) for s, w in seqs if len(s) == N_ROUNDS]
    if not full:
        return None
    ham = lambda a, b: sum(x != y for x, y in zip(a, b))
    return min((s for s, _ in full), key=lambda c: sum(w * ham(c, s) for s, w in full))


def _num(x, d=0.0):
    try:
        v = float(x)
        return v if v == v else d
    except (TypeError, ValueError):
        return d


def build(xlsx: Path):
    raw = pd.read_excel(xlsx, sheet_name="RAW PICK LOG")
    raw = raw.dropna(subset=["TEAM", "PLAYER", "POS", "ROUND"])
    raw["W"] = 1.0
    lives = [pd.read_csv(f) for f in sorted(ROOT.glob(LIVE_GLOB))]
    n_live = 0
    if lives:
        live = pd.concat(lives, ignore_index=True).dropna(subset=["TEAM", "PLAYER", "POS", "ROUND"])
        live["ROOM"] = live["ROOM"].astype(str)
        live["W"] = LIVE_WEIGHT
        n_live = live["ROOM"].nunique()
        raw["ROOM"] = raw["ROOM"].astype(str)
        raw = pd.concat([raw, live[[c for c in live.columns if c in raw.columns or c == "W"]]],
                        ignore_index=True)
    raw["nk"] = raw["PLAYER"].map(idmod.name_key)
    total_rooms = raw["ROOM"].nunique()

    # profiles: archetype / full name / round script, matched to the short TEAM name
    prof = pd.read_excel(xlsx, sheet_name="AI PROFILES")
    prof_by_last = {}
    for _, r in prof.iterrows():
        full = str(r.get("A.I. OPPONENT") or "")
        script = str(r.get("ROUND SCRIPT R1→R11") or "").split()
        prof_by_last[full.replace('"', "").split()[-1] if full.strip() else ""] = {
            "full_name": full, "archetype": str(r.get("ARCHETYPE") or ""),
            "round_script": [s for s in script if s in POS] or None,
            "script_holds": _num(r.get("SCRIPT HOLDS"), None),
            "reliable_through": str(r.get("RELIABLE THROUGH") or ""),
        }

    ais = []
    opp = raw[raw["TEAM"] != "YOU"]
    for name, g in opp.groupby("TEAM"):
        rooms_faced = int(g["ROOM"].nunique())
        room_w = g.groupby("ROOM")["W"].first()
        w_total = float(room_w.sum())
        # position-by-round distribution (room-weighted: live rooms dominate)
        pbr = {}
        for rnd in range(1, N_ROUNDS + 1):
            gr = g[g["ROUND"] == rnd]
            if len(gr) == 0:
                continue
            counts = gr.groupby("POS")["W"].sum() / gr["W"].sum()
            pbr[str(rnd)] = {p: round(float(counts.get(p, 0.0)), 4) for p in POS}
        # player-targeting priors: weighted share of the AI's rooms a player appeared in
        priors = {}
        for (nk, player, pos), gg in g.groupby(["nk", "PLAYER", "POS"]):
            rooms = gg["ROOM"].nunique()
            w_rooms = float(gg.groupby("ROOM")["W"].first().sum())
            priors[nk] = {"name": player, "pos": pos,
                          "share": round(w_rooms / w_total, 4),
                          "avg_round": round(float(gg["ROUND"].mean()), 2),
                          "n": int(rooms)}
        meta = prof_by_last.get(name, {})
        seqs = [(list(gs.sort_values("ROUND")["POS"]), float(gs["W"].iloc[0]))
                for _, gs in g.groupby("ROOM")]
        live_rooms = int((room_w > 1).sum())
        script = (_seq_medoid(seqs) if live_rooms else None) or meta.get("round_script")
        ais.append({"name": name, "full_name": meta.get("full_name", name),
                    "archetype": meta.get("archetype", ""),
                    "round_script": script,
                    "profile_script": meta.get("round_script"),
                    "live_rooms": live_rooms,
                    "script_holds": meta.get("script_holds"),
                    "reliable_through": meta.get("reliable_through", ""),
                    "rooms_faced": rooms_faced, "pos_by_round": pbr,
                    "priors": priors})
    ais.sort(key=lambda a: -a["rooms_faced"])

    # global ADP / draft rate (all teams incl. YOU, for board annotation)
    adp = {}
    for (nk, player, pos), gg in raw.groupby(["nk", "PLAYER", "POS"]):
        rooms = gg["ROOM"].nunique()   # global ADP: unweighted
        avp = pd.to_numeric(gg["PROJ"], errors="coerce").mean()   # can be NaN if PROJ missing
        adp[nk] = {"name": player, "pos": pos,
                   "adp": round(float(gg["PICK"].mean()), 2),
                   "draft_pct": round(rooms / total_rooms, 4),
                   "avg_proj": round(float(avp), 2) if avp == avp else None}

    out = {"ais": ais, "adp": adp,
           "meta": {"rooms": int(total_rooms), "picks": int(len(raw)), "live_rooms": int(n_live),
                    "live_weight": LIVE_WEIGHT,
                    "n_ais": len(ais), "source": xlsx.name,
                    "default_seven": [a["name"] for a in ais if a["rooms_faced"] >= 15][:7]}}
    PUBLIC.mkdir(parents=True, exist_ok=True)
    # allow_nan=False → fail loudly rather than emit bare NaN (invalid for JS JSON.parse)
    (PUBLIC / "ai_opponents.json").write_text(json.dumps(out, allow_nan=False))
    return out


def main(argv=None):
    argv = argv or sys.argv[1:]
    xlsx = Path(argv[0]) if argv else DEFAULT_XLSX
    if not xlsx.exists():
        print(f"STOP: workbook not found: {xlsx}")
        return 1
    out = build(xlsx)
    print(f"ai_opponents.json: {out['meta']['n_ais']} AIs from {out['meta']['rooms']} rooms "
          f"({out['meta']['picks']} picks). default seven: {out['meta']['default_seven']}")
    for a in out["ais"]:
        top = sorted(a["priors"].values(), key=lambda x: -x["share"])[:3]
        tops = ", ".join(f"{t['name']}({t['pos']} {int(t['share']*100)}%)" for t in top)
        print(f"  {a['name']:12} {a['rooms_faced']:>2}rm  {a['archetype'][:22]:22}  R1:"
              f"{max(a['pos_by_round'].get('1', {}), key=a['pos_by_round'].get('1', {'x':0}).get, default='-')}"
              f"  top: {tops}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
