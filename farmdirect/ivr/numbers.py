"""Spoken quantity / price / grade / harvest-date parsers.

Handles:
  * '100 kilos', 'நூறு கிலோ', 'one hundred kg', '200 kg', 'two hundred kg'
  * '38 rupees', 'முப்பத்து எட்டு ரூபாய்', '₹45', '38'
  * 'A', 'A+', 'B', 'C', '1', '2', '3'
  * 'today', 'yesterday', 'இன்று', 'நேற்று', 'date'

All units are normalized to kg / rupees / ISO date.
"""
from datetime import date, timedelta
import re
from typing import Optional, Tuple

# --------------------------------------------------------------------- Tamil number words
_TAMIL_NUMS = {
    "பூஜ்யம்": 0, "ஒன்று": 1, "இரண்டு": 2, "மூன்று": 3, "நான்கு": 4, "ஐந்து": 5,
    "ஆறு": 6, "ஏழு": 7, "எட்டு": 8, "ஒன்பது": 9, "பத்து": 10,
    "பதினொன்று": 11, "பன்னிரண்டு": 12, "பதிமூன்று": 13, "பதினான்கு": 14,
    "பதினைந்து": 15, "பதினாறு": 16, "பதினேழு": 17, "பதினெட்டு": 18, "பத்தொன்பது": 19,
    "இருபது": 20, "முப்பது": 30, "நாற்பது": 40, "ஐம்பது": 50,
    "அறுபது": 60, "எழுபது": 70, "எண்பது": 80, "தொண்ணூறு": 90,
    "நூறு": 100, "இருநூறு": 200, "முன்னூறு": 300, "நாநூறு": 400, "ஐநூறு": 500,
    "ஆறுநூறு": 600, "எழுநூறு": 700, "எண்ணூறு": 800, "தொள்ளாயிரம்": 900,
    "ஆயிரம்": 1000, "முன்னிரண்டு": 2000,
}

# Tamil compound: 'முப்பத்து எட்டு' → 30 + 8
_TAMIL_TENS_PREFIX = {
    "பதின்": 10, "இருபத்து": 20, "முப்பத்து": 30, "நாற்பத்து": 40, "ஐம்பத்து": 50,
    "அறுபத்து": 60, "எழுபத்து": 70, "எண்பத்து": 80, "தொண்ணூற்று": 90,
}

# --------------------------------------------------------------------- English number words
_EN_NUMS = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
    "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15,
    "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19,
    "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50,
    "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90,
    "hundred": 100, "two hundred": 200, "thousand": 1000,
}

_EN_TENS = ["twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety"]


def _words_to_int(phrase: str) -> Optional[int]:
    """Convert a spoken phrase in Tamil or English (or a mix) to int."""
    if not phrase:
        return None
    s = phrase.lower().strip()
    # try plain int first
    digits = re.findall(r"\d+", s)
    if digits:
        try:
            return int("".join(digits))
        except ValueError:
            pass
    # split by whitespace
    tokens = s.replace(",", " ").split()
    if not tokens:
        return None
    total = 0
    current = 0
    matched_any = False
    for tok in tokens:
        v = _EN_NUMS.get(tok)
        if v is None:
            v = _TAMIL_NUMS.get(tok)
        if v is None:
            # try tens prefix (Tamil)
            for prefix, val in _TAMIL_TENS_PREFIX.items():
                if tok.startswith(prefix):
                    remainder = tok[len(prefix):].strip()
                    v = val + (_TAMIL_NUMS.get(remainder, 0) if remainder else 0)
                    break
        if v is None:
            continue
        matched_any = True
        if v == 100:
            current = (current if current else 1) * 100
        elif v == 1000:
            current = (current if current else 1) * 1000
        elif v >= 100:
            current += v
        elif v >= 20 and current and current < 100:
            # e.g. 'one twenty' (rare) — append
            current += v
        else:
            current += v
    if not matched_any:
        return None
    total = current
    return total if total > 0 else None


