"""Shared helpers: formatting, crop metadata, status pipelines."""
from datetime import datetime, timedelta

# Crop metadata: emoji icon + card gradient (works 100% offline, no images needed)
CROP_META = {
    "Tomato":     {"icon": "\U0001F345", "grad": "linear-gradient(135deg,#ff9a8b,#ff6a88)"},
    "Onion":      {"icon": "\U0001F9C5", "grad": "linear-gradient(135deg,#e8c39e,#c98d5e)"},
    "Potato":     {"icon": "\U0001F954", "grad": "linear-gradient(135deg,#e6d3a3,#c9a86a)"},
    "Rice":       {"icon": "\U0001F33E", "grad": "linear-gradient(135deg,#f7e08b,#d9b93c)"},
    "Banana":     {"icon": "\U0001F34C", "grad": "linear-gradient(135deg,#ffe259,#ffa751)"},
    "Mango":      {"icon": "\U0001F96D", "grad": "linear-gradient(135deg,#f6d365,#fda085)"},
    "Carrot":     {"icon": "\U0001F955", "grad": "linear-gradient(135deg,#ffb199,#ff7b54)"},
    "Spinach":    {"icon": "\U0001F96C", "grad": "linear-gradient(135deg,#a8e063,#56ab2f)"},
    "Wheat":      {"icon": "\U0001F33E", "grad": "linear-gradient(135deg,#f3e2c0,#c8a253)"},
    "Green Chili":{"icon": "\U0001F336", "grad": "linear-gradient(135deg,#96e6a1,#2f9e44)"},
    "Cauliflower":{"icon": "\U0001F966", "grad": "linear-gradient(135deg,#f5f0e6,#d9c9a3)"},
    "Cabbage":    {"icon": "\U0001F966", "grad": "linear-gradient(135deg,#b7e4c7,#74c69d)"},
}

ORDER_STEPS = ["pending", "confirmed", "picked_up", "in_transit", "delivered"]


def inr(value, symbol="\u20B9"):
    """Format a number as Indian Rupees."""
    try:
        v = float(value)
    except (TypeError, ValueError):
        return f"{symbol}0"
    s = f"{v:,.0f}" if v >= 100 or float(v).is_integer() else f"{v:,.2f}"
    return f"{symbol}{s}"


def kg(value):
    """Format kg quantity."""
    try:
        v = float(value)
    except (TypeError, ValueError):
        return "0 kg"
    if v >= 1000:
        return f"{v / 1000:.1f} ton"
    return f"{v:g} kg"


def pretty_status(s):
    return (s or "").replace("_", " ").title()


def status_steps(status):
    """Return (current_index, total) for the delivery pipeline."""
    try:
        return ORDER_STEPS.index(status), len(ORDER_STEPS) - 1
    except ValueError:
        return -1, len(ORDER_STEPS) - 1


def days_ago(date_str):
    try:
        d = datetime.strptime(str(date_str)[:10], "%Y-%m-%d").date()
        n = (datetime.now().date() - d).days
        if n <= 0:
            return "today"
        if n == 1:
            return "yesterday"
        return f"{n} days ago"
    except (ValueError, TypeError):
        return ""


def today_str(offset_days=0):
    return (datetime.now() + timedelta(days=offset_days)).strftime("%Y-%m-%d")
