"""AI Module 1 — Demand Forecasting
=================================
Predicts expected demand for the next 7 / 30 days for a given crop.

Hybrid model (scikit-learn + domain rules), fully offline:
  1. LinearRegression on the LAST 60 DAYS with engineered features:
     - time trend            (platform adoption growth)
     - day-of-week season    (sin/cos — weekend market uplift)
     - market/weather signal (smooth seasonal curve proxying weather,
                              arrivals & market trends)
  2. A short recent window keeps the regression stable — no wild
     extrapolation across unseen month boundaries.
  3. An explicit FESTIVAL/MARKET UPLIFT factor (Sep–Nov festive season,
     documented domain knowledge) is applied to the forecast window.

Uses the sales_history table written by the seeder. Deterministic.
"""
import json
import math
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_absolute_percentage_error

import db

FESTIVAL_MONTHS = (9, 10, 11)
FESTIVAL_UPLIFT = 1.12   # +12% regional demand during festive season


def _load_history(crop: str, city: str | None = None) -> pd.DataFrame:
    sql = "SELECT date, SUM(quantity_kg) AS qty, AVG(avg_price) AS price " \
          "FROM sales_history WHERE crop = ?"
    args = [crop]
    if city:
        sql += " AND city = ?"
        args.append(city)
    sql += " GROUP BY date ORDER BY date"
    rows = db.query(sql, args)
    if not rows:
        return pd.DataFrame(columns=["date", "qty"])
    df = pd.DataFrame([dict(r) for r in rows])
    df["date"] = pd.to_datetime(df["date"])
    return df


def _make_features(dates: pd.Series, t0) -> pd.DataFrame:
    """Feature engineering shared by train & predict."""
    doy = dates.dt.dayofyear
    return pd.DataFrame({
        "t": (dates - t0).dt.days.astype(float),
        "dow_sin": np.sin(2 * math.pi * dates.dt.dayofweek / 7),
        "dow_cos": np.cos(2 * math.pi * dates.dt.dayofweek / 7),
        "market_signal": 0.35 * np.sin(2 * math.pi * doy / 365.0) +
                         0.12 * np.sin(2 * math.pi * doy / 29.0),
    })


def _festival_factor(dates) -> float:
    """Mean festival uplift across the given forecast dates."""
    months = pd.DatetimeIndex(dates).month
    return float(np.mean([FESTIVAL_UPLIFT if m in FESTIVAL_MONTHS else 1.0 for m in months]))


def forecast_crop(crop: str, city: str | None = None, horizon_days: int = 7) -> dict:
    """Return a forecast dict; also persists it into demand_forecasts."""
    horizon_days = int(horizon_days) if horizon_days in (7, 30) else 7
    hist = _load_history(crop, city)

    if hist.empty or len(hist) < 21:
        # Not enough data -> flat baseline forecast
        base = float(hist["qty"].mean()) if not hist.empty else 500.0
        base = max(base, 50.0)
        result = {
            "crop": crop, "city": city, "horizon_days": horizon_days,
            "current_demand": round(base * 7, 1),
            "predicted_demand": round(base * 7 * 1.0, 1),
            "trend": "Stable", "confidence": 0.55,
            "history": [], "forecast": [],
        }
        _save(result)
        return result

    daily = (hist.groupby("date", as_index=False)["qty"].sum()
                 .sort_values("date").reset_index(drop=True))
    daily = daily[daily["date"] >= daily["date"].max() - pd.Timedelta(days=60)]

    y = daily["qty"].values.astype(float)
    t0 = daily["date"].min()
    X = _make_features(daily["date"], t0)

    model = LinearRegression()
    model.fit(X, y)

    # Back-test confidence on the last 21 days
    if len(daily) > 21:
        pred_bt = model.predict(X.iloc[-21:])
        mape = mean_absolute_percentage_error(y[-21:], np.clip(pred_bt, 1, None))
        confidence = float(max(0.55, min(0.96, 1.0 - mape)))
    else:
        confidence = 0.7

    # ----- Future dates -----
    last_date = daily["date"].max()
    future_dates = pd.date_range(last_date + pd.Timedelta(days=1),
                                 periods=horizon_days, freq="D")
    X_future = _make_features(future_dates.to_series().reset_index(drop=True), t0)
    fc = np.clip(model.predict(X_future), 0, None)

    # Festival / market-trend uplift on the forecast window (domain rule)
    fest = _festival_factor(future_dates)
    fc = fc * fest

    # Demand comparison: current = avg of last 4 weeks, predicted = next week
    last28 = daily[daily["date"] > last_date - pd.Timedelta(days=28)]["qty"]
    current_weekly = float(last28.mean() * 7)
    fc_weekly = float(fc[:min(7, len(fc))].sum())

    change = (fc_weekly - current_weekly) / max(current_weekly, 1.0)
    trend = "Increasing" if change > 0.04 else ("Decreasing" if change < -0.04 else "Stable")

    # Chart payload: last 45 days actual + forecast series
    tail = daily[daily["date"] > last_date - pd.Timedelta(days=45)]
    history_pts = [{"d": d.strftime("%b %d"), "q": round(q, 1)}
                   for d, q in zip(tail["date"], tail["qty"])]
    bridge_date = [tail["date"].iloc[-1]] if not tail.empty else [last_date]
    bridge_val = [float(tail["qty"].iloc[-1])] if not tail.empty else [y[-1]]
    forecast_pts = [{"d": d.strftime("%b %d"), "q": round(q, 1)}
                    for d, q in zip(bridge_date + list(future_dates), bridge_val + list(fc))]

    result = {
        "crop": crop, "city": city, "horizon_days": horizon_days,
        "current_demand": round(current_weekly, 1),
        "predicted_demand": round(fc_weekly, 1),
        "trend": trend, "confidence": round(confidence, 2),
        "history": history_pts, "forecast": forecast_pts,
        "model": "sklearn LinearRegression + festival uplift",
        "festival_uplift": round(fest, 2),
        "total_horizon": round(float(fc.sum()), 1),
    }
    _save(result)
    return result


def _save(result: dict):
    db.execute(
        "INSERT INTO demand_forecasts "
        "(crop, city, horizon_days, current_demand, predicted_demand, trend, confidence, payload) "
        "VALUES (?,?,?,?,?,?,?,?)",
        (result["crop"], result["city"], result["horizon_days"],
         result["current_demand"], result["predicted_demand"], result["trend"],
         result["confidence"], json.dumps(result["forecast"])),
    )


def forecast_all_crops(horizon_days: int = 7) -> list[dict]:
    """Forecast every crop present in sales_history (used on dashboards)."""
    crops = [r["crop"] for r in db.query(
        "SELECT DISTINCT crop FROM sales_history ORDER BY crop")]
    return [forecast_crop(c, None, horizon_days) for c in crops]


def top_opportunities(limit: int = 4) -> list[dict]:
    """Crops with the strongest increasing demand — 'what should I grow/sell'."""
    fc = forecast_all_crops(7)
    for f in fc:
        f["change_pct"] = round(
            (f["predicted_demand"] - f["current_demand"]) / max(f["current_demand"], 1) * 100, 1)
    inc = sorted(fc, key=lambda x: x["change_pct"], reverse=True)
    return inc[:limit]
