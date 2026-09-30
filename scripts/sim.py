#!/usr/bin/env python3
"""BRIEF §12 simulator (Python side) + sim.json builder.

Gaussian copula over players' own inverse-CDF marginals (parity with
src/sim/simCore.js + projDist.js), best-ball 9-starter lineup, win = my total >=
max of 8 (ties = wins). Seeded; seed recorded in meta.

CLI:
    python scripts/sim.py --build          # write public/data/sim.json from board.json
    python scripts/sim.py --parity         # synthetic 8x11 draft; print my win% + timing
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np
from scipy.special import ndtr  # standard normal CDF (Phi)

import distribution as dist

ROOT = Path(__file__).resolve().parent.parent
PUBLIC = ROOT / "public" / "data"
N_TEAMS = 8
N_ROUNDS = 11
DEFAULT_SEED = 12345
N_SIM_PY = 100_000

POS_MASK = {"QB": 1, "RB": 2, "WR": 4, "TE": 8}
FLEX_ALLOWED = POS_MASK["RB"] | POS_MASK["WR"] | POS_MASK["TE"]


# ---------------------------------------------- correlations (buildCorrelations port)
def build_correlations(players, team_to_opp):
    """Port of simCore.buildCorrelations: 4 base constants, same/opp game pairs."""
    BASE_SAME = {"QB-WR": 0.15, "QB-TE": 0.15, "QB-RB": 0.05}
    BASE_OPP = {"QB-QB": 0.20}
    corr = {}

    def add(i, j, rho):
        if i == j or rho == 0:
            return
        key = (min(i, j), max(i, j))
        if abs(rho) >= abs(corr.get(key, 0.0)):
            corr[key] = rho

    by_team = {}
    for p in players:
        by_team.setdefault(p.get("team") or "", []).append(p)

    for plist in by_team.values():
        qbs = sorted([p for p in plist if p["position"] == "QB"],
                     key=lambda p: -(p.get("points") or 0))
        if not qbs:
            continue
        q = qbs[0]
        for r in [p for p in plist if p["position"] in ("WR", "TE")]:
            add(q["idx"], r["idx"], BASE_SAME.get(f"QB-{r['position']}", 0.0))
        for rb in [p for p in plist if p["position"] == "RB"]:
            add(q["idx"], rb["idx"], BASE_SAME["QB-RB"])

    seen = set()
    for team, opp in team_to_opp.items():
        gk = "@".join(sorted([team, opp]))
        if gk in seen:
            continue
        seen.add(gk)
        ti, oi = by_team.get(team, []), by_team.get(opp, [])
        tq = sorted([p for p in ti if p["position"] == "QB"], key=lambda p: -(p.get("points") or 0))
        oq = sorted([p for p in oi if p["position"] == "QB"], key=lambda p: -(p.get("points") or 0))
        ts, os_ = (tq[0]["idx"] if tq else -1), (oq[0]["idx"] if oq else -1)
        for a in ti:
            for b in oi:
                if a["position"] == "QB" and b["position"] == "QB" and a["idx"] == ts and b["idx"] == os_:
                    add(a["idx"], b["idx"], BASE_OPP["QB-QB"])
    return sorted([[i, j, rho] for (i, j), rho in corr.items()])


def _chol_scaled(R):
    """Cholesky with simCore's scale-down loop for near-PSD safety."""
    n = R.shape[0]
    scale = 1.0
    while scale > 0.3:
        A = np.eye(n) + (R - np.diag(np.diag(R))) * scale
        try:
            L = np.linalg.cholesky(A)
            if np.min(np.diag(L)) >= 1e-5:
                return L, scale
        except np.linalg.LinAlgError:
            pass
        scale *= 0.85
    return np.linalg.cholesky(np.eye(n)), scale


# ---------------------------------------------- marginals + sampling
def _tables(players):
    out = []
    for p in players:
        k = p.get("knots")
        if k and len(k) >= 2 and p.get("max", 0) > p.get("min", 0):
            out.append(np.asarray(dist.build_inv_cdf_table(p["min"], p["max"], k), dtype=np.float64))
        else:
            out.append(None)
    return out


def _lerp_vec(table, u):
    n = len(table) - 1
    x = np.clip(u, 1e-12, 1 - 1e-12) * n
    i = np.minimum(n - 1, np.floor(x).astype(np.int64))
    f = x - i
    return table[i] * (1 - f) + table[i + 1] * f


def sample_scores(players, correlations, n_sim, seed):
    N = len(players)
    R = np.eye(N)
    for i, j, rho in correlations:
        r = max(-0.95, min(0.95, rho))
        R[i, j] = R[j, i] = r
    L, scale = _chol_scaled(R)
    rng = np.random.default_rng(seed)
    tables = _tables(players)
    mu = np.array([p.get("points") or 0.0 for p in players])
    sd = np.array([max(0.5, p.get("sd_pts") or 4.0) for p in players])
    scores = np.empty((n_sim, N), dtype=np.float32)
    Z = rng.standard_normal((n_sim, N))
    Y = Z @ L.T
    U = ndtr(Y)
    for i in range(N):
        if tables[i] is not None:
            scores[:, i] = _lerp_vec(tables[i], U[:, i])
        else:
            scores[:, i] = mu[i] + sd[i] * Y[:, i]
    np.clip(scores, 0, None, out=scores)
    return scores, scale


