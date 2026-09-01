"""Product synonym dictionary for IVR recognition.

Maps Tamil / Tanglish / English spoken names to the canonical ``crop``
name used by the FarmDirect marketplace (matches the seeded
``PRODUCT_CATALOG`` and ``sales_history`` crops).
"""
from typing import Optional, Dict, List

# Each canonical crop → set of spoken synonyms (lower-case, ASCII folded).
# Tamil unicode letters are kept as-is.
_PRODUCT_SYNONYMS_RAW: Dict[str, List[str]] = {
    "Tomato": ["tomato", "tomatoes", "தக்காளி", "தக்காளிகள்", "thakkali", "thakkali", "tomato price"],
    "Onion":  ["onion", "onions", "வெங்காயம்", "vengayam", "பெரிய வெங்காயம்", "big onion"],
    "Potato": ["potato", "potatoes", "உருளைக்கிழங்கு", "urulaikilangu", "urulai"],
    "Rice":   ["rice", "அரிசி", "arisi", "paddy", "நெல்"],
    "Banana": ["banana", "bananas", "வாழைப்பழம்", "வாழை", "vazhaipazham", "vazhai"],
    "Mango":  ["mango", "mangoes", "மாம்பழம்", "மா", "mampazham", "mango fruit"],
    "Carrot": ["carrot", "கேரட்", "காரட்", "carrot vegetable"],
    "Spinach": ["spinach", "palak", "பாலக்கீரை", "பசலை", " keerai", "கீரை"],
    "Wheat":  ["wheat", "கோதுமை", "godhumai"],
    "Green Chili": ["green chili", "green chilli", "chili", "chilli", "பச்சை மிளகாய்", "milagai", "மிளகாய்"],
    "Cauliflower": ["cauliflower", "காலிஃப்ளவர்", "மல்லி பூ", "phool gobi"],
    "Cabbage":  ["cabbage", "முட்டைகோஸ்", "muttaikos", "kos"],
}

# Flat reverse-map: synonym → canonical crop. Lookup is case-insensitive
# and strips surrounding whitespace.
PRODUCT_SYNONYMS: Dict[str, str] = {}
for _canon, _syns in _PRODUCT_SYNONYMS_RAW.items():
    for _s in _syns:
        PRODUCT_SYNONYMS[_s.strip().lower()] = _canon
    # always map the canonical name itself too
    PRODUCT_SYNONYMS[_canon.lower()] = _canon


def normalize_product(spoken: str) -> Optional[str]:
    """Return the canonical crop name, or ``None`` if not recognised.

    Tries a direct lookup, then a substring scan (so '100 kilo tomato irukku'
    still resolves to 'Tomato').
    """
    if not spoken:
        return None
    s = spoken.lower().strip()
    if s in PRODUCT_SYNONYMS:
        return PRODUCT_SYNONYMS[s]
    # try each synonym as a substring
    for syn, canon in PRODUCT_SYNONYMS.items():
        if len(syn) >= 3 and syn in s:
            return canon
    return None


def all_canonical_crops() -> list[str]:
    return sorted({c for c in PRODUCT_SYNONYMS.values()})
