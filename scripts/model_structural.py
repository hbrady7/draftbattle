#!/usr/bin/env python3
"""BRIEF §6b-6e structural mean (Phase 7) — compact bottom-up projection.

Opportunity x efficiency comes from ffopportunity's expected fantasy points
(tr8_xfp, already re-scored with scoring.json in features/backtest), which is
itself built from usage x field-position efficiency (§6d). We blend it with
recent realized production and scale by the game environment (Vegas implied
team total, §6b):

    mean = clip(implied_total / league_avg, 0.6, 1.5) * (0.65*xFP + 0.35*recent_pts)

This is a deliberately compact structural model: the full share x team-volume x
efficiency regression (pace/PROE/red-zone) is a future refinement — logged in
DECISIONS. Vectorized over a feature frame.
"""
from __future__ import annotations

import numpy as np

from features import LEAGUE_IMPLIED


def structural_means(df):
    # mild environment tilt: xFP already embeds usage, so only nudge by the game's
    # implied total rather than scaling proportionally (which over-projects elite QBs).
    imp = df["implied_total"].astype(float).fillna(LEAGUE_IMPLIED)
    vs = np.clip(1.0 + 0.30 * (imp / LEAGUE_IMPLIED - 1.0), 0.82, 1.22)
    xfp = df["tr8_xfp"].astype(float)
    pts = df["tr8_pts"].astype(float)
    opp = xfp.fillna(pts).fillna(0.0)
    rec = pts.fillna(xfp).fillna(0.0)
    return np.clip(vs.values * (0.65 * opp.values + 0.35 * rec.values), 0.0, None)
