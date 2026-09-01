# 📞 IVR — Bilingual Voice Channel for Uzhavar / FarmDirect

A farmer who is not comfortable using the smartphone app can now **call a
phone number** and use the entire marketplace through a Tamil/English
voice menu. The IVR is **not** a mockup — it writes to the same SQLite
tables as the web app (products, orders, payments, quotes) and reads
from the same AI services (`ai.pricing`, `ai.forecasting`,
`sales_history`).

## Highlights

- **Bilingual** prompts: தமிழ் + English (selected at call start, remembered
  for the whole session).
- **Two input modes**: DTMF keypad (1–9, 0, *, #) AND natural speech
  (Tamil / English / Tanglish). The simulator uses the browser's
  SpeechSynthesis + SpeechRecognition APIs.
- **Rule-based intent recognizer** that runs 100% offline — no external
  NLU API key required (matches the project's offline-first philosophy).
- **AI price recommendation** during the listing flow — the IVR asks
  for the price, optionally compares it to the market range, and
  surfaces the existing `recommend_price` engine's suggestion. The
  farmer always stays in control.
- **Persistent session**: every call has a session row that remembers
  language, current menu, conversation state and per-call counters.
- **Real telephony-ready**: the `/api/ivr/*` endpoints accept both the
  simulator's JSON payload and Twilio's form-encoded webhook fields
  (From, Digits, SpeechResult, CallSid, …). Switch `IVR_MODE=production`
  + set Twilio creds and point Twilio's voice webhook to
  `/api/ivr/incoming`.
- **IVR simulator** inside the app at `/ivr/simulator` — phone-frame UI
  with Tamil/English selector, mic button, DTMF keypad, transcript,
  AI intent panel, backend action panel.
- **Admin IVR dashboard** at `/admin/ivr` — KPIs, Tamil vs English
  pie chart, top intents, success/fail chart, recent call list with
  per-call detail page (transcript + event timeline + final session
  state).

## Architecture

```
┌────────────────────┐         ┌───────────────────────┐
│  Real phone (PBX)  │  HTTP   │  /api/ivr/incoming   │
│  Twilio / Exotel   │ ──────► │  /api/ivr/input      │
└────────────────────┘         │  /api/ivr/callback   │
                                │  /api/ivr/hangup     │
┌────────────────────┐         └──────────┬──────────┘
│  In-app Simulator  │  JSON              │
│  /ivr/simulator    │ ──────────────────► │
└────────────────────┘                     ▼
                          ┌──────────────────────────────┐
                          │  ivr.session.DialogManager    │
                          │  ivr.intents.recognize_intent │
                          │  ivr.i18n.PROMPTS             │
                          └─────────────┬────────────────┘
                                        ▼
                          ┌──────────────────────────────┐
                          │  ivr.services                │
                          │  (REAL backend actions)      │
                          │  • createProduceListing      │
                          │  • getMarketPrice            │
                          │  • getFarmerOrders           │
                          │  • getBulkOpportunities       │
                          │  • acceptBulkOpportunity     │
                          │  • getFarmerEarnings         │
                          └─────────────┬────────────────┘
                                        ▼
                          ┌──────────────────────────────┐
                          │  Same SQLite tables as web:  │
                          │  users, products, orders,   │
                          │  payments, deliveries,      │
                          │  quotes, sales_history, …   │
                          └──────────────────────────────┘
```

The IVR never owns a fake database. Every action goes through the same
SQLite instance as the web app.

## Files added / changed

### New Python modules
| File | Purpose |
|------|---------|
| `ivr/__init__.py` | Public package surface |
| `ivr/i18n.py` | Tamil/English prompt strings (welcome, main menu, errors, all flow prompts) |
| `ivr/products_dict.py` | Tamil / English / Tanglish → canonical crop name (Tomato/தக்காளி/thakkali) |
| `ivr/numbers.py` | Spoken quantity / price / grade / harvest-date parser (Tamil + English number words) |
| `ivr/intents.py` | Rule-based intent recognizer (LIST_PRODUCE, MARKET_PRICE, ORDER_STATUS, …) + entity extraction |
| `ivr/providers.py` | Telephony / TTS / STT / Intent provider abstractions (Mock + Production stubs) |
| `ivr/services.py` | Backend bridge: `getFarmerByPhone`, `getMarketPrice`, `createProduceListing`, … |
| `ivr/session.py` | `DialogManager` state machine + session persistence + call-log finalizer |
| `ivr_api.py` | Flask blueprint: `/api/ivr/incoming`, `/input`, `/session`, `/callback`, `/hangup`, `/mode`, `/admin/stats`, `/admin/calls`, `/admin/call/<id>` |

### New templates / static
| File | Purpose |
|------|---------|
| `templates/ivr/simulator.html` | Phone-frame UI: language selector, mic, keypad, transcript, intent + action panels, caller pick-list, quick demo scripts |
| `templates/ivr/admin.html` | IVR admin dashboard: KPIs, charts (Tamil vs English, top intents, success/fail), recent calls table |
| `templates/ivr/call_detail.html` | Per-call detail: summary, transcript, event timeline, final session state |
| `static/css/ivr.css` | Phone frame, keypad, transcript bubbles, caller cards, mode pill |
| `static/js/ivr_simulator.js` | Web Speech API TTS+STT wrapper, fetch() to /api/ivr/*, quick demo scripts |

### Files modified
| File | Change |
|------|--------|
| `schema.sql` | Added 3 IVR tables (`ivr_sessions`, `ivr_call_logs`, `ivr_events`) + indexes |
| `app_factory.py` | Registered `ivr_api` blueprint at `/api` |
| `views.py` | New routes: `/ivr/simulator`, `/admin/ivr`, `/admin/ivr/call/<id>` |
| `seed.py` | Demo farmers/FPOs/consumers/buyers/admin now have fixed phone numbers (so the simulator can dial them) |
| `templates/base.html` | Added "IVR Voice" link in navbar (visible to all logged-in users) and "IVR Calls" link in admin navbar |
| `templates/farmer/dashboard.html` | Added "Voice / IVR" link in the farmer sidebar |
| `templates/admin/dashboard.html` | Added "IVR" tab with simulator launch + production config snippet |
| `static/css/style.css` | Added `.ivr-config-snippet` styling for the admin config block |

### Database changes
3 new tables (added to `schema.sql`, created automatically on first run):
- `ivr_sessions(id, session_token, call_id, caller_number, user_id, farmer_id, language, current_menu, current_intent, conversation_state, auth_status, failure_count, status, created_at, updated_at)`
- `ivr_call_logs(id, session_id, caller_number, user_id, farmer_name, language, intent, success, had_error, duration_sec, listings_created, bulk_accepted, price_requests, order_requests, earnings_requests, start_time, end_time, transcript)`
- `ivr_events(id, session_id, ts, event_type, raw_input, recognized_text, intent, intent_payload, response_text, backend_action, backend_result, error)`

The IVR does NOT add columns to existing tables. It re-uses
`users.phone` for caller→farmer matching and `products/orders/payments/
quotes/quote_responses` for all real actions.

## API endpoints

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/api/ivr/incoming` | Start a new call (simulator: JSON `caller_number`; Twilio: form-encoded `From`/`CallSid`) |
| POST | `/api/ivr/input` | Submit one turn (JSON `{session_token, input?, dtmf?}` or Twilio `Digits`/`SpeechResult`) |
| GET  | `/api/ivr/session?session_token=` | Get current session state + last event (used by the simulator to resume) |
| POST | `/api/ivr/callback` | Telephony status callback (Twilio `CallStatus=completed` etc.) |
| POST | `/api/ivr/hangup` | Simulator-driven hangup → finalizes call log |
| GET  | `/api/ivr/mode` | Active provider mode (mock / production + provider class names) |
| GET  | `/api/ivr/admin/stats` | Admin KPIs (admin-only) |
| GET  | `/api/ivr/admin/calls` | Recent calls list (admin-only) |
| GET  | `/api/ivr/admin/call/<id>` | Single call detail with events + transcript (admin-only) |

## Environment variables

The IVR runs out-of-the-box in mock mode (no env vars required). For
production telephony:

| Variable | Default | Purpose |
|----------|---------|---------|
| `IVR_MODE` | `mock` | `mock` = in-app simulator; `production` = real telephony |
| `IVR_TELEPHONY_PROVIDER` | `twilio` | Production telephony adapter |
| `IVR_TWILIO_ACCOUNT_SID` | — | Twilio Account SID |
| `IVR_TWILIO_AUTH_TOKEN` | — | Twilio Auth Token |
| `IVR_TWILIO_NUMBER` | — | The phone number callers dial (E.164) |
| `IVR_PUBLIC_BASE_URL` | — | Public https URL of this Flask app (so Twilio can POST back) |
| `IVR_TTS_PROVIDER` | — | `elevenlabs` (or any HTTP TTS) in production |
| `IVR_TTS_API_KEY` | — | TTS provider API key |
| `IVR_TTS_VOICE_ID` | — | TTS voice id |
| `IVR_STT_PROVIDER` | — | `google` for Google Cloud Speech |
| `IVR_GOOGLE_CREDS_JSON` | — | Google Cloud service-account JSON |
| `IVR_INTENT_PROVIDER` | — | `dialogflow` for Dialogflow ES |
| `IVR_DIALOGFLOW_PROJECT` | — | Dialogflow project id |

**No credentials are stored in source code.** The Mock providers are
the default and the production providers raise `RuntimeError` if the
required env vars are missing, so the simulator always works.

## How to run

```bash
cd farmdirect
pip install -r requirements.txt
python run.py            # → http://localhost:5000
```

The DB is auto-created and seeded on first run. To test the IVR:

1. Log in as any farmer (e.g. `vikram@farmdirect.in` / `farm123`).
2. Click **"IVR Voice"** in the navbar (or go to `/ivr/simulator`).
3. Pick a caller number on the right (e.g. Vikram Patil →
   `9820110001`).
4. Click the green call button.
5. You will hear the Tamil welcome. Press **1** for Tamil, **2** for English.
6. Try one of the **quick demo scripts** on the right of the page — e.g.
   "List 100 kg tomato @ ₹38" runs the full listing flow end-to-end.
7. After confirming, open the **Farmer Dashboard** or the
   **Marketplace** in another tab — the new listing appears instantly.

To run the automated end-to-end IVR test:

```bash
python /home/z/my-project/scripts/test_ivr_e2e.py
```

The test walks through 8 demos (Tamil listing, Tamil market price, Tamil
order, Tamil earnings, Tamil bulk order, call-log finalization, English
DTMF, admin stats) and verifies that the DB rows are actually written.

## Demo caller numbers (seeded)

| Number | Name | Role | City |
|--------|------|------|------|
| +91 98100 00001 | Admin — FarmDirect | admin | Nashik |
| +91 98201 10001 | Vikram Patil (Patil Fresh Farms) | farmer | Nashik |
| +91 98201 10002 | Sharda More (More Krishi Farm) | farmer | Dindori |
| +91 98201 10003 | Rahul Deshmukh (Deshmukh Agro) | farmer | Sinnar |
| +91 98201 10004 | Meena Shinde (Shinde Organic Farms) | farmer | Igatpuri |
| +91 98201 10005 | Suresh Yadav (Yadav Farms) | farmer | Nagpur |
| +91 98201 10006 | Vidarbha Farmer Producers Co. | fpo | Nagpur |
| +91 98201 10007 | Kaveri Green FPO Ltd. | fpo | Pune |

(All passwords: `farm123`, admin: `admin123`)

## Connecting a real phone number later

1. Buy a Twilio (or any SIP/IVR provider) phone number.
2. Set the env vars above (`IVR_MODE=production`, `IVR_TWILIO_*`, `IVR_PUBLIC_BASE_URL`).
3. Restart the Flask app.
4. In the Twilio console, configure the number's voice webhook to
   `https://your-app.example/api/ivr/incoming` (POST) and the status
   callback to `https://your-app.example/api/ivr/callback` (POST).
5. Done. Callers will hear the same Tamil welcome as the simulator.

The provider abstraction (`ivr/providers.py`) makes it trivial to add
Exotel, Knowlarity, Jio etc. — implement `TelephonyProvider` and
register it in `get_telephony()`.

## What the IVR does NOT do

- It does NOT keep a separate fake product/order/price database.
- It does NOT expose secrets (OTP, bank details, passwords) over the
  phone. Earnings are read-only summaries; no payment actions can be
  initiated from the IVR.
- It does NOT trust AI output blindly — every structured intent is
  validated (numeric fields are parsed with `int()`/`float()`, grades
  are constrained to A/B/C, harvest dates are normalized via ISO).
- It does NOT crash on bad input — every failure path produces a
  Tamil/English error prompt and routes back to the main menu.
