"""IVR subsystem for FarmDirect.

A bilingual (தமிழ் / English) voice channel that lets farmers who cannot
use the smartphone app call a phone number and:

  * list produce (creates a real ``products`` row)
  * hear today's market price (re-uses ``ai.pricing`` + ``sales_history``)
  * check their orders / deliveries
  * see bulk-order opportunities (real ``quotes`` rows)
  * see their earnings (real ``payments`` rows)

Architecture:

  ┌───────────────────────────┐         ┌────────────────────────┐
  │  Telephony provider       │  HTTP   │  ivr_api blueprint     │
  │  (Twilio / Exotel / mock) │ ──────► │  /api/ivr/incoming &c. │
  └───────────────────────────┘         └──────────┬─────────────┘
                                                  │
                       ┌──────────────────────────┴──────────────┐
                       │  ivr.session.DialogManager              │
                       │  ivr.intents.recognize_intent            │
                       │  ivr.i18n.PROMPTS                        │
                       └──────────────────────────┬──────────────┘
                                                  │
                       ┌──────────────────────────┴──────────────┐
                       │  ivr.services — REAL backend actions     │
                       │  (re-uses existing db, ai, models)       │
                       └──────────────────────────────────────────┘

The IVR never owns a fake database — every action goes through the same
SQLite instance as the web app.
"""
from .i18n import PROMPTS, pick_prompt
from .products_dict import PRODUCT_SYNONYMS, normalize_product
from .numbers import parse_quantity, parse_price, parse_grade, parse_harvest_offset
from .intents import recognize_intent, IntentResult
from .session import DialogManager
from .services import (
    getFarmerByPhone,
    getFarmerProfile,
    authenticateIVRSession,
    getMarketPrice,
    createProduceListing,
    getFarmerOrders,
    getDeliveryStatus,
    getBulkOpportunities,
    acceptBulkOpportunity,
    getFarmerEarnings,
)

__all__ = [
    "PROMPTS", "pick_prompt",
    "PRODUCT_SYNONYMS", "normalize_product",
    "parse_quantity", "parse_price", "parse_grade", "parse_harvest_offset",
    "recognize_intent", "IntentResult",
    "DialogManager",
    "getFarmerByPhone", "getFarmerProfile", "authenticateIVRSession",
    "getMarketPrice", "createProduceListing", "getFarmerOrders",
    "getDeliveryStatus", "getBulkOpportunities", "acceptBulkOpportunity",
    "getFarmerEarnings",
]
