# NPEDATA - Forecasting and time-series analytics engine.
#
# Copyright 2026 Taoheed Abdulmanan Olaosebikan (Matric 22/10267,
# Computer Science, Caleb University, Lagos). Apache-2.0; see LICENSE/NOTICE.
# Provenance fingerprint 3b191f211c44c1286fd5ec5cf9ddb867988c33da3ea228040c9a7b53226c6966
#
# Pure-Python (no numpy/statsmodels) so it stays transparent, auditable and
# deployable on a minimal host. Every method is classical and its parameters
# are reported back to the caller - no black box, in keeping with the platform.

from __future__ import annotations

import math
from typing import Optional

Z_95 = 1.959963984540054  # two-sided 95% normal quantile


def _mean(xs):
    return sum(xs) / len(xs) if xs else 0.0


def season_length_for(frequency: str) -> int:
    """Seasonal period implied by a series' frequency. 0 = non-seasonal."""
    return {
        "monthly": 12,
        "quarterly": 4,
        "daily": 7,      # weekly seasonality
        "weekly": 52,
    }.get((frequency or "").lower(), 0)


# --------------------------------------------------------------------------- #
#  Holt-Winters exponential smoothing (additive), with a coarse grid search   #
#  over the smoothing constants and normal-approximation prediction bands.    #
# --------------------------------------------------------------------------- #
def _hw_run(values, alpha, beta, gamma, m):
    """One additive Holt-Winters pass. Returns (fitted, level, trend, season)."""
    n = len(values)
    if m and n >= 2 * m:
        level = _mean(values[:m])
        # initial trend: average per-step change between the first two seasons
        trend = sum((values[m + i] - values[i]) for i in range(m)) / (m * m)
        season = [values[i] - level for i in range(m)]
    else:
        m = 0
        level = values[0]
        trend = (values[1] - values[0]) if n > 1 else 0.0
        season = []

    fitted = []
    for t in range(n):
        s = season[t % m] if m else 0.0
        fitted.append(level + trend + s)
        y = values[t]
        if m:
            new_level = alpha * (y - s) + (1 - alpha) * (level + trend)
            new_trend = beta * (new_level - level) + (1 - beta) * trend
            season[t % m] = gamma * (y - new_level) + (1 - gamma) * s
            level, trend = new_level, new_trend
        else:
            new_level = alpha * y + (1 - alpha) * (level + trend)
            trend = beta * (new_level - level) + (1 - beta) * trend
            level = new_level
    return fitted, level, trend, season, m


def _sse(values, fitted):
    return sum((v - f) ** 2 for v, f in zip(values, fitted))


def holt_winters(values, m: int, periods: int, ci: float = 0.95):
    """Additive Holt-Winters forecast with prediction intervals.

    Smoothing constants alpha/beta/gamma are chosen by a coarse grid search
    that minimises in-sample squared error, so the fit is data-driven yet
    fully reported. Falls back to Holt's linear trend when the series is too
    short for a full seasonal cycle.
    """
    n = len(values)
    grid = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9]
    use_season = bool(m and n >= 2 * m)
    best = None
    for a in grid:
        for b in grid:
            gammas = grid if use_season else [0.0]
            for g in gammas:
                fitted, level, trend, season, mm = _hw_run(values, a, b, g, m if use_season else 0)
                err = _sse(values, fitted)
                if best is None or err < best[0]:
                    best = (err, a, b, g, fitted, level, trend, season, mm)

    err, a, b, g, fitted, level, trend, season, mm = best
    # residual standard error (one-step), guard against tiny samples
    dof = max(1, n - (3 if mm else 2))
    resid_sd = math.sqrt(err / dof)
    z = Z_95 if abs(ci - 0.95) < 1e-6 else _z_for(ci)

    forecast = []
    for h in range(1, periods + 1):
        s = season[(n + h - 1) % mm] if mm else 0.0
        point = level + h * trend + s
        # bands widen with the square root of the horizon (naive but honest)
        band = z * resid_sd * math.sqrt(h)
        forecast.append({
            "step": h,
            "value": round(point, 4),
            "lower": round(point - band, 4),
            "upper": round(point + band, 4),
        })

    return {
        "method": "holt_winters_additive" if mm else "holt_linear_trend",
        "seasonal": bool(mm),
        "season_length": mm,
        "params": {"alpha": a, "beta": b, "gamma": g if mm else None},
        "residual_std_error": round(resid_sd, 4),
        "confidence": ci,
        "fitted": [round(f, 4) for f in fitted],
        "forecast": forecast,
    }


