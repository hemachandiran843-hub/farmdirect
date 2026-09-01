-- ============================================================
-- FarmDirect — Digital Agricultural Marketplace
-- SQLite Schema (Prototype / SIH Hackathon)
-- ============================================================

PRAGMA foreign_keys = ON;

-- ---------- Users & Profiles ----------
CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    name          TEXT NOT NULL,
    email         TEXT UNIQUE NOT NULL,
    phone         TEXT,
    password_hash TEXT NOT NULL,
    role          TEXT NOT NULL CHECK (role IN ('farmer','fpo','consumer','buyer','admin')),
    city          TEXT,
    state         TEXT,
    lat           REAL,
    lng           REAL,
    active        INTEGER DEFAULT 1,
    created_at    TEXT DEFAULT (datetime('now','localtime'))
);

CREATE TABLE IF NOT EXISTS farmers (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         INTEGER NOT NULL REFERENCES users(id),
    farm_name       TEXT,
    farm_size_acres REAL DEFAULT 2.0,
    crops_grown     TEXT,                      -- comma separated
    bio             TEXT,
    rating          REAL DEFAULT 4.5,
    verified        INTEGER DEFAULT 1
);

CREATE TABLE IF NOT EXISTS fpos (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id      INTEGER NOT NULL REFERENCES users(id),
    fpo_name     TEXT NOT NULL,
    member_count INTEGER DEFAULT 50,
    district     TEXT,
    state        TEXT,
    description  TEXT,
    verified     INTEGER DEFAULT 1
);

-- ---------- Marketplace ----------
CREATE TABLE IF NOT EXISTS products (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    seller_id    INTEGER NOT NULL REFERENCES users(id),
    crop         TEXT NOT NULL,
    name         TEXT NOT NULL,
    category     TEXT DEFAULT 'Vegetables',
    grade        TEXT NOT NULL CHECK (grade IN ('A','B','C')),
    quantity_kg  REAL NOT NULL,
    price_per_kg REAL NOT NULL,
    harvest_date TEXT,
    organic      INTEGER DEFAULT 0,
    description  TEXT,
    unit_label   TEXT DEFAULT 'kg',
    status       TEXT DEFAULT 'active' CHECK (status IN ('active','sold_out','removed')),
    created_at   TEXT DEFAULT (datetime('now','localtime'))
);

-- ---------- Cart ----------
CREATE TABLE IF NOT EXISTS cart_items (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL REFERENCES users(id),
    product_id  INTEGER NOT NULL REFERENCES products(id),
    quantity_kg REAL NOT NULL,
    created_at  TEXT DEFAULT (datetime('now','localtime'))
);

-- ---------- Orders ----------
CREATE TABLE IF NOT EXISTS orders (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    order_code       TEXT UNIQUE NOT NULL,          -- e.g. FD-260831-0142
    buyer_id         INTEGER NOT NULL REFERENCES users(id),
    buyer_type       TEXT DEFAULT 'consumer',       -- consumer / bulk
    total_amount     REAL NOT NULL,
    platform_fee     REAL DEFAULT 0,
    delivery_fee     REAL DEFAULT 0,
    delivery_address TEXT,
    delivery_city    TEXT,
    delivery_pincode TEXT,
    delivery_lat     REAL,
    delivery_lng     REAL,
    order_type       TEXT DEFAULT 'retail',         -- retail / bulk
    status           TEXT DEFAULT 'pending' CHECK (status IN
                       ('pending','confirmed','rejected','picked_up','in_transit','delivered','cancelled')),
    created_at       TEXT DEFAULT (datetime('now','localtime')),
    updated_at       TEXT
);

