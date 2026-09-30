#!/usr/bin/env python3
"""BRIEF §8 distribution — baseline.

Conditional shape A = KDE of recent games (projDist.fitKnotsFromScores port) or a
right-skewed position template, reshaped by player_sd.match_mean_sd to hit the
conditional (mean, SD) on exactly what the simulator samples.

Full weekly distribution = (1 - p_play) point-mass at 0  +  p_play * conditional.
Quantiles / ci90 come off the same inverse-CDF-with-tails the browser sim uses
(port of src/sim/projDist.js — kept byte-parity so Python and JS agree).
"""
from __future__ import annotations

import math

import player_sd  # sibling module

N_KNOTS = 9
INV_CDF_STEPS = 256
MAX_TAIL_FRAC = 0.05
TAIL_WIDTH_CAP = 6.0
TAIL_WIDTH_SPAN_FRAC = 0.15

# Right-skewed 9-knot base templates (peak-normalized). Skew grows for flex
# positions (more boom/bust); QB is more centered. match_mean_sd sets mean/SD.
TEMPLATES = {
    "QB": [0.10, 0.35, 0.72, 1.00, 0.95, 0.72, 0.45, 0.22, 0.09],
    "RB": [0.30, 0.72, 1.00, 0.92, 0.70, 0.48, 0.30, 0.16, 0.07],
    "WR": [0.42, 0.85, 1.00, 0.88, 0.66, 0.45, 0.27, 0.14, 0.06],
    "TE": [0.50, 0.90, 1.00, 0.84, 0.60, 0.40, 0.24, 0.12, 0.05],
}


# ----------------------------------- projDist.js ports (browser parity) ------
def _summarize(mn, mx, knots):
    n = len(knots)
    dx = (mx - mn) / (n - 1)
    ys = [max(0.0, y) if math.isfinite(y) else 0.0 for y in knots]
    if all(y <= 1e-12 for y in ys):
        ys = [1.0] * n
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
        return None
    mean = moment / mass
    var = max(0.0, m2 / mass - mean * mean)
    return {"min": mn, "max": mx, "ys": ys, "mass": mass, "dx": dx, "n": n,
            "mean": mean, "sd": math.sqrt(var)}


def _vis_invcdf(s, p):
    mn, dx, n, ys, mass = s["min"], s["dx"], s["n"], s["ys"], s["mass"]
    target = min(1.0, max(0.0, p)) * mass
    acc = 0.0
    for i in range(n - 1):
        x0 = mn + i * dx
        y0, y1 = ys[i], ys[i + 1]
        dy = y1 - y0
        area = dx * (y0 + y1) / 2
        if acc + area >= target - 1e-12:
            need = max(0.0, target - acc)
            if abs(dy) < 1e-12:
                sfrac = (need / dx) / y0 if y0 > 1e-12 else 0.0
            else:
                a, b, c = dy / 2, y0, -need / dx
                disc = max(0.0, b * b - 4 * a * c)
                sfrac = (-b + math.sqrt(disc)) / (2 * a)
            return x0 + min(1.0, max(0.0, sfrac)) * dx
        acc += area
    return s["max"]


def _tailspec(mn, mx, knots):
    ys = [max(0.0, y) for y in knots]
    peak = max(ys + [0.0])

    def edge(h):
        return MAX_TAIL_FRAC * max(0.0, min(1.0, h / peak)) if peak > 1e-9 else 0.0

    tailL, tailR = edge(ys[0]), edge(ys[-1])
    span = mx - mn
    cap = min(TAIL_WIDTH_CAP, max(0.0, TAIL_WIDTH_SPAN_FRAC * span))
    leftW = 0.0 if mn <= 0 else min(cap, mn)
    return {"tailL": tailL, "tailR": tailR, "leftW": leftW, "rightW": cap,
            "vis": max(0.0, 1 - tailL - tailR),
            "leftAtom": tailL > 0 and (0.0 if mn <= 0 else min(cap, mn)) <= 1e-9}


def _invcdf_tails(s, spec, u):
    p = min(1 - 1e-12, max(1e-12, u))
    if p < spec["tailL"]:
        if spec["leftAtom"] or spec["leftW"] <= 1e-9:
            return s["min"]
        return (s["min"] - spec["leftW"]) + spec["leftW"] * math.sqrt(p / spec["tailL"])
    rs = 1 - spec["tailR"]
    if spec["tailR"] > 0 and p > rs:
        t = min(1.0, max(0.0, (p - rs) / spec["tailR"]))
        return s["max"] + spec["rightW"] * (1 - math.sqrt(1 - t))
    visP = (p - spec["tailL"]) / spec["vis"] if spec["vis"] > 1e-12 else 0.5
    return _vis_invcdf(s, visP)


