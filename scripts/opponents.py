#!/usr/bin/env python3
"""BRIEF §13 AI opponent model.

Pick probability = softmax over available players of score/temperature, where
score is a weighted sum of standardized features:
  - negative DB rank            (draft-value signal)
  - our mean                    (our projection)
  - positional need             (unfilled required slots; -inf for a dead position, e.g. 3rd QB)
  - position-run bonus          (share of the last 5 picks at that position)
  - QB-early bonus
Default: all 7 AI teams draft off DB rank + positional need, temperature 0.8.

Writes public/data/opponents.json (the 7 editable profiles).
Check (--adp): 500 simulated drafts -> each player's simulated ADP vs DB rank
for the top 50, and the Spearman rank correlation (should be high).
Learning (--fit): logistic fit of weights once results/ has 5+ drafts (no-ops below).
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
PUBLIC = ROOT / "public" / "data"
RESULTS = ROOT / "results"

N_TEAMS = 8
N_ROUNDS = 11
POS = ("QB", "RB", "WR", "TE")
REQUIRED = {"QB": 2, "RB": 2, "WR": 3, "TE": 1}   # superflex: teams target 2 QBs (QB + SF)
HARD_CAP = {"QB": 2}                               # a 3rd QB can never score (1 QB + 1 SF)
# Fixed standardization scales so the softmax is sharp enough at temperature 0.8:
# ~RANK_SCALE ranks of DB gap ≈ 1 score unit → effective reach ≈ temp*RANK_SCALE picks.
RANK_SCALE = 8.0
MEAN_SCALE = 8.0

DEFAULT_WEIGHTS = {"db_rank": 1.0, "our_mean": 0.0, "positional_need": 0.6,
                   "position_run": 0.0, "qb_early": 0.0}


def default_profiles():
    return [{"name": f"AI-{s}", "seat": s,
             "weights": dict(DEFAULT_WEIGHTS), "temperature": 0.8, "notes": ""}
            for s in range(1, N_TEAMS + 1)]


def write_profiles():
    PUBLIC.mkdir(parents=True, exist_ok=True)
    profiles = default_profiles()
    (PUBLIC / "opponents.json").write_text(json.dumps({"profiles": profiles}, indent=1))
    return profiles


def _zscore(x):
    x = np.asarray(x, float)
    s = x.std()
    return (x - x.mean()) / s if s > 1e-9 else np.zeros_like(x)


def pick_scores(board, avail_idx, counts, recent, weights):
    """Vectorized §13 score for every available player (higher = more likely)."""
    db_rank = np.array([board[i]["db_rank"] for i in avail_idx], float)
    mean = np.array([board[i]["mean"] or 0.0 for i in avail_idx], float)
    pos = np.array([board[i]["position"] for i in avail_idx])

    # Fixed-scale standardization (NOT per-pool z-score, which flattens adjacent
    # ranks to ~0.016 SD and makes temp-0.8 softmax near-uniform over the top).
    f_dbrank = -db_rank / RANK_SCALE      # lower rank number = higher priority
    f_mean = mean / MEAN_SCALE
    # positional need: unfilled required + small baseline so filled positions stay draftable
    f_need = np.array([max(0, REQUIRED[p] - counts[p]) + 0.25 for p in pos])
    # position run: share of last 5 picks at that position
    if recent:
        last = recent[-5:]
        share = {p: last.count(p) / len(last) for p in POS}
    else:
        share = {p: 0.0 for p in POS}
    f_run = np.array([share[p] for p in pos])
    # QB early bonus (only meaningful early; standardized binary)
    f_qb = (pos == "QB").astype(float)

    w = weights
    score = (w["db_rank"] * f_dbrank + w["our_mean"] * f_mean
             + w["positional_need"] * f_need + w["position_run"] * f_run
             + w["qb_early"] * f_qb)
    # dead positions (hard cap reached) -> -inf so never picked
    for k, p in enumerate(pos):
        if p in HARD_CAP and counts[p] >= HARD_CAP[p]:
            score[k] = -np.inf
    return score


def simulate_draft(board, profiles, rng):
    """One 8x11 snake draft; returns pick_number -> board index and per-player pick."""
    order = []
    for rnd in range(N_ROUNDS):
        seats = range(N_TEAMS) if rnd % 2 == 0 else range(N_TEAMS - 1, -1, -1)
        order.extend(seats)
    counts = [{p: 0 for p in POS} for _ in range(N_TEAMS)]
    recent = [[] for _ in range(N_TEAMS)]
    taken = np.zeros(len(board), bool)
    pick_of = {}
    for pick_no, team in enumerate(order):
        avail_idx = np.where(~taken)[0]
        prof = profiles[team]
        score = pick_scores(board, avail_idx, counts[team], recent[team], prof["weights"])
        finite = np.isfinite(score)
        avail_idx, score = avail_idx[finite], score[finite]
        if len(avail_idx) == 0:
            break
        z = score / max(1e-6, prof["temperature"])
        z -= z.max()
        pr = np.exp(z); pr /= pr.sum()
        choice = avail_idx[rng.choice(len(avail_idx), p=pr)]
        taken[choice] = True
        p = board[choice]["position"]
        counts[team][p] += 1
        recent[team].append(p)
        pick_of[choice] = pick_no + 1  # 1-based ADP
    return pick_of


def adp_check(n_drafts=500, seed=7):
    board = json.loads((PUBLIC / "board.json").read_text())
    # pool = draftable universe (top by DB rank), keep it to a sane size
    board = sorted(board, key=lambda p: p["db_rank"])[:220]
    profiles = default_profiles()
    rng = np.random.default_rng(seed)
    sums = np.zeros(len(board))
    picks = np.zeros(len(board))
    for _ in range(n_drafts):
        pick_of = simulate_draft(board, profiles, rng)
        for idx, pn in pick_of.items():
            sums[idx] += pn
            picks[idx] += 1
    adp = np.where(picks > 0, sums / np.maximum(picks, 1), np.nan)
    db_rank = np.array([p["db_rank"] for p in board])

    # Spearman = Pearson on ranks, over players drafted in >=10% of sims
    drawn = picks >= 0.1 * n_drafts
    a, r = adp[drawn], db_rank[drawn]
    ra, rr = _rankdata(a), _rankdata(r)
    rho = np.corrcoef(ra, rr)[0, 1]

    print(f"=== §13 ADP check: {n_drafts} drafts, {drawn.sum()} players drawn >=10% ===")
    print(f"  Spearman(ADP, DB rank) = {rho:.3f}  (should be high)")
    print(f"  {'name':22s} {'pos':>3} {'DBrank':>6} {'ADP':>6}")
    top = sorted(range(len(board)), key=lambda i: db_rank[i])[:50]
    for i in top:
        print(f"  {board[i]['name'][:22]:22s} {board[i]['position']:>3} "
              f"{int(db_rank[i]):>6} {adp[i]:>6.1f}")
    return rho


def _rankdata(x):
    order = np.argsort(x)
    ranks = np.empty_like(order, float)
    ranks[order] = np.arange(len(x))
    return ranks


def fit_weights():
    drafts = sorted(RESULTS.glob("*.json")) if RESULTS.exists() else []
    if len(drafts) < 5:
        print(f"opponents fit: {len(drafts)} drafts in results/ (need 5+); no-op.")
        return None
    print(f"opponents fit: {len(drafts)} drafts found — logistic fit wired in Phase 11/13.")
    return None


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--adp", action="store_true")
    ap.add_argument("--fit", action="store_true")
    ap.add_argument("--drafts", type=int, default=500)
    args = ap.parse_args(argv)
    profiles = write_profiles()
    print(f"opponents.json: {len(profiles)} default profiles (db_rank 1.0, need 0.6, temp 0.8)")
    if args.fit:
        fit_weights()
    if args.adp or not args.fit:
        adp_check(n_drafts=args.drafts)


if __name__ == "__main__":
    main()