# ---------------------------------------------- best-ball lineup
def best_ball_ref(team_scores, positions):
    """Exact greedy port of simCore.bestBallTeamScores (reference; loops per sim)."""
    n_sim, k = team_scores.shape
    bits = [POS_MASK.get(p, 0) for p in positions]
    out = np.zeros(n_sim)
    for s in range(n_sim):
        order = sorted(range(k), key=lambda z: -team_scores[s, z])
        tQB = tRB = tWR = tTE = tSF = tFLEX = 0
        total = 0.0
        for z in order:
            b = bits[z]
            sc = team_scores[s, z]
            if b == 1 and tQB < 1:
                tQB += 1; total += sc
            elif b == 2 and tRB < 2:
                tRB += 1; total += sc
            elif b == 4 and tWR < 3:
                tWR += 1; total += sc
            elif b == 8 and tTE < 1:
                tTE += 1; total += sc
            elif tFLEX < 1 and (b & FLEX_ALLOWED):
                tFLEX += 1; total += sc
            elif tSF < 1:
                tSF += 1; total += sc
        out[s] = total
    return out


def best_ball(team_scores, positions):
    """Vectorized best-ball (validated == best_ball_ref). Optimal for nested slots:
    mandatory QB/2RB/3WR/TE, then FLEX(RB/WR/TE)+SF(any) = the top-2 leftovers with
    FLEX restricted to non-QB."""
    n_sim, k = team_scores.shape
    pos = np.array(positions)

    def desc(mask, need):
        cols = team_scores[:, mask] if mask.any() else np.zeros((n_sim, 0))
        cols = -np.sort(-cols, axis=1)
        if cols.shape[1] < need:  # pad missing with zeros (empty slot = 0 pts)
            cols = np.hstack([cols, np.zeros((n_sim, need - cols.shape[1]))])
        return cols

    qb = desc(pos == "QB", 1)
    rb = desc(pos == "RB", 2)
    wr = desc(pos == "WR", 3)
    te = desc(pos == "TE", 1)
    mandatory = qb[:, 0] + rb[:, :2].sum(1) + wr[:, :3].sum(1) + te[:, 0]

    # leftovers: flex-eligible (RB[2:],WR[3:],TE[1:]) and SF-only (QB[1:])
    fe = [rb[:, 2:], wr[:, 3:], te[:, 1:]]
    fe = np.hstack(fe) if any(c.shape[1] for c in fe) else np.zeros((n_sim, 1))
    sq = qb[:, 1:] if qb.shape[1] > 1 else np.zeros((n_sim, 0))
    full = np.hstack([fe, sq])
    elig = np.concatenate([np.ones(fe.shape[1], bool), np.zeros(sq.shape[1], bool)])
    if full.shape[1] == 0:
        return mandatory

    arg1 = np.argmax(full, axis=1)
    m1 = full[np.arange(n_sim), arg1]
    full2 = full.copy()
    full2[np.arange(n_sim), arg1] = -np.inf
    m2 = full2.max(axis=1)
    fe1 = np.where(elig, full, -np.inf).max(axis=1)
    m1_elig = elig[arg1]
    extra = m1 + np.where(m1_elig, m2, fe1)
    extra = np.maximum(extra, 0.0)
    return mandatory + extra


# ---------------------------------------------- run
def run_sim(players, correlations, rosters, my_team, n_sim=N_SIM_PY, seed=DEFAULT_SEED):
    # subset to rostered players for speed; remap indices, subset correlations
    used = sorted({idx for r in rosters for idx in r})
    remap = {g: i for i, g in enumerate(used)}
    sub = [players[g] for g in used]
    for i, p in enumerate(sub):
        p = dict(p); p["idx"] = i; sub[i] = p
    sub_corr = [[remap[i], remap[j], rho] for i, j, rho in correlations
                if i in remap and j in remap]
    scores, scale = sample_scores(sub, sub_corr, n_sim, seed)
    team_tot = np.zeros((len(rosters), n_sim))
    for t, r in enumerate(rosters):
        idxs = [remap[g] for g in r]
        team_tot[t] = best_ball(scores[:, idxs], [players[g]["position"] for g in r])
    mx = team_tot.max(axis=0)
    win = (team_tot[my_team] >= mx).mean() * 100
    return {"win_pct": win, "team_means": team_tot.mean(axis=1).tolist(), "shrink": scale}


# ---------------------------------------------- sim.json + synthetic draft
def board_to_sim_players(board):
    out = []
    for i, p in enumerate(board):
        out.append({"idx": i, "id": p["id"], "name": p["name"], "position": p["position"],
                    "team": p.get("team"), "db_rank": p.get("db_rank"),  # opponent model needs this
                    "points": p.get("mean"), "sd_pts": p.get("sd"),
                    "min": p.get("min"), "max": p.get("max"), "knots": p.get("knots")})
    return out