def build_inv_cdf_table(mn, mx, knots, steps=INV_CDF_STEPS):
    s = _summarize(mn, mx, knots)
    if s is None:
        return None
    spec = _tailspec(mn, mx, knots)
    return [_invcdf_tails(s, spec, i / steps) for i in range(steps + 1)]


def lerp(table, u):
    n = len(table) - 1
    x = min(1 - 1e-12, max(1e-12, u)) * n
    i = min(n - 1, int(math.floor(x)))
    f = x - i
    return table[i] * (1 - f) + table[i + 1] * f


# ------------------------------------------------- shape A (KDE / template) ---
def _silverman(vals):
    n = len(vals)
    if n < 2:
        return 1.0
    mean = sum(vals) / n
    sd = math.sqrt(sum((v - mean) ** 2 for v in vals) / (n - 1))
    sv = sorted(vals)

    def qtl(q):
        pos = (len(sv) - 1) * q
        b = int(math.floor(pos))
        r = pos - b
        return sv[b] + r * (sv[b + 1] - sv[b]) if b + 1 < len(sv) else sv[b]

    iqr = qtl(0.75) - qtl(0.25)
    spread = min(sd, iqr / 1.349) if iqr > 1e-6 else sd
    safe = spread if spread > 1e-6 else max(sd, 1e-6)
    return 0.9 * safe * n ** (-0.2)


def _kde_knots(scores, mn, mx, n=N_KNOTS):
    h = max(_silverman(scores), 1e-3)
    dx = (mx - mn) / (n - 1)
    norm = 1.0 / (len(scores) * h * math.sqrt(2 * math.pi))
    out = []
    for i in range(n):
        x = mn + i * dx
        d = sum(math.exp(-0.5 * ((x - s) / h) ** 2) for s in scores)
        out.append(d * norm)
    return out


def shape_a(pos, mean, sd, scores=None, use_kde=False):
    """Return (min, max, knots) for the conditional distribution.

    Baseline uses the unimodal position template as the match_mean_sd base: it
    reshapes cleanly across the full SD range, unlike a raw KDE which can go
    bimodal for boom/bust players and then can't be narrowed to a low target SD.
    Per-player KDE shapes return in Phase 9 with smoothing + validation.
    """
    mn = 0.0
    mx = max(mean + 5.0 * sd, mean * 1.7 + 1.0, 8.0)
    base = list(TEMPLATES.get(pos, TEMPLATES["WR"]))
    if use_kde and scores and len(scores) >= 3:
        kde = _kde_knots(scores, mn, mx)
        if any(b > 1e-9 for b in kde):
            base = kde
    knots = player_sd.match_mean_sd(mn, mx, base, mean, sd, sim_tails=True)
    return mn, mx, knots


# ------------------------------------------------------- full distribution ---
def player_distribution(pos, mean, sd, p_play, scores=None):
    """conditional shape A + (1-p_play) mass at 0. Returns board-ready dict."""
    mn, mx, knots = shape_a(pos, mean, sd, scores)
    table = build_inv_cdf_table(mn, mx, knots)
    dnp = 1.0 - p_play

    def q(p):  # mixture inverse-CDF
        if p <= dnp or table is None:
            return 0.0
        return max(0.0, lerp(table, (p - dnp) / p_play))

    return {
        "min": round(mn, 3), "max": round(mx, 3),
        "knots": [round(k, 3) for k in knots],
        "p_play": round(p_play, 3),
        "p05": round(q(0.05), 2), "p25": round(q(0.25), 2), "p50": round(q(0.50), 2),
        "p75": round(q(0.75), 2), "p95": round(q(0.95), 2),
        "ci90": [round(q(0.05), 2), round(q(0.95), 2)],
        "_table": table,  # kept in-process for the sim/check; stripped from board.json
    }


def simulated_sd(mn, mx, knots, n=20000, seed=0, steps=INV_CDF_STEPS):
    """SD of what the simulator draws (conditional curve + tails).

    steps=256 is the production table (§8's 257-node table); it adds ~0.08 of
    linear-interpolation quantization in the convex tails. A finer table isolates
    the distribution's true SD (what match_mean_sd targets).
    """
    import random
    rng = random.Random(seed)
    table = build_inv_cdf_table(mn, mx, knots, steps=steps)
    if table is None:
        return None
    vals = [lerp(table, rng.random()) for _ in range(n)]
    m = sum(vals) / n
    return math.sqrt(sum((v - m) ** 2 for v in vals) / n)