def _z_for(ci: float) -> float:
    """Inverse normal CDF (two-sided) via Acklam's rational approximation."""
    p = 1 - (1 - ci) / 2
    a = [-3.969683028665376e+01, 2.209460984245205e+02, -2.759285104469687e+02,
         1.383577518672690e+02, -3.066479806614716e+01, 2.506628277459239e+00]
    b = [-5.447609879822406e+01, 1.615858368580409e+02, -1.556989798598866e+02,
         6.680131188771972e+01, -1.328068155288572e+01]
    c = [-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e+00,
         -2.549732539343734e+00, 4.374664141464968e+00, 2.938163982698783e+00]
    d = [7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e+00,
         3.754408661907416e+00]
    plow, phigh = 0.02425, 1 - 0.02425
    if p < plow:
        q = math.sqrt(-2 * math.log(p))
        return (((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / \
               ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1)
    if p <= phigh:
        q = p - 0.5
        r = q * q
        return (((((a[0] * r + a[1]) * r + a[2]) * r + a[3]) * r + a[4]) * r + a[5]) * q / \
               (((((b[0] * r + b[1]) * r + b[2]) * r + b[3]) * r + b[4]) * r + 1)
    q = math.sqrt(-2 * math.log(1 - p))
    return -(((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / \
           ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1)


# --------------------------------------------------------------------------- #
#  Classical additive seasonal decomposition (trend = centred moving average) #
# --------------------------------------------------------------------------- #
def seasonal_decompose(values, m: int):
    """Additive decomposition: value = trend + seasonal + residual."""
    n = len(values)
    if not m or n < 2 * m:
        return {"seasonal_detected": False, "reason": "series too short for a full seasonal cycle"}

    # centred moving average for the trend
    trend = [None] * n
    half = m // 2
    for i in range(half, n - half):
        if m % 2 == 0:
            window = values[i - half:i + half + 1]
            avg = (sum(window) - 0.5 * window[0] - 0.5 * window[-1]) / m
        else:
            avg = _mean(values[i - half:i + half + 1])
        trend[i] = avg

    # seasonal component: average detrended value per season index, then centre
    detr = [(values[i] - trend[i]) if trend[i] is not None else None for i in range(n)]
    seasonal_idx = []
    for k in range(m):
        vals = [detr[i] for i in range(k, n, m) if detr[i] is not None]
        seasonal_idx.append(_mean(vals) if vals else 0.0)
    centre = _mean(seasonal_idx)
    seasonal_idx = [s - centre for s in seasonal_idx]

    seasonal = [seasonal_idx[i % m] for i in range(n)]
    residual = [
        (values[i] - trend[i] - seasonal[i]) if trend[i] is not None else None
        for i in range(n)
    ]
    # strength of seasonality (0..1), a la Wang/Hyndman
    resid_clean = [r for r in residual if r is not None]
    detr_clean = [values[i] - trend[i] for i in range(n) if trend[i] is not None]
    var_resid = _variance(resid_clean)
    var_detr = _variance(detr_clean)
    strength = max(0.0, 1 - var_resid / var_detr) if var_detr else 0.0

    return {
        "seasonal_detected": True,
        "season_length": m,
        "seasonal_strength": round(strength, 4),
        "trend": [round(t, 4) if t is not None else None for t in trend],
        "seasonal": [round(s, 4) for s in seasonal],
        "residual": [round(r, 4) if r is not None else None for r in residual],
        "seasonal_indices": [round(s, 4) for s in seasonal_idx],
    }


def _variance(xs):
    if len(xs) < 2:
        return 0.0
    mu = _mean(xs)
    return sum((x - mu) ** 2 for x in xs) / (len(xs) - 1)


# --------------------------------------------------------------------------- #
#  Lead / lag cross-correlation between two aligned series.                    #
# --------------------------------------------------------------------------- #
def _pearson(x, y):
    n = len(x)
    if n < 2:
        return 0.0
    mx, my = _mean(x), _mean(y)
    num = sum((a - mx) * (b - my) for a, b in zip(x, y))
    den = math.sqrt(sum((a - mx) ** 2 for a in x) * sum((b - my) ** 2 for b in y))
    return num / den if den else 0.0


def cross_correlation(x, y, max_lag: int):
    """Correlation of x with y shifted by each lag in [-max_lag, +max_lag].

    A positive best_lag means x leads y (x's past predicts y). Useful for
    'does the exchange rate lead inflation?' style questions.
    """
    n = min(len(x), len(y))
    x, y = x[:n], y[:n]
    max_lag = min(max_lag, n - 2) if n > 2 else 0
    results = []
    for lag in range(-max_lag, max_lag + 1):
        if lag < 0:      # y leads x
            a, b = x[-lag:], y[:n + lag]
        elif lag > 0:    # x leads y
            a, b = x[:n - lag], y[lag:]
        else:
            a, b = x, y
        if len(a) >= 2:
            results.append({"lag": lag, "r": round(_pearson(a, b), 4), "n": len(a)})
    best = max(results, key=lambda d: abs(d["r"])) if results else {"lag": 0, "r": 0.0}
    if best["lag"] > 0:
        lead = "x_leads_y"
    elif best["lag"] < 0:
        lead = "y_leads_x"
    else:
        lead = "contemporaneous"
    return {"max_lag": max_lag, "correlations": results, "best": best, "relationship": lead}
