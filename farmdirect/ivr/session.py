"""IVR dialog manager — the state machine that drives a call.

Public surface:

    mgr = DialogManager(session_dict)
    step = mgr.process_input(text="100 kilo tomato", dtmf=None)
    #   step.prompt      -> list[str]  sentences the TTS should speak
    #   step.intent      -> str
    #   step.action      -> dict | None (e.g. {'name':'createProduceListing', ...})
    #   step.ended       -> bool
    #   step.session     -> updated session dict

The manager is stateless between requests: it loads the session state
(``current_menu`` + ``conversation_state`` JSON), processes one input,
mutates the session, and returns. Persistence is handled by the caller
(the API blueprint) via ``ivr_session_*`` helpers in this module.
"""
from __future__ import annotations
import json
import uuid
from dataclasses import dataclass, field
from datetime import date
from typing import Optional, Dict, Any, List

import db

from .i18n import PROMPTS, pick_prompt, WELCOME, MAIN_MENU, HELP_TEXT, ERRORS
from .intents import (recognize_intent, IntentResult,
                     LIST_PRODUCE, MARKET_PRICE, ORDER_STATUS, DELIVERY_STATUS,
                     BULK_ORDER, EARNINGS, HELP, LANGUAGE_CHANGE,
                     CANCEL, CONFIRM, CHANGE, REPEAT, GO_BACK, MAIN_MENU as MAIN_MENU_INTENT,
                     UNKNOWN, RAW_NUMBER)
from .numbers import parse_quantity, parse_price, parse_grade, parse_harvest_offset, harvest_label_to_iso, HARVEST_LABEL_TA, HARVEST_LABEL_EN
from .services import (getFarmerByPhone, getFarmerProfile, authenticateIVRSession,
                      getMarketPrice, createProduceListing,
                      getFarmerOrders, getDeliveryStatus,
                      getBulkOpportunities, acceptBulkOpportunity,
                      getFarmerEarnings, pretty_status)
from .products_dict import normalize_product


# --------------------------------------------------------------------- Step result
@dataclass
class StepResult:
    prompt: List[str] = field(default_factory=list)
    intent: str = UNKNOWN
    intent_payload: Dict[str, Any] = field(default_factory=dict)
    action: Optional[Dict[str, Any]] = None     # backend action executed (or None)
    ended: bool = False
    new_menu: str = ""
    failure_count: int = 0
    session: Optional[dict] = None

    def to_dict(self) -> dict:
        return {
            "prompt": self.prompt,
            "intent": self.intent,
            "intent_payload": self.intent_payload,
            "action": self.action,
            "ended": self.ended,
            "new_menu": self.new_menu,
            "failure_count": self.failure_count,
        }


# --------------------------------------------------------------------- Session helpers
def new_session(caller_number: str, call_id: Optional[str] = None) -> dict:
    """Create a new IVR session row and return it as a dict."""
    token = uuid.uuid4().hex
    sid = db.execute(
        "INSERT INTO ivr_sessions (session_token, call_id, caller_number, language, "
        "current_menu, conversation_state, auth_status, status) "
        "VALUES (?,?,?,?,?,?,'unverified','active')",
        (token, call_id, caller_number, "ta", "language_select", "{}"))
    return load_session(sid)


def load_session(session_id: int) -> Optional[dict]:
    row = db.query("SELECT * FROM ivr_sessions WHERE id=?", (session_id,), one=True)
    if not row:
        return None
    s = dict(row)
    try:
        s["conversation_state"] = json.loads(s["conversation_state"] or "{}")
    except json.JSONDecodeError:
        s["conversation_state"] = {}
    return s


def load_session_by_token(token: str) -> Optional[dict]:
    row = db.query("SELECT * FROM ivr_sessions WHERE session_token=?", (token,), one=True)
    if not row:
        return None
    s = dict(row)
    try:
        s["conversation_state"] = json.loads(s["conversation_state"] or "{}")
    except json.JSONDecodeError:
        s["conversation_state"] = {}
    return s


