#!/usr/bin/env python3
"""
player_sd.py: weekly fantasy-point standard deviation for each player.

For every player it uses his last 8 games on his current team, weighted
toward the most recent (weights 1, 2, ..., 8; the latest game counts 8x the
oldest), scales that to this week's projection, and blends it with the
typical SD for his position at that projection. The blend weights come from
a backtest (below). It can also reshape a player's PDF so the curve the
simulator samples from actually has that SD.


INSTALL
-------
Drop this file next to ffb_pipeline.py (or generate_pdfs.py) in scripts/.
No new dependencies. Then make two edits in ffb_pipeline.py (the same
functions exist in generate_pdfs.py):

1) Replace the body of hist_sd():

    def hist_sd(p, mu, pos):
        from player_sd import sd_for_board_player
        return sd_for_board_player(p, mu)["sd"]

2) In make_pdf(), right after the line
       knots = [round(y, 3) for y in knots]
   add:

        if not backup_qb and not injured(p):
            from player_sd import match_mean_sd
            knots = match_mean_sd(mn, mx, knots, mu, sd)

   Without edit 2 the SD only sets each PDF's min/max range, and the final
   curve's SD comes out wherever the KDE/template shape lands (on 2025-26
   data: 0.76x to 1.31x the intended SD, and about +1 point more in the
   simulator). With it, the simulated SD matches to within about 0.03.
   Backup QBs and Q/O/D/IR players keep their special shapes (spike at 0),
   which already carry their did-he-play risk.

   The build log's "sd=" is the drawn curve's SD. It reads about 2-3% under
   the target because the simulator adds thin tails past min/max; the curve
   is drawn slightly narrower so that what the simulator samples has the
   target SD.

Standalone report (reads board.json, writes public/data/player_sd.json):
    python scripts/player_sd.py                    # everyone, sorted by position/projection
    python scripts/player_sd.py --player "Gibbs"   # name filter
    python scripts/player_sd.py --mode raw         # pure last-8 version


HOW THE SD IS BUILT
-------------------
1. Last 8 games: from the player's game log on his current team (2025+2026,
   the same games get_priors.py collects), oldest to newest. Fewer than 8 is
   fine; with 0-1 games there's no spread to measure.

2. Recency-weighted SD: weights are the last n of [1..8] (newest = 8).
   Weighted mean m = sum(w*x)/sum(w). Weighted variance uses the unbiased
   reliability-weights formula:
       V = sum(w*(x-m)^2) / (V1 - V2/V1),   V1 = sum(w), V2 = sum(w^2)
   Effective sample size n_eff = V1^2/V2 (6.35 for a full 8 games), so the
   evidence is worth n_eff - 1 = 5.35 degrees of freedom.

3. Scale to this week's projection: SD grows with scoring level, so the
   player's variance is rescaled from the level he played at (m) to his
   projection (mu):  V_scaled = V * (curve(mu) / curve(m))^2.

4. Position curve (the typical game-to-game SD at a projection):
       SD = a * projection^b
       QB  6.2511 * p^0.0780   (5/10/15/20/25 -> 7.1  7.5  7.7  7.9  8.0)
       RB  2.5353 * p^0.4115   (             -> 4.9  6.5  7.7  8.7  9.5)
       WR  2.0950 * p^0.5078   (             -> 4.7  6.7  8.3  9.6 10.7)
       TE  1.6761 * p^0.5865   (             -> 4.3  6.5  8.2  9.7 11.1)
   QBs are multiplied by exp(0.40 * (rush_share - 0.1453)), where rush_share
   is the share of his fantasy points from rushing: 0.96x for a pocket
   passer, 1.10x at 40% rushing.

5. Blend (variance-weighted, like adding K "typical" games to his sample):
       V_final = (dof*V_scaled + K*curve(mu)^2) / (dof + K)
       K:  RB 48,  QB 512,  WR 512,  TE infinite
   With a full 8 games his own games carry about 10% of the weight for an RB,
   about 1% for a QB or WR, and 0% for a TE. MODE = "raw" skips this step
   and returns sqrt(V_scaled).

The result is game-to-game SD around his expected score. It does not add
uncertainty about whether the projection itself is right, and it doesn't
include did-not-play risk (injury designations handle that in the pipeline).


WHERE THE NUMBERS COME FROM (backtest)
--------------------------------------
Data: nflverse weekly box scores 2019-2026, regular season, QB/RB/WR/TE,
scored with this league's rules (the same as get_priors.py). 26,658
test points: at each game, take the player's last <=8 current-team games,
predict the variance of his next 4-8 games, and score it with QLIKE (the
standard loss for variance forecasts: lower = better).

- The projection level at each point is the mean of his previous 16 games,
  calibrated so it behaves like a real projection
  (E[next games' mean | level] = level).
- Curves fit by minimizing QLIKE. Tested power, linear-variance and
  quadratic-variance shapes; all within 0.0003, so the power form stays.
- K chosen by leave-one-season-out cross-validation.
  Gain over curve-only (x1000, higher is better):
                 K=8     K=16    K=48    K=128   K=512
       QB      -23.9    -8.5    -1.1    -0.1    +0.03
       RB      -14.9    -2.6    +1.6    +1.1    +0.4
       WR      -22.0    -8.2    -1.2    -0.1    +0.02
       TE      -25.1   -10.3    -2.3    -0.6    -0.1
  The raw last-8 SD (K=0) scored far worse than any of these at every
  position, mostly because 8 games can look calm by chance and give a
  near-zero SD.
- Recency schemes (equal, linear 1..8, exponential half-life 2-6 games)
  scored within 0.0001 of each other. Linear 1..8 is used.
- Year-over-year correlation of a player's volatility beyond what his
  projection implies: 0.03-0.13. Most of what looks like a "volatile player"
  in 8 games is luck, which is why K is large.
- QB rushing share predicted next season's volatility (r ~0.29); the
  multiplier's slope was chosen on 2019-22 and improved 2023-26 predictions.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

# ══════════════════════════════════════════════════════════════════════════════
# SETTINGS
# ══════════════════════════════════════════════════════════════════════════════

WINDOW = 8                 # games used
MODE = "blended"           # "blended" (backtested best) or "raw" (pure last-8 SD scaled to projection)

# Typical game-to-game SD at a projection: SD = a * projection^b
CURVE = {
    "QB": (6.2511, 0.0780),
    "RB": (2.5353, 0.4115),
    "WR": (2.0950, 0.5078),
    "TE": (1.6761, 0.5865),
}
# Pseudo-games of "typical player at his projection" blended with his own games
PRIOR_GAMES = {
    "QB": 512.0,
    "RB": 48.0,
    "WR": 512.0,
    "TE": math.inf,
}
QB_RUSH_BETA = 0.40        # QB volatility multiplier: exp(beta * (rush_share - center))
QB_RUSH_CENTER = 0.1453    # average QB rush share in the fit data (multiplier = 1.0 here)

LEVEL_FLOOR = 1.0          # projections below this are treated as 1.0 for the curve
SD_FLOOR = 1.0             # never return an SD below this

ROOT = Path(__file__).resolve().parents[1]
BOARD_PATH = ROOT / "public" / "data" / "board.json"
PRIORS_PATH = ROOT / "public" / "data" / "priors.json"
OUT_PATH = ROOT / "public" / "data" / "player_sd.json"


# ══════════════════════════════════════════════════════════════════════════════
# CORE MATH
# ══════════════════════════════════════════════════════════════════════════════

def _finite(x) -> bool:
    try:
        return x is not None and math.isfinite(float(x))
    except (TypeError, ValueError):
        return False


def recency_weights(n: int, window: int = WINDOW) -> list[float]:
    """Weights for n games ordered oldest -> newest: the last n of [1..window]."""
    n = max(0, min(int(n), window))
    return [float(window - n + 1 + i) for i in range(n)]


def weighted_stats(scores: list[float], window: int = WINDOW) -> dict:
    """
    Recency-weighted mean/variance of the last `window` scores (oldest -> newest).
    Returns mean, var (None if < 2 games), sd, n, n_eff, dof.
    """
    xs = [float(s) for s in (scores or []) if _finite(s)][-window:]
    n = len(xs)
    if n == 0:
        return {"mean": None, "var": None, "sd": None, "n": 0, "n_eff": 0.0, "dof": 0.0}
    w = recency_weights(n, window)
    v1 = sum(w)
    v2 = sum(wi * wi for wi in w)
    mean = sum(wi * x for wi, x in zip(w, xs)) / v1
    n_eff = v1 * v1 / v2
    if n < 2:
        return {"mean": mean, "var": None, "sd": None, "n": n, "n_eff": n_eff, "dof": 0.0}
    var = sum(wi * (x - mean) ** 2 for wi, x in zip(w, xs)) / (v1 - v2 / v1)
    var = max(var, 0.0)
    return {"mean": mean, "var": var, "sd": math.sqrt(var), "n": n, "n_eff": n_eff, "dof": n_eff - 1.0}


def qb_rush_multiplier(rush_share: float | None) -> float:
    if not _finite(rush_share):
        return 1.0
    rs = min(1.0, max(0.0, float(rush_share)))
    return math.exp(QB_RUSH_BETA * (rs - QB_RUSH_CENTER))


def curve_sd(pos: str, level: float, rush_share: float | None = None) -> float:
    """Typical game-to-game SD for a position at a scoring level (projection)."""
    a, b = CURVE.get(pos, CURVE["WR"])
    lv = max(float(level) if _finite(level) else LEVEL_FLOOR, LEVEL_FLOOR)
    sd = a * lv ** b
    if pos == "QB":
        sd *= qb_rush_multiplier(rush_share)
    return sd


def player_sd(pos: str, proj: float, scores: list[float], rush_share: float | None = None,
              mode: str | None = None) -> dict:
    """
    Weekly SD for one player.

    pos         "QB" | "RB" | "WR" | "TE"
    proj        this week's projected points (the PDF's target mean)
    scores      his fantasy scores on his CURRENT team, oldest -> newest (any length; last 8 used)
    rush_share  QBs only: share of his fantasy points from rushing (0-1); None = neutral
    mode        "blended" (default from MODE) or "raw"

    Returns a dict; "sd" is the number to use.
    """
    mode = (mode or MODE).lower()
    if mode not in ("blended", "raw"):
        raise ValueError(f"mode must be 'blended' or 'raw', not {mode!r}")
    proj_f = float(proj) if _finite(proj) else 0.0
    rush_share = min(1.0, max(0.0, float(rush_share))) if _finite(rush_share) else None
    st = weighted_stats(scores)
    c_proj = curve_sd(pos, proj_f, rush_share)

    raw_scaled_var = None
    if st["var"] is not None:
        c_hist = curve_sd(pos, st["mean"], rush_share)
        raw_scaled_var = st["var"] * (c_proj / c_hist) ** 2

    k = PRIOR_GAMES.get(pos, PRIOR_GAMES["WR"])
    dof = st["dof"] if raw_scaled_var is not None else 0.0

    if mode == "raw":
        var = raw_scaled_var if raw_scaled_var is not None else c_proj ** 2
        weight = 1.0 if raw_scaled_var is not None else 0.0
    elif math.isinf(k) or dof <= 0:
        var = c_proj ** 2
        weight = 0.0
    else:
        var = (dof * raw_scaled_var + k * c_proj ** 2) / (dof + k)
        weight = dof / (dof + k)

    sd = max(math.sqrt(max(var, 0.0)), SD_FLOOR)
    return {
        "sd": round(sd, 3),
        "curve_sd": round(c_proj, 3),
        "last8_sd": None if st["sd"] is None else round(st["sd"], 3),
        "last8_sd_scaled": None if raw_scaled_var is None else round(math.sqrt(raw_scaled_var), 3),
        "last8_mean": None if st["mean"] is None else round(st["mean"], 2),
        "games": st["n"],
        "player_weight": round(weight, 4),
        "rush_share": None if not _finite(rush_share) else round(float(rush_share), 4),
        "mode": mode,
    }


# ══════════════════════════════════════════════════════════════════════════════
# PIPELINE ADAPTERS (board.json player dicts)
# ══════════════════════════════════════════════════════════════════════════════

_PRIOR_LOGS: dict | None = None


def _load_prior_logs() -> dict:
    """game_logs by player id from priors.json (written by get_priors / build). Cached."""
    global _PRIOR_LOGS
    if _PRIOR_LOGS is None:
        _PRIOR_LOGS = {}
        try:
            data = json.loads(PRIORS_PATH.read_text(encoding="utf-8"))
            for pid, rec in (data.get("byId") or {}).items():
                _PRIOR_LOGS[str(pid)] = rec.get("game_logs") or []
        except (OSError, ValueError):
            pass
    return _PRIOR_LOGS


def reset_cache() -> None:
    """Call if priors.json is rewritten in the same process and you need fresh QB rush shares."""
    global _PRIOR_LOGS
    _PRIOR_LOGS = None


def rush_share_from_logs(game_logs: list[dict]) -> float | None:
    """Share of fantasy points from rushing across his game logs (0.1/rush yd + 6/rush TD)."""
    total = rush = 0.0
    for g in game_logs or []:
        ppr = g.get("ppr")
        if not _finite(ppr):
            continue
        total += float(ppr)
        rush += 0.1 * float(g.get("rush_yds") or 0) + 6.0 * float(g.get("rush_td") or 0)
    if total <= 0:
        return None
    return min(1.0, max(0.0, rush / total))


def rush_share_from_fp(fp: dict | None) -> float | None:
    """Projected rushing share from a FantasyPros stat line (board player['fp'])."""
    if not fp or not _finite(fp.get("ppr")) or float(fp["ppr"]) <= 0:
        return None
    rush = 0.1 * float(fp.get("rush_yds") or 0) + 6.0 * float(fp.get("rush_td") or 0)
    return min(1.0, max(0.0, rush / float(fp["ppr"])))


def current_team_scores(p: dict) -> list[float]:
    """His scores on his current team, oldest -> newest (same games the pipeline's priors use)."""
    fit = p.get("fit2025") or {}
    if fit.get("team") and p.get("team") and fit.get("team") != p.get("team"):
        return []
    return [float(s) for s in (fit.get("scores") or []) if _finite(s)]


def sd_for_board_player(p: dict, mu: float, mode: str | None = None) -> dict:
    """player_sd() for a board.json player at projection mu (the pipeline's target mean)."""
    pos = p.get("position") or ""
    rush_share = None
    if pos == "QB":
        logs = _load_prior_logs().get(str(p.get("id")))
        rush_share = rush_share_from_logs(logs) if logs else None
        if rush_share is None:
            rush_share = rush_share_from_fp(p.get("fp"))
    return player_sd(pos, mu, current_team_scores(p), rush_share, mode)


# ══════════════════════════════════════════════════════════════════════════════
# MAKE THE PDF ACTUALLY HAVE THIS SD
# ══════════════════════════════════════════════════════════════════════════════

def _moments(mn: float, mx: float, ys: list[float]):
    """Exact mean/SD of the piecewise-linear density through the knots (same math as generate_pdfs.summarize)."""
    n = len(ys)
    dx = (mx - mn) / (n - 1)
    mass = moment = m2 = 0.0
    for i in range(n - 1):
        x0 = mn + i * dx
        y0, y1 = ys[i], ys[i + 1]
        dy = y1 - y0
        mass += dx * (y0 + y1) / 2
        moment += dx * (x0 * y0 + (x0 * dy + dx * y0) / 2 + (dx * dy) / 3)
        m2 += dx * (x0 * x0 * y0 + (x0 * x0 * dy + 2 * x0 * dx * y0) / 2
                    + (2 * x0 * dx * dy + dx * dx * y0) / 3 + (dx * dx * dy) / 4)
    if mass <= 1e-12:
        return None, None
    mean = moment / mass
    return mean, math.sqrt(max(0.0, m2 / mass - mean * mean))


# Simulator tail settings (project_results.py / simCore.js): thin tails are added past min and max
SIM_MAX_TAIL_FRAC = 0.05
SIM_TAIL_WIDTH_CAP = 6.0
SIM_TAIL_WIDTH_SPAN_FRAC = 0.15


def _sim_sd(mn: float, mx: float, ys: list[float]):
    """
    SD of what the simulator actually samples: the curve plus its tails, exactly as
    build_inv_cdf_table() constructs them (left tail sqrt-shaped below min, right tail past max).
    """
    ys = [max(0.0, float(y)) for y in ys]
    if all(y <= 1e-12 for y in ys):
        ys = [1.0] * len(ys)
    m, sd = _moments(mn, mx, ys)
    if m is None:
        return None
    peak = max(ys)
    tl = SIM_MAX_TAIL_FRAC * max(0.0, min(1.0, ys[0] / peak)) if peak > 1e-9 else 0.0
    tr = SIM_MAX_TAIL_FRAC * max(0.0, min(1.0, ys[-1] / peak)) if peak > 1e-9 else 0.0
    span = mx - mn
    cap = min(SIM_TAIL_WIDTH_CAP, max(0.0, SIM_TAIL_WIDTH_SPAN_FRAC * span))
    lw = 0.0 if mn <= 0 else min(cap, mn)
    rw = cap
    vis = max(0.0, 1.0 - tl - tr)
    mean = vis * m
    ex2 = vis * (sd * sd + m * m)
    if tl > 0:
        if lw <= 1e-9:
            mean += tl * mn
            ex2 += tl * mn * mn
        else:                       # v = (mn - lw) + lw*sqrt(t), t ~ U(0,1)
            a = mn - lw
            mean += tl * (mn - lw / 3.0)
            ex2 += tl * (a * a + 4.0 / 3.0 * a * lw + lw * lw / 2.0)
    if tr > 0:                      # v = mx + rw*(1 - sqrt(1-t)), t ~ U(0,1)
        mean += tr * (mx + rw / 3.0)
        ex2 += tr * (mx * mx + 2.0 * mx * rw / 3.0 + rw * rw / 6.0)
    return math.sqrt(max(0.0, ex2 - mean * mean))


def _peak_round(ys: list[float]) -> list[float]:
    pk = max(ys) if ys else 0.0
    if pk <= 1e-12:
        return [1.0] * len(ys)
    return [round(max(0.0, y) / pk, 3) for y in ys]


def match_mean_sd(mn: float, mx: float, knots: list[float], target_mean: float, target_sd: float,
                  tol: float = 0.01, sim_tails: bool = True) -> list[float]:
    """
    Reshape knots so the PDF on [mn, mx] has the target mean and SD while keeping
    its shape: each knot becomes  y_i^g * exp(t * u_i),  u = position in [-0.5, 0.5].
      g < 1 flattens (wider), g > 1 sharpens (narrower). Raising heights to a power
            keeps their order, so no new bumps or rising edges appear.
      t     slides mass left/right to hold the mean.

    sim_tails=True (default): the SD is matched on what the simulator samples (curve
    plus the thin tails project_results/simCore add past min/max), so the drawn curve
    comes out ~2-3% narrower than target and the simulated SD lands on target. The mean
    is matched on the curve itself, the same convention as the pipeline's tilt_to_mean.
    sim_tails=False matches the drawn curve's SD instead.

    If the target SD is beyond what [mn, mx] can hold, returns the closest possible.
    Output is peak-normalized to 1 and rounded to 3 decimals, like the pipeline's knots.
    """
    n = len(knots)
    if n < 3 or not (mx > mn) or not _finite(target_mean) or not _finite(target_sd) or target_sd <= 0:
        return list(knots)
    base = [max(0.0, float(y)) for y in knots]
    if all(y <= 1e-12 for y in base):
        base = [1.0] * n
    span = mx - mn
    u = [i / (n - 1) - 0.5 for i in range(n)]
    tm = min(mx - span * 1e-4, max(mn + span * 1e-4, float(target_mean)))
    logb = [math.log(y) if y > 0 else None for y in base]
    nz = [v for v in logb if v is not None]
    log_range = max(nz) - min(nz)   # how uneven the knot heights are (log scale)

    def shaped(t, g):
        # log space over the non-zero knots so nothing overflows or underflows to all-zero
        logs = [g * lb + t * ui if lb is not None else None for lb, ui in zip(logb, u)]
        top = max(v for v in logs if v is not None)
        return [math.exp(v - top) if v is not None else 0.0 for v in logs]

    def fit_mean(g):
        # the slide must be able to outweigh the (powered) height differences between neighbors
        lim = 80.0 + 2.0 * (n - 1) * g * log_range
        lo, hi = -lim, lim
        m_lo = _moments(mn, mx, shaped(lo, g))[0]
        m_hi = _moments(mn, mx, shaped(hi, g))[0]
        if m_lo is None or m_hi is None:
            return 0.0
        if tm <= m_lo:
            return lo
        if tm >= m_hi:
            return hi
        for _ in range(60):
            mid = (lo + hi) / 2
            m = _moments(mn, mx, shaped(mid, g))[0]
            if m is None:
                break
            lo, hi = (mid, hi) if m < tm else (lo, mid)
        return (lo + hi) / 2

    def sd_at(g):
        t = fit_mean(g)
        ys = shaped(t, g)
        return t, (_sim_sd(mn, mx, ys) if sim_tails else _moments(mn, mx, ys)[1])

    # SD falls as g rises; search log(g) in [log 0.01, log 60]
    lo, hi = math.log(0.01), math.log(60.0)
    t_lo, sd_wide = sd_at(math.exp(lo))
    t_hi, sd_narrow = sd_at(math.exp(hi))
    if sd_wide is None or sd_narrow is None:
        return list(knots)
    if target_sd >= sd_wide:
        best = (t_lo, math.exp(lo))
    elif target_sd <= sd_narrow:
        best = (t_hi, math.exp(hi))
    else:
        best = None
        for _ in range(60):
            mid = (lo + hi) / 2
            t, s = sd_at(math.exp(mid))
            if s is None:
                break
            if abs(s - target_sd) < tol / 10:
                best = (t, math.exp(mid))
                break
            lo, hi = (mid, hi) if s > target_sd else (lo, mid)
        if best is None:
            g = math.exp((lo + hi) / 2)
            best = (fit_mean(g), g)
    return _peak_round(shaped(*best))


# ══════════════════════════════════════════════════════════════════════════════
# STANDALONE REPORT
# ══════════════════════════════════════════════════════════════════════════════

def _pipeline_means():
    """Import the pipeline's target_mean / is_backup_qb / injured so projections match exactly."""
    for mod in ("ffb_pipeline", "generate_pdfs"):
        try:
            m = __import__(mod)
            return m.target_mean, m.is_backup_qb, m.injured
        except ImportError:
            continue
    return None, None, None


def main(argv: list[str] | None = None):
    ap = argparse.ArgumentParser(description="Per-player weekly SD from last 8 games, recency-weighted, scaled to projection.")
    ap.add_argument("--mode", choices=["blended", "raw"], default=None, help=f"default: {MODE}")
    ap.add_argument("--player", default=None, help="only show players whose name contains this text")
    ap.add_argument("--no-write", action="store_true", help="print only; don't write player_sd.json")
    args = ap.parse_args(argv)

    if not BOARD_PATH.exists():
        print(f"Error: board not found at {BOARD_PATH}. Run the build first.")
        return 1
    board = json.loads(BOARD_PATH.read_text(encoding="utf-8"))
    players = board.get("players", [])
    target_mean, is_backup_qb, injured = _pipeline_means()
    if target_mean is None:
        print("Note: pipeline module not found next to this file; using projectedPoints as the projection.")
    by_team: dict = {}
    for p in players:
        by_team.setdefault(p.get("team"), []).append(p)

    out = {}
    rows = []
    for p in players:
        if target_mean is not None:
            bq = is_backup_qb(p, by_team)
            mu = target_mean(p, bq)
        else:
            mu = float(p.get("projectedPoints") or 0.0)
        r = sd_for_board_player(p, mu, args.mode)
        r.update({"name": p.get("name"), "team": p.get("team"), "position": p.get("position"), "proj": round(mu, 2)})
        out[str(p.get("id"))] = r
        rows.append(r)

    if not args.no_write:
        OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
        OUT_PATH.write_text(json.dumps({"mode": args.mode or MODE, "window": WINDOW, "byId": out}, indent=2), encoding="utf-8")

    order = {"QB": 0, "RB": 1, "WR": 2, "TE": 3}
    rows.sort(key=lambda r: (order.get(r["position"], 9), -r["proj"]))
    if args.player:
        q = args.player.lower()
        rows = [r for r in rows if q in (r["name"] or "").lower()]
    fmt = lambda v: "   -" if v is None else f"{v:5.1f}"
    print(f"{'player':24} {'pos':3} {'team':4} {'proj':>5} {'SD':>5} {'curve':>5} {'last8':>5} {'l8@pj':>5} {'games':>5} {'own wt':>6}")
    for r in rows:
        print(f"{(r['name'] or '')[:24]:24} {r['position']:3} {str(r['team'] or ''):4} {r['proj']:5.1f} {r['sd']:5.1f} "
              f"{r['curve_sd']:5.1f} {fmt(r['last8_sd'])} {fmt(r['last8_sd_scaled'])} {r['games']:5d} {r['player_weight']:6.1%}")
    if not args.no_write:
        print(f"\nWrote {OUT_PATH} ({len(out)} players, mode={args.mode or MODE})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
