"""IVR intent recognizer.

Pure-Python rule-based NLU. No external API key, works 100% offline —
just like the rest of FarmDirect's AI stack (forecasting / pricing /
routing all use local scikit-learn + rules).

Inputs: a spoken/typed phrase (Tamil, English, Tanglish) or a DTMF key.
Output: a structured ``IntentResult`` with the top-level intent and
extracted entities (product, quantity, unit, price, grade, harvest).

Why rule-based for a hackathon:
  * deterministic and explainable (matches the app's AI philosophy)
  * zero extra infrastructure
  * trivially supports Tamil + Tanglish without a Tamil-language model
  * easy to extend via ``PRODUCT_SYNONYMS`` + keyword lists
"""
from dataclasses import dataclass, field, asdict
from typing import Optional, Dict, Any

from .products_dict import normalize_product
from .numbers import parse_quantity, parse_price, parse_grade, parse_harvest_offset

# ----------------------------------------------------------------- intent constants
LIST_PRODUCE   = "LIST_PRODUCE"
MARKET_PRICE   = "MARKET_PRICE"
ORDER_STATUS   = "ORDER_STATUS"
DELIVERY_STATUS= "DELIVERY_STATUS"
BULK_ORDER     = "BULK_ORDER"
EARNINGS       = "EARNINGS"
HELP           = "HELP"
LANGUAGE_CHANGE= "LANGUAGE_CHANGE"
CANCEL         = "CANCEL"
CONFIRM        = "CONFIRM"
CHANGE         = "CHANGE"
REPEAT         = "REPEAT"
GO_BACK        = "GO_BACK"
MAIN_MENU      = "MAIN_MENU"
UNKNOWN        = "UNKNOWN"
RAW_NUMBER     = "RAW_NUMBER"      # used inside listing flow when user just said '100'

# Tamil keyword groups — order matters, more specific first
_TAMIL_PRICE_WORDS = ["விலை", "விலையை", "விலையென்ன", "விலை என்ன"]
_TAMIL_LIST_WORDS  = ["விற்க", "விற்பனை", "பதிவு", "என்னிடம்", "இருக்கு", "விளைபொருள்"]
_TAMIL_ORDER_WORDS = ["ஆர்டர்", "ஆர்டர்கள்", "ஆர்டர் எங்கே", "எனது ஆர்டர்"]
_TAMIL_DELIVERY_WORDS = ["டெலிவரி", "pickup", "பிக்கப்", "டெலிவரி நிலை"]
_TAMIL_BULK_WORDS = ["மொத்த", "பெரிய ஆர்டர்", "பெரிய ஆர்டர் ஏதாவது", "bulk"]
_TAMIL_EARN_WORDS = ["வருமானம்", "வருமானத்தை", "பணம்", "எவ்வளவு பணம்", "எனக்கு எவ்வளவு"]
_TAMIL_HELP_WORDS = ["உதவி", "உதவிக்கு", "எப்படி", "என்ன செய்ய"]
_TAMIL_CANCEL_WORDS = ["ரத்து", "ரத்து செய்", "வேண்டாம்"]
_TAMIL_REPEAT_WORDS = ["மீண்டும்", "மீண்டும் சொல்லுங்கள்", "திரும்ப சொல்லுங்கள்"]
_TAMIL_BACK_WORDS = ["பின்னாடி", "பின்னாடி போ", "திரும்பி போ", "பின்"]
_TAMIL_MAIN_MENU_WORDS = ["முக்கிய மெனு", "முதன்மை மெனு", "பிரதான மெனு"]
_TAMIL_CONFIRM_WORDS = ["சரி", "ஆம்", "பதிவு செய்", "உறுதி", "சரி பதிவு செய்"]
_TAMIL_CHANGE_WORDS = ["மாற்ற", "மாற்று", "வேறு"]

_EN_PRICE_WORDS = ["price", "what price", "today price", "market price", "rate"]
_EN_LIST_WORDS  = ["i have", "sell", "list", "listing", "produce", "harvest"]
_EN_ORDER_WORDS = ["my order", "where is my order", "order status", "orders"]
_EN_DELIVERY_WORDS = ["delivery", "pickup", "delivery status", "where is the delivery"]
_EN_BULK_WORDS = ["bulk", "bulk order", "big order", "any bulk"]
_EN_EARN_WORDS = ["earnings", "income", "how much money", "money received", "payment"]
_EN_HELP_WORDS = ["help", "how to", "support"]
_EN_CANCEL_WORDS = ["cancel", "no", "never mind", "stop"]
_EN_REPEAT_WORDS = ["repeat", "say again", "again", "what did you say"]
_EN_BACK_WORDS = ["back", "go back", "previous"]
_EN_MAIN_MENU_WORDS = ["main menu", "home", "start over"]
_EN_CONFIRM_WORDS = ["confirm", "yes", "ok", "okay", "go ahead", "register", "submit"]
_EN_CHANGE_WORDS = ["change", "edit", "modify", "different"]