def save_session(s: dict):
    state = json.dumps(s.get("conversation_state", {}), ensure_ascii=False)
    db.execute(
        "UPDATE ivr_sessions SET language=?, current_menu=?, current_intent=?, "
        "conversation_state=?, auth_status=?, failure_count=?, status=?, "
        "user_id=?, farmer_id=?, updated_at=datetime('now','localtime') WHERE id=?",
        (s.get("language", "ta"), s.get("current_menu", "main_menu"),
         s.get("current_intent"), state,
         s.get("auth_status", "unverified"), s.get("failure_count", 0),
         s.get("status", "active"),
         s.get("user_id"), s.get("farmer_id"),
         s["id"]))


def log_event(session_id: int, event_type: str, raw_input: str = None,
              recognized_text: str = None, intent: str = None,
              intent_payload: dict = None, response_text: str = None,
              backend_action: str = None, backend_result: dict = None,
              error: str = None):
    db.execute(
        "INSERT INTO ivr_events (session_id, event_type, raw_input, recognized_text, "
        "intent, intent_payload, response_text, backend_action, backend_result, error) "
        "VALUES (?,?,?,?,?,?,?,?,?,?)",
        (session_id, event_type, raw_input, recognized_text, intent,
         json.dumps(intent_payload, ensure_ascii=False) if intent_payload else None,
         response_text,
         backend_action,
         json.dumps(backend_result, ensure_ascii=False) if backend_result else None,
         error))


def finalize_call_log(session: dict, intent: str, success: bool, had_error: bool,
                     duration_sec: int, transcript: list):
    # Counters live inside conversation_state JSON
    state = session.get("conversation_state", {})
    if isinstance(state, str):
        try:
            state = json.loads(state)
        except json.JSONDecodeError:
            state = {}
    counters = state.get("_counters", {})
    db.execute(
        "INSERT INTO ivr_call_logs (session_id, caller_number, user_id, farmer_name, "
        "language, intent, success, had_error, duration_sec, listings_created, "
        "bulk_accepted, price_requests, order_requests, earnings_requests, "
        "start_time, end_time, transcript) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (session["id"], session.get("caller_number"), session.get("user_id"),
         session.get("_farmer_name") or state.get("_farmer_name"),
         session.get("language"), intent,
         1 if success else 0, 1 if had_error else 0, duration_sec,
         counters.get("listings_created", 0), counters.get("bulk_accepted", 0),
         counters.get("price_requests", 0), counters.get("order_requests", 0),
         counters.get("earnings_requests", 0),
         session.get("created_at"),
         datetime_str_now(),
         json.dumps(transcript, ensure_ascii=False)))


