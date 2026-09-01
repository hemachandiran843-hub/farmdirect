"""AI Module 3 — Logistics Route Optimization
============================================
Groups nearby deliveries into vehicle routes and orders the stops.

Pipeline (all offline, deterministic):
  1. KMeans clustering (scikit-learn) of drop points around the hub
  2. Nearest-neighbour route construction per cluster
  3. 2-opt local search improvement
  4. Compare against the naive baseline (one dedicated trip per delivery)

Returns GeoJSON-ish route objects ready for the SVG map mockup.
"""
import math
from datetime import datetime

import numpy as np
from sklearn.cluster import KMeans

import db

AVG_SPEED_KMH = 26          # Indian city average with stops
SERVICE_MIN_PER_STOP = 8
HUB = {"name": "FarmDirect City Hub", "lat": 19.9975, "lng": 73.7898}  # Nashik-like mock city


def haversine_km(lat1, lng1, lat2, lng2):
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def route_length_km(points):
    total = 0.0
    for a, b in zip(points, points[1:]):
        total += haversine_km(a["lat"], a["lng"], b["lat"], b["lng"])
    return total


def _two_opt(points):
    """In-place 2-opt improvement on a list of {'lat','lng','label',...}."""
    improved = True
    while improved:
        improved = False
        for i in range(1, len(points) - 2):
            for j in range(i + 1, len(points) - 1):
                if (haversine_km(points[i - 1]["lat"], points[i - 1]["lng"],
                                 points[j]["lat"], points[j]["lng"]) +
                    haversine_km(points[i]["lat"], points[i]["lng"],
                                 points[j + 1]["lat"], points[j + 1]["lng"])) < \
                   (haversine_km(points[i - 1]["lat"], points[i - 1]["lng"],
                                 points[i]["lat"], points[i]["lng"]) +
                    haversine_km(points[j]["lat"], points[j]["lng"],
                                 points[j + 1]["lat"], points[j + 1]["lng"])):
                    points[i:j + 1] = reversed(points[i:j + 1])
                    improved = True
    return points


def _eta_minutes(km, stops):
    return int(round(km / AVG_SPEED_KMH * 60 + stops * SERVICE_MIN_PER_STOP))


def optimize_routes(deliveries, num_vehicles=3):
    """deliveries: list of dicts with id, drop_lat, drop_lng, order_code, area.
    Returns dict with routes, baseline stats and savings."""
    pts = [(d["drop_lat"], d["drop_lng"]) for d in deliveries]
    n = len(pts)
    if n == 0:
        return {"routes": [], "baseline": {}, "savings_pct": 0, "generated_at": datetime.now().isoformat()}

    coords = np.array(pts)
    k = max(1, min(num_vehicles, n))

    # 1) Cluster nearby drops (spread if fewer deliveries than vehicles)
    if n <= k:
        labels = np.arange(n)
        k_eff = n
    else:
        km = KMeans(n_clusters=k, n_init=10, random_state=42).fit(coords)
        labels, k_eff = km.labels_, k

    routes = []
    for c in range(k_eff):
        idxs = list(np.where(labels == c)[0])
        if not idxs:
            continue
        stops = [{"seq": 0, "delivery_id": deliveries[i]["id"],
                  "order_code": deliveries[i]["order_code"],
                  "area": deliveries[i].get("area", ""),
                  "buyer": deliveries[i].get("buyer", ""),
                  "lat": float(coords[i][0]), "lng": float(coords[i][1])}
                 for i in idxs]
        # 2) Nearest neighbour from hub
        remaining, ordered = list(stops), []
        cur = (HUB["lat"], HUB["lng"])
        while remaining:
            nxt = min(remaining, key=lambda s: haversine_km(cur[0], cur[1], s["lat"], s["lng"]))
            ordered.append(nxt)
            remaining.remove(nxt)
            cur = (nxt["lat"], nxt["lng"])
        # 3) 2-opt improve
        ordered = _two_opt(ordered)
        for s_i, s in enumerate(ordered, start=1):
            s["seq"] = s_i

        path = [{"lat": HUB["lat"], "lng": HUB["lng"], "label": "Hub"}] + ordered \
               + [{"lat": HUB["lat"], "lng": HUB["lng"], "label": "Hub"}]
        dist = route_length_km(path)
        routes.append({
            "route_id": c + 1,
            "vehicle": f"EV Van {c + 1}",
            "driver": ["R. Pawar", "S. Kumar", "A. Shah", "M. Verma", "K. Singh"][c % 5],
            "stops": ordered,
            "path": path,
            "distance_km": round(dist, 1),
            "eta_minutes": _eta_minutes(dist, len(ordered)),
            "deliveries": len(ordered),
        })

    # Baseline: separate hub→drop→hub trip per delivery
    baseline_km = sum(2 * haversine_km(HUB["lat"], HUB["lng"], la, ln) for la, ln in pts)
    optimized_km = sum(r["distance_km"] for r in routes)
    baseline_eta = sum(_eta_minutes(2 * haversine_km(HUB["lat"], HUB["lng"], la, ln), 1) for la, ln in pts)
    optimized_eta = sum(r["eta_minutes"] for r in routes)

    return {
        "routes": routes,
        "baseline": {
            "distance_km": round(baseline_km, 1),
            "eta_minutes": baseline_eta,
            "trips": n,
        },
        "optimized": {
            "distance_km": round(optimized_km, 1),
            "eta_minutes": optimized_eta,
            "vehicles": len(routes),
        },
        "savings_pct": round((1 - optimized_km / max(baseline_km, 0.1)) * 100, 1),
        "generated_at": datetime.now().strftime("%d %b %Y, %H:%M"),
    }


def optimize_from_db():
    """Optimize all city-region deliveries that are confirmed but not yet picked up.
    Inter-city bulk trips (Pune/Mumbai linehaul) are handled separately."""
    rows = db.query(
        "SELECT d.id, d.order_id, d.drop_lat, d.drop_lng, o.order_code, "
        "       o.delivery_city AS area, u.name AS buyer "
        "FROM deliveries d JOIN orders o ON o.id=d.order_id "
        "JOIN users u ON u.id=o.buyer_id "
        "WHERE d.status IN ('confirmed') AND d.drop_lat IS NOT NULL")
    # Keep only stops inside the simulated city service region (~60 km around hub)
    data = [dict(r) for r in rows
            if abs(r["drop_lat"] - HUB["lat"]) < 0.55 and abs(r["drop_lng"] - HUB["lng"]) < 0.55]
    if not data:
        return {"routes": [], "baseline": {"distance_km": 0, "eta_minutes": 0, "trips": 0},
                "optimized": {"distance_km": 0, "eta_minutes": 0, "vehicles": 0},
                "savings_pct": 0, "generated_at": datetime.now().strftime("%d %b %Y, %H:%M"),
                "skipped_intercity": len(rows) - len(data)}
    vehicles = 2 if len(data) < 7 else 3
    result = optimize_routes(data, num_vehicles=vehicles)
    result["skipped_intercity"] = len(rows) - len(data)
    for r in result["routes"]:
        for s in r["stops"]:
            db.execute("UPDATE deliveries SET route_id=? WHERE id=?", (r["route_id"], s["delivery_id"]))
    return result