_TANG_HELPERS = ["enna", "irukku", "irukkku", "engga", "enga", "vendam", "seri", "ok"]


@dataclass
class IntentResult:
    """Structured intent + extracted entities."""
    intent: str = UNKNOWN
    confidence: float = 0.0
    product: Optional[str] = None        # canonical crop name
    quantity: Optional[float] = None
    unit: Optional[str] = None
    price: Optional[float] = None
    grade: Optional[str] = None          # 'A+', 'A', 'B', 'C'
    harvest_label: Optional[str] = None  # 'today' / 'yesterday' / ISO date
    harvest_offset: Optional[int] = None
    raw_text: str = ""
    dtmf: Optional[str] = None
    entities: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


def _has_any(text: str, words: list[str]) -> bool:
    return any(w in text for w in words)


def recognize_intent(text: str, language: str = "ta", dtmf: Optional[str] = None,
                    context: Optional[str] = None) -> IntentResult:
    """Top-level intent + entity extraction.

    ``text`` may be Tamil / English / Tanglish. ``language`` is the active
    IVR language ('ta' or 'en'). ``dtmf`` is the keypad digit if any.
    ``context`` is the current IVR state name (e.g. 'list_ask_qty'); when
    in a multi-step listing flow the recognizer will give preference to
    entity extraction rather than top-level intents.
    """
    raw = (text or "").strip().lower()
    res = IntentResult(raw_text=raw, dtmf=dtmf)

    # ----- DTMF paths ------------------------------------------------------
    if dtmf is not None:
        d = str(dtmf).strip()
        res.dtmf = d
        # numeric answers inside listing flow
        if context in ("list_ask_qty", "list_ask_price"):
            try:
                num = float(d) if "." in d else int(d)
                if context == "list_ask_qty":
                    res.quantity, res.unit = float(num), "kg"
                    res.intent = RAW_NUMBER
                    res.confidence = 0.95
                    return res
                else:
                    res.price = float(num)
                    res.intent = RAW_NUMBER
                    res.confidence = 0.95
                    return res
            except ValueError:
                pass
        if context == "list_ask_grade":
            g = parse_grade(d)
            if g:
                res.grade = g
                res.intent = RAW_NUMBER
                res.confidence = 0.95
                return res
        if context in ("list_confirm", "bulk_confirm", "price_hint_offer", "price_hint_recommend"):
            if d == "1":
                res.intent = CONFIRM; res.confidence = 0.95; return res
            if d == "2":
                # In price_hint_offer, DTMF 2 means "skip the AI hint, keep my price"
                # In list_confirm, DTMF 2 means "change my entry"
                # In other confirm contexts, treat 2 as a soft "no" (CHANGE)
                res.intent = CHANGE; res.confidence = 0.95; return res
            if d == "3":
                res.intent = CANCEL; res.confidence = 0.95; return res

        # main-menu top-level DTMF mapping
        if context in (None, "", "main_menu", "language_select", "help"):
            mapping = {
                "1": LIST_PRODUCE, "2": MARKET_PRICE, "3": ORDER_STATUS,
                "4": DELIVERY_STATUS, "5": BULK_ORDER, "6": EARNINGS,
                "7": HELP, "8": LANGUAGE_CHANGE, "0": MAIN_MENU, "9": HELP,
            }
            if d in mapping:
                res.intent = mapping[d]
                res.confidence = 0.99
                return res

    if not raw:
        res.intent = UNKNOWN
        return res

    # ----- global control intents (work in any state) ---------------------
    if _has_any(raw, _TAMIL_REPEAT_WORDS + _EN_REPEAT_WORDS):
        res.intent = REPEAT; res.confidence = 0.85; return res
    if _has_any(raw, _TAMIL_BACK_WORDS + _EN_BACK_WORDS):
        res.intent = GO_BACK; res.confidence = 0.85; return res
    if _has_any(raw, _TAMIL_MAIN_MENU_WORDS + _EN_MAIN_MENU_WORDS):
        res.intent = MAIN_MENU; res.confidence = 0.9; return res
    if _has_any(raw, _TAMIL_CANCEL_WORDS + _EN_CANCEL_WORDS):
        # Don't hijack raw 'no' in confirm context unless explicitly cancel
        if context in ("list_confirm", "bulk_confirm"):
            res.intent = CANCEL
        else:
            res.intent = CANCEL
        res.confidence = 0.85; return res
    if _has_any(raw, _TAMIL_CHANGE_WORDS + _EN_CHANGE_WORDS):
        res.intent = CHANGE; res.confidence = 0.8; return res
    if _has_any(raw, _TAMIL_CONFIRM_WORDS + _EN_CONFIRM_WORDS):
        res.intent = CONFIRM; res.confidence = 0.85; return res

    # ----- multi-step listing flow: extract entities ----------------------
    if context in ("list_ask_crop", "list_ask_qty", "list_ask_price",
                   "list_ask_harvest", "list_ask_grade"):
        # Try to extract the relevant entity first
        if context == "list_ask_crop":
            p = normalize_product(raw)
            if p:
                res.product = p
                res.intent = LIST_PRODUCE
                res.confidence = 0.95
                return res
        if context == "list_ask_qty":
            q, u = parse_quantity(raw)
            if q:
                res.quantity, res.unit = q, u
                res.intent = LIST_PRODUCE
                res.confidence = 0.95
                return res
        if context == "list_ask_price":
            p = parse_price(raw)
            if p:
                res.price = p
                res.intent = LIST_PRODUCE
                res.confidence = 0.95
                return res
        if context == "list_ask_harvest":
            lbl, off = parse_harvest_offset(raw)
            if lbl:
                res.harvest_label, res.harvest_offset = lbl, off
                res.intent = LIST_PRODUCE
                res.confidence = 0.95
                return res
        if context == "list_ask_grade":
            g = parse_grade(raw)
            if g:
                res.grade = g
                res.intent = LIST_PRODUCE
                res.confidence = 0.95
                return res
        # fall through to top-level recognition (user may have switched topics)

    # ----- multi-step market-price flow -----------------------------------
    if context == "price_ask_crop":
        p = normalize_product(raw)
        if p:
            res.product = p
            res.intent = MARKET_PRICE
            res.confidence = 0.95
            return res

    # ----- top-level intent classification --------------------------------
    # We try product extraction first because most Tamil/English/Tanglish
    # intents include the produce name ('tomato price enna').
    product = normalize_product(raw)
    qty, unit = parse_quantity(raw)
    price = parse_price(raw)

    has_price_word = _has_any(raw, _TAMIL_PRICE_WORDS + _EN_PRICE_WORDS)
    has_list_word = _has_any(raw, _TAMIL_LIST_WORDS + _EN_LIST_WORDS)
    has_order_word = _has_any(raw, _TAMIL_ORDER_WORDS + _EN_ORDER_WORDS)
    has_delivery_word = _has_any(raw, _TAMIL_DELIVERY_WORDS + _EN_DELIVERY_WORDS)
    has_bulk_word = _has_any(raw, _TAMIL_BULK_WORDS + _EN_BULK_WORDS)
    has_earn_word = _has_any(raw, _TAMIL_EARN_WORDS + _EN_EARN_WORDS)
    has_help_word = _has_any(raw, _TAMIL_HELP_WORDS + _EN_HELP_WORDS)

    # Priority: explicit help first (so 'help' isn't misinterpreted as list)
    if has_help_word and not has_price_word and not has_list_word:
        res.intent = HELP; res.confidence = 0.85
        return res

    # bulk 'bulk order for tomato' / '500 kg tomato bulk order'
    if has_bulk_word:
        res.product = product
        res.intent = BULK_ORDER; res.confidence = 0.85
        return res

    # price intent — even if no product, intent still classified
    if has_price_word:
        res.product = product
        res.intent = MARKET_PRICE; res.confidence = 0.9
        return res

    # delivery status
    if has_delivery_word:
        res.intent = DELIVERY_STATUS; res.confidence = 0.9
        return res

    # order status
    if has_order_word:
        res.intent = ORDER_STATUS; res.confidence = 0.9
        return res

    # earnings
    if has_earn_word:
        res.intent = EARNINGS; res.confidence = 0.9
        return res

    # listing intent: "i have 100 kg tomato" or "என்னிடம் தக்காளி இருக்கு"
    if (has_list_word or product or qty) and not has_order_word and not has_delivery_word:
        res.product = product or res.product
        res.quantity, res.unit = (qty, unit) if qty else (res.quantity, res.unit)
        res.price = price if price else res.price
        # Only emit LIST_PRODUCE if we found a product or quantity
        if product or qty:
            res.intent = LIST_PRODUCE
            res.confidence = 0.85 if product else 0.6
            return res

    # fallback: if there is a recognised product but no clear verb, treat as MARKET_PRICE
    if product:
        res.product = product
        res.intent = MARKET_PRICE
        res.confidence = 0.55
        return res

    # fallback: if only a number was said, return RAW_NUMBER (caller's context decides)
    if qty:
        res.quantity, res.unit = qty, unit
        res.intent = RAW_NUMBER
        res.confidence = 0.5
        return res

    res.intent = UNKNOWN
    return res