def datetime_str_now() -> str:
    from datetime import datetime
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# --------------------------------------------------------------------- DialogManager
class DialogManager:
    """Stateful wrapper around a single session dict.

    Each ``process_input`` call mutates ``self.session`` in place and
    returns a :class:`StepResult`. The caller is responsible for
    persisting the session via :func:`save_session`.
    """

    def __init__(self, session: dict):
        self.session = session
        self.lang = session.get("language", "ta")
        self.state = session.get("conversation_state", {})
        self.menu = session.get("current_menu", "language_select")

    # -- helpers -------------------------------------------------------
    def _say(self, *keys) -> List[str]:
        out = []
        for k in keys:
            if k in (WELCOME, MAIN_MENU, HELP_TEXT):
                out.extend(self._collection(k))
            else:
                txt = pick_prompt(k, self.lang, **self.state.get("fmt", {}))
                if txt:
                    out.append(txt)
        return out

    def _collection(self, coll) -> List[str]:
        if coll is WELCOME:
            return list(WELCOME[self.lang])
        if coll is MAIN_MENU:
            return list(MAIN_MENU[self.lang])
        if coll is HELP_TEXT:
            return list(HELP_TEXT[self.lang])
        return []

    def _reset_failure(self):
        self.session["failure_count"] = 0

    def _bump_failure(self) -> int:
        self.session["failure_count"] = self.session.get("failure_count", 0) + 1
        return self.session["failure_count"]

    def _failure_prompt(self) -> List[str]:
        n = self.session.get("failure_count", 0)
        if n <= 1:
            return [pick_prompt("speech_unclear_1", self.lang)]
        if n == 2:
            return [pick_prompt("speech_unclear_2", self.lang)]
        return [pick_prompt("speech_unclear_3", self.lang)]

    def _incr(self, key):
        # Persist counters inside conversation_state so they survive between
        # requests (the session dict itself is not persisted as a whole).
        self.state.setdefault("_counters", {})
        self.state["_counters"][key] = self.state["_counters"].get(key, 0) + 1

    def _fresh_dialog_state(self, seed: Optional[dict] = None) -> dict:
        """Return a new dialog-state dict that PRESERVES the call counters.

        Always use this instead of ``self.state = {...}`` from inside a
        handler, otherwise per-call counters (listings_created, price_requests,
        …) get lost between turns.
        """
        counters = self.state.get("_counters", {})
        farmer_name = self.state.get("_farmer_name")
        new_state = dict(seed or {})
        new_state["_counters"] = counters
        if farmer_name:
            new_state["_farmer_name"] = farmer_name
        return new_state

    # -- main entry ---------------------------------------------------
    def process_input(self, text: Optional[str] = None,
                     dtmf: Optional[str] = None) -> StepResult:
        # 1) try to recognize intent from text and/or DTMF
        ir = recognize_intent(text, self.lang, dtmf=dtmf, context=self.menu)
        result = StepResult(intent=ir.intent, intent_payload=ir.to_dict(),
                          session=self.session)
        # 2) dispatch by current menu
        if self.menu == "language_select":
            self._handle_language_select(ir, text, dtmf, result)
        else:
            self._handle_menu(ir, text, dtmf, result)

        # 3) persist state back into session dict so save_session stores it
        self.session["conversation_state"] = self.state
        self.session["language"] = self.lang
        self.session["current_intent"] = ir.intent if ir.intent != UNKNOWN else self.session.get("current_intent")

        result.new_menu = self.session.get("current_menu", "")
        result.failure_count = self.session.get("failure_count", 0)
        save_session(self.session)
        return result

    # -- language select ----------------------------------------------
    def _handle_language_select(self, ir, text, dtmf, result):
        if ir.intent == LANGUAGE_CHANGE or dtmf in ("1", "2"):
            self.lang = "ta" if (dtmf == "1" or ir.intent == LANGUAGE_CHANGE and "tamil" in (text or "").lower()) else "en" if dtmf == "2" else "ta"
            # actually use a clearer rule
            if dtmf == "2":
                self.lang = "en"
            elif dtmf == "1":
                self.lang = "ta"
            elif text and any(w in (text or "").lower() for w in ("english", "2", "இரண்டு")):
                self.lang = "en"
            self.session["language"] = self.lang
            self._reset_failure()
            self.session["current_menu"] = "main_menu"
            # caller lookup happens after language is set so welcome can be personalised
            self._lookup_farmer()
            if self.session.get("farmer_id"):
                result.prompt = [
                    f"{'வணக்கம்' if self.lang == 'ta' else 'Welcome'}, {self.session.get('_farmer_name', '')}.",
                    *MAIN_MENU[self.lang],
                ]
            else:
                result.prompt = [
                    ERRORS["no_account"][self.lang],
                    *MAIN_MENU[self.lang],
                ]
            return
        # invalid
        n = self._bump_failure()
        result.prompt = self._failure_prompt()

    # -- lookup farmer by phone --------------------------------------
    def _lookup_farmer(self):
        phone = self.session.get("caller_number", "")
        if not phone:
            return
        f = getFarmerByPhone(phone)
        if f:
            self.session["user_id"] = f["id"]
            self.session["farmer_id"] = f["id"]
            self.session["_farmer_name"] = (f.get("farm_name") or f["name"] or "Farmer")
            # also stash in conversation_state so it survives save/load
            self.state.setdefault("_farmer_name", self.session["_farmer_name"])
            self.session["auth_status"] = "verified"

    # -- main menu ----------------------------------------------------
    def _handle_menu(self, ir, text, dtmf, result):
        # Global control intents — work in any state
        if ir.intent == REPEAT:
            self._reset_failure()
            last_prompt = self.state.get("last_prompt")
            result.prompt = [last_prompt] if last_prompt else [pick_prompt("acknowledged", self.lang)]
            return
        if ir.intent == GO_BACK:
            self._reset_failure()
            prev = self.state.get("prev_menu", "main_menu")
            self.session["current_menu"] = prev
            self.menu = prev
            self.state["fmt"] = {}
            if prev == "main_menu":
                result.prompt = [pick_prompt("returning_to_main", self.lang), *MAIN_MENU[self.lang]]
            else:
                result.prompt = self._say(prev)
            return
        if ir.intent == MAIN_MENU_INTENT:
            self._reset_failure()
            self.session["current_menu"] = "main_menu"
            # Preserve counters; only clear dialog-specific state
            for k in ("listing", "fmt", "bulk_opp", "market_low",
                     "market_high", "market_suggested", "last_prompt", "prev_menu"):
                self.state.pop(k, None)
            result.prompt = [pick_prompt("returning_to_main", self.lang), *MAIN_MENU[self.lang]]
            return
        if ir.intent == CANCEL and self.menu != "main_menu":
            self._reset_failure()
            self.session["current_menu"] = "main_menu"
            for k in ("listing", "fmt", "bulk_opp", "market_low",
                     "market_high", "market_suggested", "last_prompt", "prev_menu"):
                self.state.pop(k, None)
            result.prompt = [pick_prompt("list_cancelled", self.lang),
                            pick_prompt("returning_to_main", self.lang),
                            *MAIN_MENU[self.lang]]
            return

        # Dispatch on current menu
        handlers = {
            "main_menu": self._h_main_menu,
            "list_ask_crop": self._h_list_ask_crop,
            "list_ask_qty": self._h_list_ask_qty,
            "list_ask_price": self._h_list_ask_price,
            "list_ask_harvest": self._h_list_ask_harvest,
            "list_ask_grade": self._h_list_ask_grade,
            "list_confirm": self._h_list_confirm,
            "price_hint_offer": self._h_price_hint_offer,
            "price_hint_recommend": self._h_price_hint_recommend,
            "price_ask_crop": self._h_price_ask_crop,
            "price_report_done": self._h_main_menu,
            "order_report_done": self._h_main_menu,
            "delivery_report_done": self._h_main_menu,
            "bulk_confirm": self._h_bulk_confirm,
            "earnings_report_done": self._h_main_menu,
            "help_done": self._h_main_menu,
        }
        handler = handlers.get(self.menu, self._h_main_menu)
        handler(ir, text, dtmf, result)

    # -- main menu handler -------------------------------------------
    def _h_main_menu(self, ir, text, dtmf, result):
        self._reset_failure()
        # If intent is still UNKNOWN, re-prompt main menu
        if ir.intent == UNKNOWN and ir.dtmf is None and not ir.raw_text:
            result.prompt = list(MAIN_MENU[self.lang])
            return
        if ir.intent == LIST_PRODUCE or dtmf == "1":
            # Fast-track the listing flow if the user already named a crop
            # and/or quantity in the same utterance ("I have 100 kilos of tomato").
            self.state = self._fresh_dialog_state({"listing": {}})
            self.session["current_menu"] = "list_ask_crop"
            if ir.product or ir.quantity:
                # Delegate to the crop handler so it advances to qty/price.
                self._h_list_ask_crop(ir, text, dtmf, result)
            else:
                result.prompt = [pick_prompt("list_ask_crop", self.lang)]
        elif ir.intent == MARKET_PRICE or dtmf == "2":
            # Fast-track market price flow if user already named the crop.
            self.state = self._fresh_dialog_state()
            self.session["current_menu"] = "price_ask_crop"
            if ir.product:
                self._h_price_ask_crop(ir, text, dtmf, result)
            else:
                result.prompt = [pick_prompt("price_ask_crop", self.lang)]
        elif ir.intent == ORDER_STATUS or dtmf == "3":
            self._handle_order_status(result)
        elif ir.intent == DELIVERY_STATUS or dtmf == "4":
            self._handle_delivery_status(result)
        elif ir.intent == BULK_ORDER or dtmf == "5":
            self._handle_bulk_query(result)
        elif ir.intent == EARNINGS or dtmf == "6":
            self._handle_earnings(result)
        elif ir.intent == HELP or dtmf == "7":
            result.prompt = list(HELP_TEXT[self.lang])
            self.session["current_menu"] = "main_menu"
        elif ir.intent == LANGUAGE_CHANGE or dtmf == "8":
            self.session["current_menu"] = "language_select"
            result.prompt = list(WELCOME[self.lang])
        else:
            result.prompt = [ERRORS["invalid_choice"][self.lang], *MAIN_MENU[self.lang]]

    # -- listing flow -------------------------------------------------
    def _h_list_ask_crop(self, ir, text, dtmf, result):
        if ir.intent == LIST_PRODUCE and ir.product:
            self._reset_failure()
            self.state["listing"]["crop"] = ir.product
            self.state["listing"]["quantity"] = ir.quantity
            self.state["listing"]["unit"] = ir.unit or "kg"
            self.session["current_menu"] = "list_ask_qty" if not ir.quantity else "list_ask_price"
            if ir.quantity:
                result.prompt = [pick_prompt("list_ask_price", self.lang)]
            else:
                result.prompt = [pick_prompt("list_ask_qty", self.lang)]
        elif ir.product:
            self._reset_failure()
            self.state["listing"]["crop"] = ir.product
            self.session["current_menu"] = "list_ask_qty"
            result.prompt = [pick_prompt("list_ask_qty", self.lang)]
        else:
            n = self._bump_failure()
            if n >= 3:
                # give DTMF crop menu
                crops = ["Tomato", "Onion", "Potato", "Banana", "Mango"]
                options = "; ".join(f"{crops[i]} {i+1}" for i in range(len(crops)))
                result.prompt = [pick_prompt("product_unknown", self.lang),
                               f"{options}.",
                               pick_prompt("speech_unclear_3", self.lang)]
            else:
                result.prompt = [pick_prompt("product_unknown", self.lang),
                               pick_prompt("list_ask_crop", self.lang)]

    def _h_list_ask_qty(self, ir, text, dtmf, result):
        qty = ir.quantity
        if qty:
            self._reset_failure()
            self.state["listing"]["quantity"] = qty
            self.state["listing"]["unit"] = ir.unit or "kg"
            self.session["current_menu"] = "list_ask_price"
            result.prompt = [pick_prompt("list_ask_price", self.lang)]
        else:
            n = self._bump_failure()
            if n >= 3:
                result.prompt = [pick_prompt("quantity_missing", self.lang),
                               pick_prompt("speech_unclear_3", self.lang)]
            else:
                result.prompt = [pick_prompt("quantity_missing", self.lang)]

    def _h_list_ask_price(self, ir, text, dtmf, result):
        price = ir.price
        if price is not None:
            self._reset_failure()
            self.state["listing"]["price"] = price
            self.session["current_menu"] = "list_ask_harvest"
            # AI price hint: fetch market range and offer comparison
            try:
                mp = getMarketPrice(self.state["listing"]["crop"], None)
                self.state["market_low"] = mp["low"]
                self.state["market_high"] = mp["high"]
                self.state["market_suggested"] = mp["suggested"]
                if price < mp["low"] * 0.95 or price > mp["high"] * 1.1:
                    self.session["current_menu"] = "price_hint_offer"
                    result.prompt = [pick_prompt("price_hint_offer", self.lang,
                                                price=int(price), low=int(mp["low"]),
                                                high=int(mp["high"]))]
                else:
                    result.prompt = [pick_prompt("list_ask_harvest", self.lang)]
            except Exception:
                result.prompt = [pick_prompt("list_ask_harvest", self.lang)]
        else:
            n = self._bump_failure()
            if n >= 3:
                result.prompt = [pick_prompt("price_missing", self.lang),
                               pick_prompt("speech_unclear_3", self.lang)]
            else:
                result.prompt = [pick_prompt("price_missing", self.lang)]

    def _h_price_hint_offer(self, ir, text, dtmf, result):
        if ir.intent == CONFIRM or dtmf == "1":
            self._reset_failure()
            self.session["current_menu"] = "price_hint_recommend"
            suggested = self.state.get("market_suggested", 0)
            result.prompt = [pick_prompt("price_hint_recommend", self.lang, suggested=int(suggested))]
        else:
            self._reset_failure()
            self.session["current_menu"] = "list_ask_harvest"
            # If the user spoke a harvest date while declining the hint,
            # capture it now so they don't have to repeat it.
            if ir.harvest_label:
                self.state["listing"]["harvest_label"] = ir.harvest_label
                self.state["listing"]["harvest_offset"] = ir.harvest_offset
                self.session["current_menu"] = "list_ask_grade"
                result.prompt = [pick_prompt("price_hint_skipped", self.lang),
                               pick_prompt("list_ask_grade", self.lang)]
            else:
                result.prompt = [pick_prompt("price_hint_skipped", self.lang),
                               pick_prompt("list_ask_harvest", self.lang)]

    def _h_price_hint_recommend(self, ir, text, dtmf, result):
        if ir.intent == CONFIRM or dtmf == "1":
            self.state["listing"]["price"] = self.state.get("market_suggested", self.state["listing"]["price"])
        # either way proceed
        self._reset_failure()
        self.session["current_menu"] = "list_ask_harvest"
        # If the user spoke a harvest date while declining the recommendation,
        # capture it now so they don't have to repeat it.
        if ir.harvest_label:
            self.state["listing"]["harvest_label"] = ir.harvest_label
            self.state["listing"]["harvest_offset"] = ir.harvest_offset
            self.session["current_menu"] = "list_ask_grade"
            result.prompt = [pick_prompt("list_ask_grade", self.lang)]
        else:
            result.prompt = [pick_prompt("list_ask_harvest", self.lang)]

    def _h_list_ask_harvest(self, ir, text, dtmf, result):
        if ir.harvest_label:
            self._reset_failure()
            self.state["listing"]["harvest_label"] = ir.harvest_label
            self.state["listing"]["harvest_offset"] = ir.harvest_offset
            self.session["current_menu"] = "list_ask_grade"
            result.prompt = [pick_prompt("list_ask_grade", self.lang)]
        else:
            n = self._bump_failure()
            if n >= 3:
                # default to today
                self.state["listing"]["harvest_label"] = "today"
                self.state["listing"]["harvest_offset"] = 0
                self.session["current_menu"] = "list_ask_grade"
                result.prompt = [pick_prompt("list_ask_grade", self.lang)]
            else:
                result.prompt = [pick_prompt("list_ask_harvest", self.lang)]

    def _h_list_ask_grade(self, ir, text, dtmf, result):
        g = ir.grade
        if g is None and dtmf in ("1", "2", "3"):
            g = parse_grade(dtmf)
        if g:
            self._reset_failure()
            self.state["listing"]["grade"] = g
            self.session["current_menu"] = "list_confirm"
            harvest_label = self.state["listing"].get("harvest_label", "today")
            offset = self.state["listing"].get("harvest_offset")
            if offset is not None:
                if self.lang == "ta":
                    hl = HARVEST_LABEL_TA.get(harvest_label, harvest_label)
                else:
                    hl = HARVEST_LABEL_EN.get(harvest_label, harvest_label)
            else:
                hl = harvest_label
            self.state["fmt"] = dict(
                qty=int(self.state["listing"]["quantity"]),
                crop=self.state["listing"]["crop"],
                price=int(self.state["listing"]["price"]),
                grade=g,
                harvest_label=hl,
            )
            summary = pick_prompt("list_summary", self.lang, **self.state["fmt"])
            confirm_opts = pick_prompt("list_confirm_options", self.lang)
            result.prompt = [summary, confirm_opts]
        else:
            n = self._bump_failure()
            if n >= 3:
                result.prompt = [pick_prompt("invalid_choice", self.lang),
                               pick_prompt("speech_unclear_3", self.lang)]
            else:
                result.prompt = [pick_prompt("list_ask_grade", self.lang)]

    def _h_list_confirm(self, ir, text, dtmf, result):
        if ir.intent == CONFIRM or dtmf == "1":
            self._reset_failure()
            farmer_id = self.session.get("farmer_id")
            if not farmer_id:
                # no account — fallback to admin so demo works even unauthed
                admin = db.query("SELECT id FROM users WHERE role='admin' LIMIT 1", one=True)
                farmer_id = admin["id"] if admin else 1
                self.session["farmer_id"] = farmer_id
                self.session["user_id"] = farmer_id
            try:
                lst = self.state["listing"]
                harvest_iso = harvest_label_to_iso(lst.get("harvest_label"),
                                                  lst.get("harvest_offset"))
                grade = lst.get("grade") or "A"
                out = createProduceListing(
                    farmer_id,
                    lst["crop"], float(lst["quantity"]),
                    float(lst["price"]), grade, harvest_iso)
                self._incr("listings_created")
                result.action = {"name": "createProduceListing", "result": out}
                result.prompt = [pick_prompt("list_success", self.lang),
                               pick_prompt("returning_to_main", self.lang),
                               *MAIN_MENU[self.lang]]
                self.session["current_menu"] = "main_menu"
                # Clear listing-specific state but PRESERVE counters
                self.state.pop("listing", None)
                self.state.pop("fmt", None)
                self.state.pop("market_low", None)
                self.state.pop("market_high", None)
                self.state.pop("market_suggested", None)
            except Exception as e:
                result.prompt = [ERRORS["db_unavailable"][self.lang]]
                result.action = {"name": "createProduceListing", "error": str(e)}
        elif ir.intent == CHANGE or dtmf == "2":
            self._reset_failure()
            self.session["current_menu"] = "list_ask_crop"
            self.state.pop("listing", None)
            self.state["listing"] = {}
            result.prompt = [pick_prompt("acknowledged", self.lang),
                           pick_prompt("list_ask_crop", self.lang)]
        else:  # cancel / 3
            self._reset_failure()
            self.session["current_menu"] = "main_menu"
            for k in ("listing", "fmt"):
                self.state.pop(k, None)
            result.prompt = [pick_prompt("list_cancelled", self.lang),
                           *MAIN_MENU[self.lang]]

    # -- market price flow --------------------------------------------
    def _h_price_ask_crop(self, ir, text, dtmf, result):
        if ir.product:
            self._reset_failure()
            try:
                mp = getMarketPrice(ir.product, None)
                self._incr("price_requests")
                result.prompt = [
                    pick_prompt("price_report", self.lang,
                                crop=mp["crop"], low=int(mp["low"]),
                                high=int(mp["high"]), avg=int(mp["avg"]),
                                updated=mp["updated"]),
                    pick_prompt("demo_note", self.lang) if mp["demo_data"] else "",
                    pick_prompt("returning_to_main", self.lang),
                    *MAIN_MENU[self.lang],
                ]
                result.prompt = [p for p in result.prompt if p]
                result.action = {"name": "getMarketPrice", "result": mp}
                self.session["current_menu"] = "main_menu"
            except Exception as e:
                result.prompt = [ERRORS["db_unavailable"][self.lang]]
                result.action = {"name": "getMarketPrice", "error": str(e)}
        else:
            n = self._bump_failure()
            if n >= 3:
                result.prompt = [pick_prompt("product_unknown", self.lang),
                               pick_prompt("speech_unclear_3", self.lang)]
            else:
                result.prompt = [pick_prompt("product_unknown", self.lang),
                               pick_prompt("price_ask_crop", self.lang)]

    # -- order status ------------------------------------------------
    def _handle_order_status(self, result):
        fid = self.session.get("farmer_id")
        if not fid:
            result.prompt = [ERRORS["no_account"][self.lang], *MAIN_MENU[self.lang]]
            self.session["current_menu"] = "main_menu"
            return
        orders = getFarmerOrders(fid, 5)
        self._incr("order_requests")
        if not orders:
            result.prompt = [ERRORS["no_orders"][self.lang], *MAIN_MENU[self.lang]]
            self.session["current_menu"] = "main_menu"
            return
        o = orders[0]
        status_txt = pretty_status(o["status"], self.lang)
        text = pick_prompt("order_latest", self.lang, code=o["order_code"], status=status_txt)
        extra = ""
        if o.get("buyer_name"):
            extra = (f"வாடிக்கையாளர்: {o['buyer_name']}." if self.lang == "ta"
                   else f"Buyer: {o['buyer_name']}.")
        more = pick_prompt("order_more", self.lang)
        result.prompt = [text, extra, more, *MAIN_MENU[self.lang]]
        result.prompt = [p for p in result.prompt if p]
        result.action = {"name": "getFarmerOrders", "result": orders}
        self.session["current_menu"] = "main_menu"

    # -- delivery status ---------------------------------------------
    def _handle_delivery_status(self, result):
        fid = self.session.get("farmer_id")
        if not fid:
            result.prompt = [ERRORS["no_account"][self.lang], *MAIN_MENU[self.lang]]
            self.session["current_menu"] = "main_menu"
            return
        dels = getDeliveryStatus(fid, 1)
        self._incr("order_requests")
        if not dels:
            result.prompt = [ERRORS["no_orders"][self.lang], *MAIN_MENU[self.lang]]
            self.session["current_menu"] = "main_menu"
            return
        d = dels[0]
        status_txt = pretty_status(d["status"], self.lang)
        extra = ""
        if d["status"] in ("picked_up", "in_transit"):
            eta = d["eta_minutes"]
            if self.lang == "ta":
                extra = f"எதிர்பார்க்கப்படும் நேரம் சுமார் {eta} நிமிடம். டிரைவர்: {d['driver_name']}."
            else:
                extra = f"Estimated time about {eta} minutes. Driver: {d['driver_name']}."
        elif d["status"] == "delivered":
            extra = (f"டெலிவரி முடிந்தது." if self.lang == "ta" else "Delivery completed.")
        text = pick_prompt("delivery_report", self.lang, code=d["order_code"], status=status_txt, extra=extra)
        result.prompt = [text, pick_prompt("returning_to_main", self.lang), *MAIN_MENU[self.lang]]
        result.prompt = [p for p in result.prompt if p]
        result.action = {"name": "getDeliveryStatus", "result": dels}
        self.session["current_menu"] = "main_menu"

    # -- bulk orders --------------------------------------------------
    def _handle_bulk_query(self, result):
        fid = self.session.get("farmer_id")
        if not fid:
            result.prompt = [ERRORS["no_account"][self.lang], *MAIN_MENU[self.lang]]
            self.session["current_menu"] = "main_menu"
            return
        opps = getBulkOpportunities(fid, 1)
        if not opps:
            result.prompt = [ERRORS["no_bulk"][self.lang], *MAIN_MENU[self.lang]]
            self.session["current_menu"] = "main_menu"
            return
        opp = opps[0]
        self.state["bulk_opp"] = opp
        text = pick_prompt("bulk_report", self.lang,
                          qty=int(opp["quantity_kg"]), crop=opp["crop"],
                          avail=int(opp["can_supply_kg"]))
        result.prompt = [text]
        result.action = {"name": "getBulkOpportunities", "result": opps}
        self.session["current_menu"] = "bulk_confirm"

    def _h_bulk_confirm(self, ir, text, dtmf, result):
        opp = self.state.get("bulk_opp")
        if not opp:
            self.session["current_menu"] = "main_menu"
            result.prompt = [*MAIN_MENU[self.lang]]
            return
        if ir.intent == CONFIRM or dtmf == "1":
            self._reset_failure()
            out = acceptBulkOpportunity(self.session["farmer_id"], opp["quote_id"],
                                        opp["can_supply_kg"])
            self._incr("bulk_accepted")
            result.action = {"name": "acceptBulkOpportunity", "result": out}
            if out.get("ok"):
                result.prompt = [pick_prompt("bulk_accept_ok", self.lang),
                               pick_prompt("returning_to_main", self.lang),
                               *MAIN_MENU[self.lang]]
            else:
                result.prompt = [ERRORS["db_unavailable"][self.lang], *MAIN_MENU[self.lang]]
            self.session["current_menu"] = "main_menu"
        else:
            self._reset_failure()
            result.prompt = [pick_prompt("bulk_declined", self.lang),
                           *MAIN_MENU[self.lang]]
            self.session["current_menu"] = "main_menu"

    # -- earnings -----------------------------------------------------
    def _handle_earnings(self, result):
        fid = self.session.get("farmer_id")
        if not fid:
            result.prompt = [ERRORS["no_account"][self.lang], *MAIN_MENU[self.lang]]
            self.session["current_menu"] = "main_menu"
            return
        self._incr("earnings_requests")
        e = getFarmerEarnings(fid)
        result.prompt = [pick_prompt("earnings_report", self.lang,
                                    today=int(e["today"]), week=int(e["week"]),
                                    month=int(e["month"]), paid=int(e["paid"]),
                                    pending=int(e["pending"])),
                       pick_prompt("returning_to_main", self.lang),
                       *MAIN_MENU[self.lang]]
        result.action = {"name": "getFarmerEarnings", "result": e}
        self.session["current_menu"] = "main_menu"
