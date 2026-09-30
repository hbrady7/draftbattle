#!/usr/bin/env python3
"""BRIEF §6f direct gradient-boosted model (Phase 7).

sklearn HistGradientBoostingRegressor (histogram GBM, same family as LightGBM;
LightGBM's libomp is unavailable on this box — no brew). Predicts league points
directly from the §6f feature set, trained walk-forward. Handles NaN natively.
"""
from __future__ import annotations

import numpy as np
from sklearn.ensemble import HistGradientBoostingRegressor

from features import GROUPS

MARKET = ["ecr", "ecr_sd", "pos_rank"]
# full feature set = market + every §6b-6d group (base trailing included)
GBM_FEATS = list(dict.fromkeys(MARKET + [c for cols in GROUPS.values() for c in cols]))


def _fit(X, y, seed=0):
    m = HistGradientBoostingRegressor(
        loss="squared_error", max_iter=300, learning_rate=0.05,
        max_leaf_nodes=31, min_samples_leaf=40, l2_regularization=1.0,
        early_stopping=False, random_state=seed)
    m.fit(X, y)
    return m


def train_predict(train_df, eval_df, feats=None, seed=0):
    """Fit on train_df[feats]->y, predict eval_df[feats]. Returns clipped preds."""
    feats = feats or GBM_FEATS
    feats = [f for f in feats if f in train_df.columns]
    Xtr = train_df[feats].astype(float).values
    ytr = train_df["y"].astype(float).values
    ok = np.isfinite(ytr)
    m = _fit(Xtr[ok], ytr[ok], seed)
    pred = m.predict(eval_df[feats].astype(float).values)
    return np.clip(pred, 0.0, None)