CREATE TABLE IF NOT EXISTS order_items (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id    INTEGER NOT NULL REFERENCES orders(id),
    product_id  INTEGER NOT NULL REFERENCES products(id),
    farmer_id   INTEGER NOT NULL REFERENCES users(id),
    crop        TEXT,
    grade       TEXT,
    quantity_kg REAL NOT NULL,
    unit_price  REAL NOT NULL,
    subtotal    REAL NOT NULL,
    item_status TEXT DEFAULT 'pending' CHECK (item_status IN
                  ('pending','accepted','rejected')),
    farmer_note TEXT
);

-- ---------- Payments & Earnings ----------
CREATE TABLE IF NOT EXISTS payments (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id     INTEGER NOT NULL REFERENCES orders(id),
    buyer_id     INTEGER,
    farmer_id    INTEGER,
    amount       REAL NOT NULL,        -- total paid by buyer
    farmer_share REAL DEFAULT 0,       -- credited to farmer on delivery
    platform_fee REAL DEFAULT 0,
    delivery_fee REAL DEFAULT 0,
    method       TEXT DEFAULT 'UPI',
    status       TEXT DEFAULT 'pending' CHECK (status IN ('pending','completed','refunded')),
    txn_code     TEXT,
    created_at   TEXT DEFAULT (datetime('now','localtime'))
);

-- ---------- Logistics ----------
CREATE TABLE IF NOT EXISTS deliveries (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id       INTEGER NOT NULL REFERENCES orders(id),
    pickup_name    TEXT,
    pickup_lat     REAL,
    pickup_lng     REAL,
    drop_name      TEXT,
    drop_lat       REAL,
    drop_lng       REAL,
    distance_km    REAL DEFAULT 0,
    eta_minutes    INTEGER DEFAULT 0,
    driver_name    TEXT,
    driver_phone   TEXT,
    vehicle        TEXT,
    status         TEXT DEFAULT 'pending' CHECK (status IN
                     ('pending','confirmed','picked_up','in_transit','delivered')),
    route_id       INTEGER,             -- assigned optimized route
    updated_at     TEXT
);

-- ---------- Quotations (Bulk Buyers) ----------
CREATE TABLE IF NOT EXISTS quotes (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    buyer_id    INTEGER NOT NULL REFERENCES users(id),
    crop        TEXT NOT NULL,
    quantity_kg REAL NOT NULL,
    grade       TEXT DEFAULT 'A',
    city        TEXT,
    status      TEXT DEFAULT 'open' CHECK (status IN ('open','converted','closed')),
    created_at  TEXT DEFAULT (datetime('now','localtime'))
);

CREATE TABLE IF NOT EXISTS quote_responses (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    quote_id     INTEGER NOT NULL REFERENCES quotes(id),
    seller_id    INTEGER NOT NULL REFERENCES users(id),
    price_per_kg REAL NOT NULL,
    total_amount REAL,
    eta_days     INTEGER DEFAULT 3,
    status       TEXT DEFAULT 'pending' CHECK (status IN ('pending','accepted','declined'))
);

-- ---------- AI: Demand Forecasts ----------
CREATE TABLE IF NOT EXISTS demand_forecasts (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    crop             TEXT NOT NULL,
    city             TEXT,
    horizon_days     INTEGER NOT NULL,     -- 7 or 30
    current_demand   REAL,                 -- kg / week (last 4 weeks avg)
    predicted_demand REAL,                 -- kg / week (forecast)
    trend            TEXT,                 -- Increasing / Stable / Decreasing
    confidence       REAL,                 -- 0..1
    payload          TEXT,                 -- JSON series for Chart.js
    generated_at     TEXT DEFAULT (datetime('now','localtime'))
);

-- ---------- AI: Price Recommendations ----------
CREATE TABLE IF NOT EXISTS price_recommendations (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    crop              TEXT NOT NULL,
    grade             TEXT,
    quantity_kg       REAL,
    current_price     REAL,
    suggested_price   REAL,
    consumer_price    REAL,
    mandi_price       REAL,
    earnings_gain_pct REAL,
    factors           TEXT,                -- JSON factor breakdown
    created_at        TEXT DEFAULT (datetime('now','localtime'))
);

