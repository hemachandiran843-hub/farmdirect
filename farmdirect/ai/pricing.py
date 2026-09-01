"""AI Module 2 — Price Recommendation Engine
===========================================
Suggests the best selling price for a farmer's produce using:
  - predicted demand (from the forecasting module)
  - current supply listed on the marketplace
  - historical price trend (last 90 days, numpy polyfit)
  - distance to the nearest demand hub (transport cost)
  - quality grade + organic premium

Outputs the full transparent factor breakdown so judges can see the logic.
100% offline, deterministic.
"""
import json
from datetime import datetime

import numpy as np

import db
from ai.forecasting import forecast_crop

GRADE_FACTOR = {"A": 1.10, "B": 1.00, "C": 0.87}
ORGANIC_FACTOR = 1.08
PLATFORM_FEE_PCT = 0.06          # FarmDirect commission
LOGISTICS_PER_KM_PER_KG = 0.12   # ₹ per kg per km pooled transport
TRADITIONAL_MARKUP = 1.80        # traditional retail ≈ 1.8 × mandi (4 middlemen)

# Distance (km) of each city from its nearest major demand hub (simulated network)
CITY_HUB_DISTANCE = {
    "Nashik": 42, "Pune": 0, "Mumbai": 0, "Guntur": 0, "Vijayawada": 0,
    "Hooghly": 0, "Kolkata": 0, "Nagpur": 0, "Hyderabad": 12, "Bengaluru": 0,
    "Delhi NCR": 0, "Lucknow": 18, "Indore": 25, "Jaipur": 30, "Ahmedabad": 15,
}
DEFAULT_HUB_DISTANCE = 35


def _base_price(crop: str) -> tuple[float, float]:
    """Return (recent avg market price ₹/kg, 90-day trend % per month)."""
    rows = db.query(
        "SELECT date, avg_price FROM sales_history WHERE crop=? ORDER BY date",
        (crop,))
    if not rows:
        return 30.0, 0.0
    prices = np.array([r["avg_price"] or 0 for r in rows], dtype=float)
    prices = prices[prices > 0]
    if prices.size == 0:
        return 30.0, 0.0
    base = float(prices[-min(30, prices.size):].mean())
    # Linear trend on the last 90 points (₹ per month)
    tail = prices[-90:]
    if tail.size > 10:
        x = np.arange(tail.size)
        slope_per_day = float(np.polyfit(x, tail, 1)[0])
        trend_pct = slope_per_day * 30 / max(base, 1) * 100
    else:
        trend_pct = 0.0
    return round(base, 2), round(float(np.clip(trend_pct, -8, 8)), 2)


def _supply_demand_ratio(crop: str) -> float:
    """Active listed supply (kg) vs forecast weekly demand (kg). <1 = scarcity."""
    supply = db.query(
        "SELECT COALESCE(SUM(quantity_kg),0) AS s FROM products "
        "WHERE crop=? AND status='active'", (crop,), one=True)["s"]
    fc = forecast_crop(crop, None, 7)
    demand = max(fc["predicted_demand"], 1.0)
    return float(supply) / demand, fc


def recommend_price(crop: str, grade: str = "A", quantity_kg: float = 100,
                    city: str | None = None, current_price: float | None = None,
                    organic: bool = False) -> dict:
    grade = grade if grade in GRADE_FACTOR else "B"
    quantity_kg = max(float(quantity_kg or 0), 1)

    base, trend_pct = _base_price(crop)
    ratio, fc = _supply_demand_ratio(crop)

    # 1) Demand–supply factor: scarcity pushes price up, surplus pulls down
    if ratio < 0.8:
        demand_factor = 1.18
    elif ratio < 1.0:
        demand_factor = 1.10
    elif ratio < 1.4:
        demand_factor = 1.02
    elif ratio < 2.0:
        demand_factor = 0.94
    else:
        demand_factor = 0.88
    if fc["trend"] == "Increasing":
        demand_factor *= 1.05
    elif fc["trend"] == "Decreasing":
        demand_factor *= 0.95

    # 2) Historical momentum (capped)
    momentum = 1 + float(np.clip(trend_pct / 100.0, -0.08, 0.08)) * 0.6

    # 3) Quality & organic
    quality = GRADE_FACTOR[grade] * (ORGANIC_FACTOR if organic else 1.0)

    # 4) Volume bonus for bulk deals
    volume = 1.0 if quantity_kg < 500 else (0.97 if quantity_kg < 2000 else 0.93)

    # 5) Distance to demand hub → transport drag on the net price
    dist = CITY_HUB_DISTANCE.get(city or "", DEFAULT_HUB_DISTANCE)
    transport_cost = round(LOGISTICS_PER_KM_PER_KG * dist, 2)

    suggested = base * demand_factor * momentum * quality * volume
    suggested = float(np.clip(suggested, base * 0.75, base * 1.45))
    suggested = round(suggested * 2) / 2  # round to nearest ₹0.50

    consumer_price = round(suggested * (1 + PLATFORM_FEE_PCT) + transport_cost, 1)
    mandi_price = round(base, 1)                            # what intermediaries pay today
    traditional_retail = round(base * TRADITIONAL_MARKUP, 1)

    gain_pct = round((suggested - mandi_price) / max(mandi_price, 1) * 100, 1)
    consumer_saving_pct = round((traditional_retail - consumer_price) /
                                max(traditional_retail, 1) * 100, 1)
    extra_earn = round((suggested - mandi_price) * min(quantity_kg, 2000), 0)

    factors = {
        "base_market_price": base,
        "price_trend_90d_pct": trend_pct,
        "supply_demand_ratio": round(ratio, 2),
        "predicted_weekly_demand": fc["predicted_demand"],
        "demand_factor": round(demand_factor, 3),
        "momentum": round(momentum, 3),
        "quality_factor": round(quality, 3),
        "volume_factor": round(volume, 3),
        "hub_distance_km": dist,
        "transport_cost_per_kg": transport_cost,
        "confidence": fc["confidence"],
    }

    result = {
        "crop": crop, "grade": grade, "quantity_kg": quantity_kg, "city": city,
        "current_price": current_price if current_price else mandi_price,
        "suggested_price": suggested,
        "consumer_price": consumer_price,
        "mandi_price": mandi_price,
        "traditional_retail": traditional_retail,
        "earnings_gain_pct": gain_pct,
        "consumer_saving_pct": consumer_saving_pct,
        "extra_earnings_on_qty": extra_earn,
        "factors": factors,
    }
    db.execute(
        "INSERT INTO price_recommendations "
        "(crop, grade, quantity_kg, current_price, suggested_price, consumer_price, "
        " mandi_price, earnings_gain_pct, factors) VALUES (?,?,?,?,?,?,?,?,?)",
        (crop, grade, quantity_kg, result["current_price"], suggested,
         consumer_price, mandi_price, gain_pct, json.dumps(factors)))
    return result