def parse_quantity(spoken: str) -> Tuple[Optional[float], Optional[str]]:
    """Return (quantity_kg, unit). Unit is always 'kg' for now."""
    if not spoken:
        return None, None
    s = spoken.lower().strip()

    # direct number + kg pattern
    m = re.search(r"(\d+(?:\.\d+)?)\s*(kg|kilo|kilogram|kilos|kgs)?", s)
    if m:
        try:
            val = float(m.group(1))
            if val > 0:
                return val, "kg"
        except ValueError:
            pass

    # 'ton' or 'tonnes'?
    m = re.search(r"(\d+(?:\.\d+)?)\s*(ton|tonne|tons)", s)
    if m:
        try:
            return float(m.group(1)) * 1000.0, "kg"
        except ValueError:
            pass

    # try words-to-int on the whole phrase
    n = _words_to_int(s)
    if n and n > 0:
        return float(n), "kg"
    return None, None


def parse_price(spoken: str) -> Optional[float]:
    """Return price per kg as float, or None."""
    if not spoken:
        return None
    s = spoken.replace(",", " ").strip()
    # 1) explicit rupee symbol / keyword
    m = re.search(r"(?:₹|rs\.?|rupees?|ரூபாய்)?\s*(\d+(?:\.\d+)?)", s, re.IGNORECASE)
    if m:
        try:
            v = float(m.group(1))
            if v > 0:
                return v
        except ValueError:
            pass
    # 2) word form
    n = _words_to_int(s)
    if n and n > 0:
        return float(n)
    return None


def parse_grade(spoken: str) -> Optional[str]:
    """Return 'A+', 'A', 'B', or 'C'. Handles DTMF 1/2/3."""
    if not spoken:
        return None
    s = str(spoken).strip().lower()
    if s in ("1", "a+", "a plus", "ஏ பிளஸ்", "ஏ+"):
        return "A+"
    if s in ("2", "a", "ஏ"):
        return "A"
    if s in ("3", "b", "பி"):
        return "B"
    if s in ("4", "c", "சி"):
        return "C"
    return None


def parse_harvest_offset(spoken: str) -> Tuple[Optional[str], Optional[int]]:
    """Return (label, offset_days).

    ``label`` is a human-readable label (localized by caller if needed).
    ``offset_days`` is 0 (today), -1 (yesterday), or None if it's a date.
    For a date string we return (date_iso, None).
    """
    if not spoken:
        return None, None
    s = spoken.lower().strip()
    if s in ("today", "இன்று", "இன்று", "inru"):
        return ("today", 0)
    if s in ("yesterday", "நேற்று", "netru"):
        return ("yesterday", -1)
    if s in ("day_before_yesterday", "முன்னாள்", "நேற்று முன்னாள்"):
        return ("day_before", -2)
    # ISO date
    m = re.search(r"(\d{4}-\d{2}-\d{2})", s)
    if m:
        return (m.group(1), None)
    # dd/mm/yyyy
    m = re.search(r"(\d{1,2})[/-](\d{1,2})[/-](\d{4})", s)
    if m:
        d, mth, y = m.groups()
        try:
            iso = f"{int(y):04d}-{int(mth):02d}-{int(d):02d}"
            return (iso, None)
        except ValueError:
            pass
    return None, None


def harvest_label_to_iso(label: str, offset: Optional[int]) -> Optional[str]:
    """Convert (label, offset) returned by ``parse_harvest_offset`` into a YYYY-MM-DD string."""
    if not label:
        return None
    if offset is not None:
        return (date.today() + timedelta(days=offset)).isoformat()
    # label is already ISO
    try:
        date.fromisoformat(label)
        return label
    except ValueError:
        return None


# Tamil ordinal labels used in summaries
HARVEST_LABEL_TA = {
    "today": "இன்று",
    "yesterday": "நேற்று",
    "day_before": "முன்னாள்",
}
HARVEST_LABEL_EN = {
    "today": "today",
    "yesterday": "yesterday",
    "day_before": "the day before yesterday",
}
