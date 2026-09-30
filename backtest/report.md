# Backtest report (BRIEF §10)

Walk-forward on [2021, 2022, 2023, 2024] (2025 held out for Phase 10). Weeks sampled: [2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17]. Universe: ECR positional top-N (QB32/RB60/WR84/TE32), players who scored 0 kept.

Primary metric: CRPS (lower is better). Coverage targets: 50% and 90%.

## Overall (2021-2024)

| baseline | n | MAE | RMSE | CRPS | cov50 | cov90 | PIT mean |
|---|---|---|---|---|---|---|---|
| ecr_implied | 12895 | 5.835 | 7.464 | **4.036** | 0.455 | 0.847 | 0.483 |
| old_plan | 12895 | 5.847 | 7.464 | **4.038** | 0.457 | 0.846 | 0.481 |
| trailing_xfp | 12895 | 6.133 | 7.86 | **4.275** | 0.438 | 0.835 | 0.477 |
| trailing8 | 12895 | 6.156 | 7.89 | **4.305** | 0.435 | 0.829 | 0.48 |

**Best baseline on CRPS: `ecr_implied`** (4.036).

## QB by baseline

| baseline | n | MAE | RMSE | CRPS | Spearman | cov50 | cov90 | Brier(>=25) |
|---|---|---|---|---|---|---|---|---|
| old_plan | 1983 | 6.863 | 8.607 | 4.849 | 0.463 | 0.457 | 0.838 | 0.1533 |
| ecr_implied | 1983 | 6.925 | 8.678 | 4.894 | 0.473 | 0.455 | 0.845 | 0.1553 |
| trailing8 | 1983 | 7.176 | 9.103 | 5.183 | 0.376 | 0.442 | 0.819 | 0.158 |
| trailing_xfp | 1983 | 7.344 | 9.293 | 5.267 | 0.37 | 0.428 | 0.82 | 0.1633 |

## RB by baseline

| baseline | n | MAE | RMSE | CRPS | Spearman | cov50 | cov90 | Brier(>=25) |
|---|---|---|---|---|---|---|---|---|
| ecr_implied | 3720 | 5.668 | 7.255 | 3.884 | 0.554 | 0.451 | 0.866 | 0.0532 |
| old_plan | 3720 | 5.672 | 7.255 | 3.886 | 0.531 | 0.451 | 0.861 | 0.053 |
| trailing_xfp | 3720 | 5.971 | 7.687 | 4.155 | 0.43 | 0.432 | 0.846 | 0.0546 |
| trailing8 | 3720 | 6.015 | 7.748 | 4.203 | 0.435 | 0.423 | 0.83 | 0.0551 |

## WR by baseline

| baseline | n | MAE | RMSE | CRPS | Spearman | cov50 | cov90 | Brier(>=25) |
|---|---|---|---|---|---|---|---|---|
| ecr_implied | 5208 | 5.86 | 7.456 | 4.026 | 0.482 | 0.459 | 0.834 | 0.0535 |
| old_plan | 5208 | 5.897 | 7.484 | 4.044 | 0.458 | 0.463 | 0.837 | 0.0536 |
| trailing_xfp | 5208 | 6.131 | 7.786 | 4.225 | 0.38 | 0.442 | 0.833 | 0.0551 |
| trailing8 | 5208 | 6.194 | 7.874 | 4.279 | 0.378 | 0.437 | 0.829 | 0.0557 |

## TE by baseline

| baseline | n | MAE | RMSE | CRPS | Spearman | cov50 | cov90 | Brier(>=25) |
|---|---|---|---|---|---|---|---|---|
| ecr_implied | 1984 | 4.992 | 6.499 | 3.489 | 0.425 | 0.456 | 0.847 | 0.0273 |
| old_plan | 1984 | 5.025 | 6.505 | 3.496 | 0.401 | 0.45 | 0.848 | 0.0272 |
| trailing_xfp | 1984 | 5.23 | 6.733 | 3.637 | 0.322 | 0.447 | 0.838 | 0.0269 |
| trailing8 | 1984 | 5.306 | 6.819 | 3.685 | 0.322 | 0.446 | 0.834 | 0.0278 |

## Notes

- ECR-implied = isotonic (monotone, decreasing) fit of actual pts on ECR positional
  rank, per position, fit on **prior seasons only** (walk-forward by target season).
- No FFA history exists; the 'old_plan' baseline uses ECR-implied as the FFA stand-in.
- P(plays)=1.0 in this harness (availability model is Phase 8); coverage/CRPS therefore
  slightly optimistic for injury-risk players.
- Contest win-rate backtest: scaffolded; full run in Phase 10 with the stacked model.
- Feature ablations (ablations.csv) populate in Phase 7.
## Phase 7: full model vs baselines (Thursday-kickoff ECR drop applied)

All models scored apples-to-apples on sample weeks [3, 7, 11, 15] (4 seasons). (Phase-6 baseline numbers above are the full 16-week run.)

| model | n | MAE | RMSE | CRPS | cov90 |
|---|---|---|---|---|---|
| **structural** | 3116 | 5.207 | 7.036 | **3.661** | 0.895 |
| **gbm** | 3116 | 5.288 | 7.088 | **3.672** | 0.889 |
| ecr_implied | 3116 | 5.697 | 7.281 | **3.881** | 0.845 |
| old_plan | 3116 | 5.734 | 7.311 | **3.902** | 0.843 |
| trailing8 | 3116 | 6.054 | 7.788 | **4.195** | 0.822 |
| trailing_xfp | 3116 | 6.094 | 7.83 | **4.206** | 0.83 |

CRPS vs ECR-implied by position (our models must beat ECR to ship, §10):

| position | ecr_implied | structural | gbm | winner |
|---|---|---|---|---|
| QB | 4.845 | 4.501 | 4.387 | gbm |
| RB | 3.752 | 3.673 | 3.594 | gbm |
| WR | 3.856 | 3.572 | 3.691 | structural |
| TE | 3.232 | 3.038 | 3.062 | structural |

**Verdict:** best overall CRPS = `structural` (ECR-implied 3.881).
Where the structural/GBM models don't beat ECR, that's reported honestly (the market is a strong baseline, §10/§19); the stacked model in Phase 10 combines whichever wins per position.

## Phase 7: feature-group ablations (GBM, eval weeks [5, 11])

A group ships iff the 95% bootstrap CI of its CRPS improvement excludes 0.

| feature group | CRPS with | CRPS without | Δ(without−with) | 95% CI | ships |
|---|---|---|---|---|---|
| vegas | 3.816 | 3.787 | -0.029 | [-0.082, +0.019] | · |
| weather | 3.816 | 3.834 | +0.018 | [-0.026, +0.067] | · |
| participation | 3.816 | 3.79 | -0.026 | [-0.078, +0.025] | · |
| efficiency | 3.816 | 3.787 | -0.03 | [-0.11, +0.035] | · |
| opponent | 3.816 | 3.832 | +0.016 | [-0.023, +0.062] | · |
