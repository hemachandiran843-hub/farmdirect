# 🌱 FarmDirect — Digital Agricultural Marketplace

**From Farm to Consumer — Better Prices for Everyone.**

A fully functional prototype that connects farmers/FPOs directly with consumers,
retailers, restaurants and bulk buyers — eliminating unnecessary intermediaries so
that farmers earn more and consumers pay less. Built for an internal hackathon /
Smart India Hackathon demonstration.

![Stack](https://img.shields.io/badge/stack-Flask%20%2B%20SQLite%20%2B%20scikit--learn-green)

---

## ✨ What it does

| Role | Capabilities |
|------|-------------|
| **Farmer / FPO** | Register & login · profile with farm/location · add produce listings (crop, grade, quantity, harvest date, price) · accept/reject incoming orders · track earnings · AI demand forecasts · AI recommended selling price · sales history · **bilingual IVR voice channel (Tamil + English, DTMF + speech)** |
| **Consumer** | Browse & search marketplace (crop, price, location, grade) · view farmer/FPO profiles · cart & checkout · order tracking · order history |
| **Bulk Buyer** | Browse large-quantity listings · request quotations · auto-matched supplier comparison (price / ETA / total) · accept a quote → instant bulk order · estimated delivery time |
| **Admin** | Dashboard KPIs & analytics charts · manage users/products/orders · transaction ledger · logistics monitor · AI route optimization · **IVR management dashboard with call analytics & transcripts** |

## 📞 IVR — Voice channel for farmers without smartphones

A bilingual (தமிழ் / English) IVR system lets farmers who cannot use the
smartphone app call a phone number and use the entire marketplace through
DTMF or natural speech. The IVR uses the **same** backend as the web app
— every listing created through IVR appears in the marketplace, every
order status query hits the real `orders` table, every earnings number
comes from the real `payments` table.

- In-app IVR Simulator at `/ivr/simulator` (phone-frame UI, Tamil/English
  selector, mic + keypad, transcript, AI intent + backend action panels).
- IVR Admin Dashboard at `/admin/ivr` (Tamil vs English usage, top intents,
  success/failure, listings created through IVR, call details + transcripts).
- Production-ready for Twilio (set `IVR_MODE=production` + Twilio creds).
- 100% offline intent recognizer (rule-based, Tamil + English + Tanglish).

See **[IVR_README.md](IVR_README.md)** for the full IVR architecture,
API endpoints, env vars and demo caller numbers.

## 🤖 AI Features (all offline, deterministic)

1. **Demand Forecasting** — `ai/forecasting.py`
   scikit-learn `LinearRegression` trained on the last 60 days of regional sales with
   engineered features (time trend, weekday seasonality via sin/cos, market/weather
   signal) plus an explicit festival-season uplift rule. Predicts the next 7/30 days,
   reports kg/week current vs predicted, trend direction and a back-test confidence %.
   *Example output:* Tomato — current 1,626 kg/week → predicted 1,906 kg/week (Increasing, 92% confidence).

2. **Price Recommendation** — `ai/pricing.py`
   Transparent factor model: base market price × demand–supply factor (from the
   forecast) × 90-day price momentum (numpy polyfit) × quality grade × volume ×
   distance-to-hub transport cost. Shows the farmer's current price, the suggested
   price, the estimated consumer price and the potential earnings improvement —
   with the full factor breakdown visible in the UI.

3. **Route Optimization** — `ai/routing.py`
   KMeans clustering (scikit-learn) groups nearby deliveries → nearest-neighbour
   route construction from the hub → 2-opt local search. Reports distance, ETA
   (26 km/h + 8 min/stop) and savings vs individual trips on an interactive SVG
   city map (no external map API — works offline). *Typical result: ~29% distance saved.*

## 🧱 Tech Stack

- **Backend**: Python 3.10+, Flask 3 (REST API + server-rendered pages)
- **Database**: SQLite (stdlib `sqlite3`, WAL-friendly, auto-seeded)
- **AI**: pandas, NumPy, scikit-learn
- **Frontend**: Jinja2 templates, Bootstrap 5, vanilla JavaScript, Chart.js
  (all vendored locally in `static/vendor/` — the app runs **fully offline**)
- **Map**: custom SVG mockup (no external API)

## 🚀 Quick Start

```bash
cd farmdirect
pip install -r requirements.txt

python run.py            # → http://localhost:5000
```

The database (`data/farmdirect.db`) is created and seeded automatically on first
run with ~7,200 sales-history rows, 15 produce listings, 27 orders across every
status, deliveries, payments and a demo bulk quote.

To rebuild from scratch:

```bash
rm data/farmdirect.db
python run.py
```

### Demo logins (password for all: `farm123`, admin: `admin123`)

| Role | Email |
|------|-------|
| Farmer | `vikram@farmdirect.in` (also `sharda@`, `rahul@`, `meena@`, `suresh@`) |
| FPO | `fpo@farmdirect.in` (Vidarbha), `kaveri@farmdirect.in` |
| Consumer | `priya@example.in` (also `arjun@`, `kavita@`) |
| Bulk buyer | `buy@annapurna.in`, `buy@greenbasket.in` |
| Admin | `admin@farmdirect.in` / `admin123` |

The login page has **one-tap demo credential autofill** for judges.

### IVR demo caller numbers

Each demo farmer/FPO has a fixed phone number that the IVR simulator can
"dial" (caller-id → farmer lookup happens automatically):

| Phone | Name | Role |
|------|------|------|
| +91 98100 00001 | Admin — FarmDirect | admin |
| +91 98201 10001 | Vikram Patil (Patil Fresh Farms) | farmer |
| +91 98201 10002 | Sharda More (More Krishi Farm) | farmer |
| +91 98201 10003 | Rahul Deshmukh (Deshmukh Agro) | farmer |
| +91 98201 10004 | Meena Shinde (Shinde Organic Farms) | farmer |
| +91 98201 10005 | Suresh Yadav (Yadav Farms) | farmer |
| +91 98201 10006 | Vidarbha Farmer Producers Co. | fpo |
| +91 98201 10007 | Kaveri Green FPO Ltd. | fpo |

## 🗺️ Pages

Landing · Login/Register · Farmer Dashboard · Consumer Dashboard · Bulk Buyer
Dashboard · Marketplace · Product Details · Add Produce Listing · Cart & Checkout ·
Order Tracking · Farmer Earnings · AI Demand Forecast · AI Price Recommendation ·
Logistics Dashboard · Route Optimization · Admin Dashboard · **IVR Simulator** ·
**IVR Admin Dashboard** · **IVR Call Detail**.

## 🔌 REST API

```
GET  /api/products?q=&crop=&min_qty=     List/filter active products
GET  /api/products/<id>                  Product detail
POST /api/cart/add                       {product_id, quantity_kg}
POST /api/cart/update | /cart/remove     {cart_id, quantity_kg}
GET  /api/cart                           Current cart
POST /api/orders                         Direct order placement
GET  /api/orders                         My orders
POST /api/orders/<oid>/item/<iid>/status {action: accept|reject}   (farmer)
POST /api/deliveries/<id>/status         {status: picked_up|in_transit|delivered} (admin)
GET  /api/ai/forecast?crop=&horizon=7|30 AI demand forecast (JSON)
GET  /api/ai/price?crop=&grade=&qty=     AI price recommendation (JSON)
GET  /api/logistics/optimize             Route optimization result (admin)
POST /api/quotes                         Bulk quotation request (buyer)
POST /api/quotes/<qid>/accept/<rid>      Accept a supplier quote → order
GET  /api/admin/stats                    Platform KPIs (admin)
POST /api/admin/users/<id>/toggle        Suspend/activate user
POST /api/admin/products/<id>/status     Remove/restore listing

# IVR — Voice channel (same backend as the web app)
POST /api/ivr/incoming                   Start a call (simulator JSON or Twilio form)
POST /api/ivr/input                       One turn of DTMF / speech
GET  /api/ivr/session?session_token=     Resume a session
POST /api/ivr/callback                    Provider call-status webhook
POST /api/ivr/hangup                      Simulator-driven hangup
GET  /api/ivr/mode                        Active telephony / TTS / STT / intent provider
GET  /api/ivr/admin/stats                 IVR KPIs (admin)
GET  /api/ivr/admin/calls                Recent calls (admin)
GET  /api/ivr/admin/call/<id>            Single call detail (admin)
```

## 🗄️ Database Schema (`schema.sql`)

`users` · `farmers` · `fpos` · `products` · `cart_items` · `orders` ·
`order_items` · `payments` · `deliveries` · `quotes` · `quote_responses` ·
`demand_forecasts` · `price_recommendations` · `sales_history` ·
`ivr_sessions` · `ivr_call_logs` · `ivr_events`.

## 📂 Project Structure

```
farmdirect/
├── run.py                 # entry point
├── requirements.txt
├── schema.sql             # SQLite DDL (17 tables incl. 3 IVR)
├── app_factory.py         # Flask app factory + template filters
├── db.py                  # sqlite helpers (query/execute)
├── seed.py                # realistic sample data generator (fixed phone numbers)
├── auth.py                # register/login/logout + role guards
├── views.py               # all page routes (incl. /ivr/simulator, /admin/ivr)
├── api.py                 # REST JSON API + order engine
├── ivr_api.py             # IVR REST API + telephony webhooks (NEW)
├── helpers.py             # ₹/kg formatting, status pipeline
├── wsgi.py                # optional URL-prefix middleware
├── ai/
│   ├── forecasting.py     # sklearn demand forecast
│   ├── pricing.py         # price recommendation engine (re-used by IVR)
│   └── routing.py         # KMeans + 2-opt route optimizer
├── ivr/                   # NEW — IVR subsystem
│   ├── __init__.py        # public surface
│   ├── i18n.py             # Tamil + English prompt strings
│   ├── products_dict.py   # Tamil / English / Tanglish → crop
│   ├── numbers.py          # spoken quantity / price / grade / date parser
│   ├── intents.py         # rule-based intent recognizer + entity extraction
│   ├── providers.py       # Telephony / TTS / STT / Intent providers (Mock + Prod)
│   ├── services.py        # REAL backend actions (createProduceListing etc.)
│   └── session.py         # DialogManager state machine + call log
├── templates/             # Jinja2 (22 templates incl. IVR simulator / admin / call detail)
│   ├── ivr/simulator.html
│   ├── ivr/admin.html
│   └── ivr/call_detail.html
└── static/                # CSS, JS, vendored Bootstrap/Chart.js (offline)
    ├── css/ivr.css
    └── js/ivr_simulator.js
```

## 🎬 Suggested 3-minute demo script

1. **Landing** — headline, three benefits, chain comparison (52% → 85% farmer share).
2. **Consumer** (priya) — browse marketplace, filter, open a product, add to cart, checkout, watch the live order pipeline.
3. **Farmer** (vikram) — accept the incoming order, view earnings + monthly chart, open **AI Demand Forecast** (Tomato ↑17%), then **AI Price Guide**.
4. **Bulk buyer** (Annapurna) — request a 2 t onion quote, compare 3 supplier offers, accept the best.
5. **Admin** — dashboard analytics, then **Route Optimizer**: watch 7 trips collapse into 3 pooled EV routes (−29% distance).
6. **IVR Voice** — log in as Vikram, open `/ivr/simulator`, click "List 100 kg tomato @ ₹38" demo script. Watch the Tamil voice flow create a real product (visible in the marketplace). Then open **IVR Admin** (`/admin/ivr`) to see the call analytics + transcript.

## ⚠️ Prototype notes

- Payments are simulated (UPI/COD/Cardless). Farmer share is credited on pickup.
- Sales history, weather/market signals and driver telemetry are deterministic
  sample data so demos are repeatable offline.
- All AI is explainable rule + regression hybrid — no external APIs, no GPUs,
  no internet required.