-- ---------- Sales History (feeds the AI engine) ----------
CREATE TABLE IF NOT EXISTS sales_history (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    crop        TEXT NOT NULL,
    city        TEXT,
    date        TEXT NOT NULL,             -- YYYY-MM-DD
    quantity_kg REAL NOT NULL,
    avg_price   REAL
);

CREATE INDEX IF NOT EXISTS idx_sales_crop_date ON sales_history(crop, date);
CREATE INDEX IF NOT EXISTS idx_products_status ON products(status);
CREATE INDEX IF NOT EXISTS idx_orders_buyer    ON orders(buyer_id);
CREATE INDEX IF NOT EXISTS idx_items_farmer    ON order_items(farmer_id);

-- ============================================================
-- IVR — Voice channel for farmers without smartphones
-- The IVR re-uses the same products / orders / payments tables;
-- these tables only store IVR sessions, call logs and events.
-- ============================================================

CREATE TABLE IF NOT EXISTS ivr_sessions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    session_token   TEXT UNIQUE NOT NULL,
    call_id         TEXT,                       -- provider call id (Twilio etc.)
    caller_number   TEXT NOT NULL,              -- E.164 or simulator caller-id
    user_id         INTEGER,                    -- matched users.id (NULL if not registered)
    farmer_id       INTEGER,                     -- matched users.id (NULL if not a farmer/fpo)
    language        TEXT DEFAULT 'ta',          -- 'ta' or 'en'
    current_menu    TEXT DEFAULT 'language_select',
    current_intent  TEXT,
    conversation_state TEXT,                    -- JSON: partial listing, last prompt, etc.
    auth_status     TEXT DEFAULT 'unverified',   -- unverified / pin_pending / verified
    failure_count   INTEGER DEFAULT 0,          -- consecutive speech-recognition failures
    status          TEXT DEFAULT 'active'       -- active / ended / failed
                       CHECK (status IN ('active','ended','failed')),
    created_at      TEXT DEFAULT (datetime('now','localtime')),
    updated_at      TEXT DEFAULT (datetime('now','localtime'))
);

CREATE TABLE IF NOT EXISTS ivr_call_logs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id      INTEGER NOT NULL REFERENCES ivr_sessions(id),
    caller_number   TEXT NOT NULL,
    user_id         INTEGER,
    farmer_name     TEXT,
    language        TEXT,
    intent          TEXT,
    success         INTEGER DEFAULT 0,           -- 1 = call ended cleanly, 0 = failed/abandoned
    had_error       INTEGER DEFAULT 0,
    duration_sec    INTEGER DEFAULT 0,
    listings_created INTEGER DEFAULT 0,
    bulk_accepted   INTEGER DEFAULT 0,
    price_requests  INTEGER DEFAULT 0,
    order_requests  INTEGER DEFAULT 0,
    earnings_requests INTEGER DEFAULT 0,
    start_time      TEXT,
    end_time        TEXT,
    transcript      TEXT                          -- JSON array of {role, text, intent}
);

CREATE TABLE IF NOT EXISTS ivr_events (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id      INTEGER NOT NULL REFERENCES ivr_sessions(id),
    ts              TEXT DEFAULT (datetime('now','localtime')),
    event_type      TEXT NOT NULL,               -- prompt / dtmf / speech / intent / action / error / hangup
    raw_input       TEXT,
    recognized_text TEXT,
    intent          TEXT,
    intent_payload  TEXT,                         -- JSON: structured intent data
    response_text   TEXT,
    backend_action  TEXT,                         -- e.g. "createProduceListing"
    backend_result  TEXT,                         -- JSON
    error           TEXT
);

CREATE INDEX IF NOT EXISTS idx_ivr_sessions_caller ON ivr_sessions(caller_number);
CREATE INDEX IF NOT EXISTS idx_ivr_events_session ON ivr_events(session_id);