def team_to_opp_from_board(board):
    t2o = {}
    for p in board:
        if p.get("team") and p.get("opp"):
            t2o[p["team"]] = p["opp"]
    return t2o


def build_sim_json(seed=DEFAULT_SEED):
    board = json.loads((PUBLIC / "board.json").read_text())
    players = board_to_sim_players(board)
    t2o = team_to_opp_from_board(board)
    correlations = build_correlations(players, t2o)
    sim = {"players": players, "correlations": correlations, "team_to_opp": t2o,
           "meta": {"seed": seed, "n_sim_python": N_SIM_PY, "n_teams": N_TEAMS,
                    "n_rounds": N_ROUNDS, "n_players": len(players),
                    "n_correlations": len(correlations)}}
    (PUBLIC / "sim.json").write_text(json.dumps(sim))
    return sim


def synthetic_draft(sim, seat=4):
    """Snake-draft the top ~120 by points into 8x11 using a simple need-aware pick."""
    players = sim["players"]
    pool = sorted([p for p in players if p.get("points")], key=lambda p: -(p["points"] or 0))
    need = {t: {"QB": 0, "RB": 0, "WR": 0, "TE": 0} for t in range(N_TEAMS)}
    req = {"QB": 2, "RB": 3, "WR": 4, "TE": 1}  # loose targets to fill a legal best-ball roster
    rosters = [[] for _ in range(N_TEAMS)]
    order = []
    for rnd in range(N_ROUNDS):
        seats = range(N_TEAMS) if rnd % 2 == 0 else reversed(range(N_TEAMS))
        order.extend(seats)
    taken = set()
    for pick, team in enumerate(order):
        cand = None
        for p in pool:
            if p["idx"] in taken:
                continue
            pos = p["position"]
            # prefer a position the team still needs; else best available
            if need[team].get(pos, 0) < req.get(pos, 0):
                cand = p; break
        if cand is None:
            for p in pool:
                if p["idx"] not in taken:
                    cand = p; break
        taken.add(cand["idx"])
        need[team][cand["position"]] = need[team].get(cand["position"], 0) + 1
        rosters[team].append(cand["idx"])
    return rosters, seat - 1


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--build", action="store_true")
    ap.add_argument("--parity", action="store_true")
    ap.add_argument("--nsim", type=int, default=N_SIM_PY)
    ap.add_argument("--seed", type=int, default=DEFAULT_SEED)
    args = ap.parse_args(argv)

    sim = build_sim_json(args.seed)
    print(f"sim.json: {sim['meta']['n_players']} players, {sim['meta']['n_correlations']} correlations, seed={args.seed}")

    if args.parity or not args.build:
        # validate vectorized best-ball == reference greedy on a small sim
        rosters, my_team = synthetic_draft(sim, seat=4)
        used = sorted({i for r in rosters for i in r})
        remap = {g: k for k, g in enumerate(used)}
        sub = [dict(sim["players"][g], idx=remap[g]) for g in used]
        sc, _ = sample_scores(sub, [[remap[i], remap[j], r] for i, j, r in sim["correlations"]
                                    if i in remap and j in remap], 2000, args.seed)
        idxs0 = [remap[g] for g in rosters[0]]
        pos0 = [sim["players"][g]["position"] for g in rosters[0]]
        ref = best_ball_ref(sc[:, idxs0], pos0)
        vec = best_ball(sc[:, idxs0], pos0)
        agree = np.max(np.abs(ref - vec))
        # tolerance is float32 summation-order rounding (~1e-4 at ~150-pt totals);
        # a real lineup-logic error would differ by whole points.
        print(f"best-ball vectorized vs greedy: max|diff|={agree:.6f} over 2000 sims "
              f"({'MATCH' if agree < 1e-2 else 'MISMATCH'})")

        t0 = time.time()
        res = run_sim(sim["players"], sim["correlations"], rosters, my_team,
                      n_sim=args.nsim, seed=args.seed)
        dt = (time.time() - t0) * 1000
        ranks = sorted(res["team_means"], reverse=True)
        my_mean = res["team_means"][my_team]
        my_rank = ranks.index(my_mean) + 1
        print(f"Python sim: seat {my_team+1}, my win%={res['win_pct']:.2f} "
              f"(baseline 12.5%), my mean={my_mean:.1f}, rank {my_rank}/8, "
              f"shrink={res['shrink']:.3f}, n_sim={args.nsim}, {dt:.0f}ms")
        # write the synthetic draft for the JS parity driver
        (ROOT / "build").mkdir(exist_ok=True)
        (ROOT / "build" / "_parity_draft.json").write_text(
            json.dumps({"rosters": rosters, "my_team": my_team, "seed": args.seed,
                        "python_win_pct": res["win_pct"]}))


if __name__ == "__main__":
    main()
