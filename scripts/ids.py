#!/usr/bin/env python3
"""Phase 1 ID layer (BRIEF §5 resolution, §4.9 canonical gsis_id).

Match order (§5):
  1. aliases.csv manual override on (name_key, position)
  2. (name_key, position) exact via players.csv + db_playerids.csv crosswalk
  3. name_key-only fallback
  4. DB-only fallback id: db_<name_key>_<pos>

CLI:
    python scripts/ids.py --check-db   # DB top-200 gsis match rate; writes build/unmatched.txt
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path

import pandas as pd

import data_sources as ds  # sibling module (scripts/ is sys.path[0] when run directly)

ROOT = Path(__file__).resolve().parent.parent
BUILD = ROOT / "build"
ALIASES = ROOT / "input_data" / "aliases.csv"

SUFFIXES = {"jr", "sr", "ii", "iii", "iv", "v"}
POS_OK = {"QB", "RB", "WR", "TE"}


# --- name_key: exact replica of ffb_pipeline.py (clean_name -> name_parts) ----
def clean_name(name) -> str:
    return re.sub(r"\s*\(([A-Z]{2,3})\)\s*$", "", str(name or "")).strip()


def name_parts(name) -> list[str]:
    n = clean_name(name).lower()
    n = re.sub(r"[^a-z0-9\s]", "", n)
    return [p for p in n.split() if p and p not in SUFFIXES]


def name_key(name) -> str:
    return "".join(name_parts(name))


# ------------------------------------------------------------- crosswalk ------
def _pick_col(df: pd.DataFrame, candidates) -> str | None:
    for c in candidates:
        if c in df.columns:
            return c
    return None


def build_crosswalk(refresh: bool = False):
    """Returns (lut, lut_name): (name_key,pos)->gsis_id and name_key->gsis_id."""
    players = ds.load_players(refresh=refresh)
    dbids = ds.load_db_playerids(refresh=refresh)

    lut: dict[tuple[str, str], str] = {}
    lut_name: dict[str, str] = {}

    def add(nm, pos, gsis):
        if gsis is None or (isinstance(gsis, float) and pd.isna(gsis)):
            return
        gsis = str(gsis).strip()
        if not gsis or gsis.lower() == "nan":
            return
        k = name_key(nm)
        if not k:
            return
        pos = str(pos).upper()
        if pos in POS_OK:
            lut.setdefault((k, pos), gsis)
        lut_name.setdefault(k, gsis)

    if players is not None:
        ncol = _pick_col(players, ["display_name", "full_name", "player_name", "football_name"])
        gcol = _pick_col(players, ["gsis_id", "gsis_it_id"])
        pcol = _pick_col(players, ["position", "position_group"])
        if ncol and gcol:
            for nm, pos, g in zip(players[ncol], players[pcol] if pcol else [""] * len(players),
                                  players[gcol]):
                add(nm, pos, g)

    if dbids is not None:
        ncol = _pick_col(dbids, ["name", "merge_name", "mergename", "player_name"])
        gcol = _pick_col(dbids, ["gsis_id"])
        pcol = _pick_col(dbids, ["position", "pos"])
        if ncol and gcol:
            for nm, pos, g in zip(dbids[ncol], dbids[pcol] if pcol else [""] * len(dbids),
                                  dbids[gcol]):
                add(nm, pos, g)

    return lut, lut_name


def load_aliases() -> dict[tuple[str, str], str]:
    if not ALIASES.exists():
        return {}
    a = pd.read_csv(ALIASES)
    out = {}
    for _, r in a.iterrows():
        g = r.get("gsis_id")
        if g is None or (isinstance(g, float) and pd.isna(g)):
            continue
        out[(name_key(r.get("raw_name")), str(r.get("position", "")).upper())] = str(g).strip()
    return out


def resolve(name, pos, cw, aliases=None) -> str:
    pos = str(pos).upper()
    k = name_key(name)
    if aliases and (k, pos) in aliases:
        return aliases[(k, pos)]
    lut, lut_name = cw
    if (k, pos) in lut:
        return lut[(k, pos)]
    if k in lut_name:
        return lut_name[k]
    return f"db_{k}_{pos.lower()}"


# --------------------------------------------------------------- DB check -----
def _week_input(fname):
    import os
    w = int(os.environ.get("DB_WEEK", "4"))
    return ROOT / "input_data" / f"week{w}" / fname.format(w=w)


def check_db(refresh: bool = False, topn: int = 200):
    cw = build_crosswalk(refresh=refresh)
    aliases = load_aliases()

    db = pd.read_csv(_week_input("draft_battle_week{w}_projections.csv"))
    db = db.sort_values("Rank").head(topn)

    ffa = pd.read_csv(_week_input("ffa.csv"))
    ffa_keys = {(name_key(p), str(pos).upper()) for p, pos in zip(ffa["player"], ffa["position"])}
    ffa_names = {name_key(p) for p in ffa["player"]}

    matched = ffa_matched = 0
    unmatched = []
    for _, r in db.iterrows():
        gid = resolve(r["Name"], r["Position"], cw, aliases)
        is_gsis = not gid.startswith("db_")
        matched += is_gsis
        k, pos = name_key(r["Name"]), str(r["Position"]).upper()
        fm = (k, pos) in ffa_keys or k in ffa_names
        ffa_matched += bool(fm)
        if not is_gsis:
            unmatched.append((int(r["Rank"]), str(r["Name"]), pos,
                              "no-gsis" + ("" if fm else "/no-ffa")))

    BUILD.mkdir(parents=True, exist_ok=True)
    with open(BUILD / "unmatched.txt", "w") as fh:
        fh.write(f"# DB top-{topn} rows with no gsis match ({len(unmatched)} of {len(db)})\n")
        fh.write("rank\tname\tpos\treason\n")
        for rk, nm, pos, why in sorted(unmatched):
            fh.write(f"{rk}\t{nm}\t{pos}\t{why}\n")

    n = len(db)
    print(f"=== DB top-{topn} ID match ===")
    print(f"  gsis match : {matched}/{n} = {matched/n:.1%}  (target >= 95%)")
    print(f"  FFA-name   : {ffa_matched}/{n} = {ffa_matched/n:.1%}")
    print(f"  unmatched written: {BUILD/'unmatched.txt'} ({len(unmatched)} rows)")
    if matched / n < 0.95:
        print("  WARNING: below 95% gsis-match target.")
    return matched / n


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--check-db", action="store_true")
    ap.add_argument("--refresh", action="store_true")
    ap.add_argument("--topn", type=int, default=200)
    args = ap.parse_args(argv)
    if args.check_db or not any(vars(args).values()):
        check_db(refresh=args.refresh, topn=args.topn)


if __name__ == "__main__":
    main()
