# SPDX-License-Identifier: MIT
"""Synthetic, seeded input profiles for the toy models.

Nothing here is real data. Shapes are stylised on purpose so a card can state them
in one sentence: a two-hump daily load, a winter-peaked annual load, AR(1) wind on a
logit scale, a clear-sky solar bell with cloud noise, a degree-day-like heat demand
and a seasonal heat-pump COP. Every function is deterministic for a given seed.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

SEED = 42
HOURS_PER_YEAR = 8760


def hourly_index(days: int, start: str = "2025-01-01") -> pd.DatetimeIndex:
    """`days` days of hourly snapshots starting at `start` (a Wednesday by default)."""
    return pd.date_range(start, periods=24 * days, freq="h")


def year_index(every: int = 3, start: str = "2025-01-01") -> pd.DatetimeIndex:
    """A stylised year: 8760 hours sampled every `every` hours (2920 snapshots at 3 h).

    The caller sets `n.snapshot_weightings.loc[:, :] = every` so energy sums stay in MWh/a.
    """
    return pd.date_range(start, periods=HOURS_PER_YEAR // every, freq=f"{every}h")


def _hour_of_day(index: pd.DatetimeIndex) -> np.ndarray:
    return index.hour.to_numpy() + index.minute.to_numpy() / 60


def _day_of_year(index: pd.DatetimeIndex) -> np.ndarray:
    return index.dayofyear.to_numpy()


def daily_shape(index: pd.DatetimeIndex) -> np.ndarray:
    """A 0..1 two-hump day: morning ramp, evening peak, night trough."""
    h = _hour_of_day(index)
    morning = np.exp(-((h - 9) / 3.0) ** 2)
    evening = np.exp(-((h - 19) / 2.5) ** 2)
    shape = 0.35 + 0.35 * morning + 0.65 * evening
    return shape / shape.max()


def daily_load(
    index: pd.DatetimeIndex,
    base_mw: float,
    peak_mw: float,
    *,
    seed: int = SEED,
    noise: float = 0.02,
    weekend_factor: float = 0.9,
) -> pd.Series:
    """Load between `base_mw` (night) and `peak_mw` (evening), weekends scaled down."""
    rng = np.random.default_rng(seed)
    shape = daily_shape(index)
    load = base_mw + (peak_mw - base_mw) * shape
    weekend = np.where(index.dayofweek.to_numpy() >= 5, weekend_factor, 1.0)
    load = load * weekend * (1 + noise * rng.standard_normal(len(index)))
    return pd.Series(load, index=index, name="load")


def annual_load(
    index: pd.DatetimeIndex,
    mean_mw: float,
    *,
    winter_factor: float = 1.2,
    seed: int = SEED,
    noise: float = 0.02,
) -> pd.Series:
    """Daily shape times a seasonal cosine, winter `winter_factor` above summer, mean `mean_mw`."""
    rng = np.random.default_rng(seed)
    season = 1 + (winter_factor - 1) / 2 * np.cos(2 * np.pi * (_day_of_year(index) - 15) / 365.25)
    shape = (0.6 + 0.4 * daily_shape(index)) * season
    weekend = np.where(index.dayofweek.to_numpy() >= 5, 0.92, 1.0)
    load = shape * weekend * (1 + noise * rng.standard_normal(len(index)))
    load = load / load.mean() * mean_mw
    return pd.Series(load, index=index, name="load")


def wind(
    index: pd.DatetimeIndex, *, mean_cf: float = 0.35, seed: int = SEED, persistence: float = 0.96
) -> pd.Series:
    """Wind capacity factor: an AR(1) process on the logit scale, winter-heavier, clipped 0..1."""
    rng = np.random.default_rng(seed)
    n = len(index)
    x = np.empty(n)
    x[0] = 0.0
    shocks = rng.standard_normal(n) * np.sqrt(1 - persistence**2) * 1.6
    for t in range(1, n):
        x[t] = persistence * x[t - 1] + shocks[t]
    season = 0.5 * np.cos(2 * np.pi * (_day_of_year(index) - 15) / 365.25)
    logit_mean = np.log(mean_cf / (1 - mean_cf))
    cf = 1 / (1 + np.exp(-(x + season + logit_mean)))
    cf = cf / cf.mean() * mean_cf
    return pd.Series(np.clip(cf, 0, 1), index=index, name="wind")


def solar(
    index: pd.DatetimeIndex, *, peak_cf: float = 0.75, seed: int = SEED, cloud_persistence: float = 0.9
) -> pd.Series:
    """Solar capacity factor: clear-sky bell, day length by season, persistent cloud noise."""
    rng = np.random.default_rng(seed + 1)
    h = _hour_of_day(index)
    doy = _day_of_year(index)
    # day length swings 8..16 h over the year (mid-latitude), noon at 12:30
    half_day = 0.5 * (12 + 4 * np.cos(2 * np.pi * (doy - 172) / 365.25))
    x = (h - 12.5) / half_day
    clear = np.clip(np.cos(np.pi / 2 * np.clip(x, -1, 1)), 0, None) ** 1.5
    season = 0.75 + 0.25 * np.cos(2 * np.pi * (doy - 172) / 365.25)
    n = len(index)
    cloud = np.empty(n)
    cloud[0] = 0.0
    shocks = rng.standard_normal(n) * np.sqrt(1 - cloud_persistence**2)
    for t in range(1, n):
        cloud[t] = cloud_persistence * cloud[t - 1] + shocks[t]
    clearness = np.clip(0.75 + 0.35 * cloud, 0.15, 1.0)
    cf = peak_cf * clear * season * clearness
    return pd.Series(np.clip(cf, 0, 1), index=index, name="solar")


def heat(index: pd.DatetimeIndex, mean_mw: float, *, seed: int = SEED) -> pd.Series:
    """Space-heat demand: degree-day-like, winter peak about four times the summer floor."""
    rng = np.random.default_rng(seed + 2)
    doy = _day_of_year(index)
    season = 0.25 + 0.75 * (0.5 + 0.5 * np.cos(2 * np.pi * (doy - 15) / 365.25))
    h = _hour_of_day(index)
    diurnal = 0.85 + 0.15 * np.exp(-((h - 7) / 2.5) ** 2) + 0.1 * np.exp(-((h - 20) / 3) ** 2)
    noise = 1 + 0.05 * rng.standard_normal(len(index))
    demand = season * diurnal * noise
    demand = demand / demand.mean() * mean_mw
    return pd.Series(np.clip(demand, 0, None), index=index, name="heat")


def cop(index: pd.DatetimeIndex, *, base: float = 2.5, swing: float = 1.5) -> pd.Series:
    """Air-source heat pump COP: `base` in mid-winter, `base + swing` in mid-summer."""
    doy = _day_of_year(index)
    value = base + swing * (0.5 - 0.5 * np.cos(2 * np.pi * (doy - 15) / 365.25))
    return pd.Series(value, index=index, name="cop")


def load_duration_synthetic(
    steps: int, peak_mw: float, base_mw: float, *, hours: int = HOURS_PER_YEAR
) -> tuple[pd.Series, pd.Series]:
    """A sorted load-duration curve as `steps` load levels with weights summing to `hours`.

    The curve is convex-ish (a few peak hours, a long flat middle), the classic textbook
    shape behind screening-curve arguments. Returns (levels_mw, weights_h), both indexed
    by step number and sorted from the peak down.
    """
    x = (np.arange(steps) + 0.5) / steps
    levels = base_mw + (peak_mw - base_mw) * (1 - x) ** 2.2
    weights = np.full(steps, hours / steps)
    idx = pd.RangeIndex(steps, name="step")
    return pd.Series(levels, index=idx, name="load"), pd.Series(weights, index=idx, name="weight")


def subsample(series: pd.Series, every: int) -> pd.Series:
    """Every `every`-th value; the caller must weight snapshots by `every`."""
    return series.iloc[::every]


def representative_weeks(
    every: int = 3,
    weeks: tuple[tuple[str, int], ...] = (("2025-01-08", 14), ("2025-07-08", 14)),
) -> tuple[pd.DatetimeIndex, float]:
    """A few stretches of the stylised year, and the weight that makes them stand for it.

    Profiles are still generated on the full `year_index(every)` and then sliced, so a
    winter fortnight here is the same winter fortnight as in the year-long models.
    Returns (index, weight_per_snapshot) with weight = 8760 / len(index).
    """
    year = year_index(every)
    parts = [year[(year >= pd.Timestamp(start)) & (year < pd.Timestamp(start) + pd.Timedelta(days=days))] for start, days in weeks]
    index = parts[0].append(parts[1:]) if len(parts) > 1 else parts[0]
    return index, HOURS_PER_YEAR / len(index)
