"""Sample data seeder — realistic Indian agri-marketplace dataset.

Generates: users (all roles), farmers/FPOs, products, 180 days of sales
history with seasonality, orders across every status, deliveries, payments
and demo bulk quotes. Deterministic (seeded RNG) so demos are repeatable.
"""
import hashlib
import os
import random
from datetime import datetime, timedelta

import db

rng = random.Random(42)


def _hash(pw):
    from werkzeug.security import generate_password_hash
    return generate_password_hash(pw)


# City coordinates (simulated service region — Nashik & Pune belt)
CITY_COORDS = {
    "Nashik": (19.9975, 73.7898), "Pune": (18.5204, 73.8567),
    "Mumbai": (19.0760, 72.8777), "Nagpur": (21.1458, 79.0882),
    "Nashik Rural": (20.0110, 73.7900), "Dindori": (20.2000, 73.8300),
    "Sinnar": (19.8500, 74.0000), "Igatpuri": (19.6900, 73.5600),
}
# Delivery drop points used by the route-optimizer demo (spread around Nashik hub)
DROP_POINTS = [
    ("College Road", 20.0110, 73.7900), ("Gangapur Road", 20.0320, 73.7410),
    ("Panchavati", 20.0130, 73.7990), ("Nashik Road Stn", 19.9470, 73.8380),
    ("Satpur MIDC", 20.0060, 73.7280), ("Ambad MIDC", 19.9730, 73.7230),
    ("Indira Nagar", 19.9780, 73.8480), ("Pathardi Phata", 19.9620, 73.7760),
    ("Adgaon", 20.0430, 73.8330), ("Ashwin Nagar", 19.9900, 73.7540),
    ("Jail Road", 19.9860, 73.8060), ("Mahatma Nagar", 20.0170, 73.7650),
    ("Bhagur", 20.0640, 73.9580), ("Deolali Cantt", 19.9270, 73.8560),
]

PRODUCT_CATALOG = [
    # crop, name, category, grade, qty, price, organic, seller_key, days_to_harvest
    ("Tomato", "Nashik Red Tomato (Hybrid)", "Vegetables", "A", 850, 24, 0, "vikram", -3),
    ("Tomato", "Farm Fresh Loose Tomato", "Vegetables", "B", 1200, 18, 0, "sharda", -1),
    ("Onion", "Nashik Lasalgaon Onion", "Vegetables", "A", 2500, 19, 0, "fpo_vidarbha", -7),
    ("Onion", "Red Onion — Sorted Grade", "Vegetables", "B", 1800, 14, 0, "rahul", -5),
    ("Potato", "Jyoti Potato — Fresh Dug", "Vegetables", "A", 2000, 21, 0, "rahul", -2),
    ("Rice", "Sona Masoori Rice (2026 Harvest)", "Grains", "A", 3500, 52, 0, "fpo_kaveri", -15),
    ("Rice", "Katarni Rice — Aromatic", "Grains", "A", 900, 68, 0, "suresh", -20),
    ("Banana", "Elder Banana — Grand Naine", "Fruits", "A", 1500, 28, 1, "sharda", -1),
    ("Mango", "Alphonso Mango — GI Tagged", "Fruits", "A", 600, 145, 0, "vikram", -4),
    ("Mango", "Kesar Mango — Juicy", "Fruits", "B", 950, 95, 0, "fpo_vidarbha", -6),
    ("Carrot", "Ooty Carrot — Crunchy", "Vegetables", "A", 700, 32, 1, "meena", -2),
    ("Carrot", "Desi Red Carrot", "Vegetables", "B", 1100, 24, 0, "suresh", -3),
    ("Spinach", "Palak — Pesticide Free", "Vegetables", "A", 300, 22, 1, "meena", 0),
    ("Wheat", "Khapli Wheat — Organic", "Grains", "A", 4000, 38, 1, "fpo_kaveri", -30),
    ("Green Chili", "Guntur Chili — Spicy", "Vegetables", "A", 450, 46, 0, "suresh", -2),
]

FARMERS = [
    ("vikram", "Vikram Patil", "vikram@farmdirect.in", "Nashik", "Maharashtra",
     "Patil Fresh Farms", 6.5, "Tomato, Mango, Onion",
     "3rd-generation farmer from Sinnar. Specialises in drip-irrigated tomato & Alphonso mango."),
    ("sharda", "Sharda More", "sharda@farmdirect.in", "Dindori", "Maharashtra",
     "More Krishi Farm", 4.0, "Banana, Tomato, Onion",
     "Women-led farm growing Grand Naine banana with organic compost."),
    ("rahul", "Rahul Deshmukh", "rahul@farmdirect.in", "Sinnar", "Maharashtra",
     "Deshmukh Agro", 9.0, "Potato, Onion",
     "Mechanised potato & onion farm with on-site grading unit."),
    ("meena", "Meena Shinde", "meena@farmdirect.in", "Igatpuri", "Maharashtra",
     "Shinde Organic Farms", 3.2, "Carrot, Spinach",
     "Certified organic grower — zero chemical pesticides since 2019."),
]

FPOS = [
    ("fpo_vidarbha", "Vidarbha Farmer Producers Co.", "fpo@farmdirect.in", "Nagpur",
     "Maharashtra", 412, "Mango, Onion",
     "FPO collective of 412 cotton-belt farmers now diversifying into horticulture."),
    ("fpo_kaveri", "Kaveri Green FPO Ltd.", "kaveri@farmdirect.in", "Pune",
     "Maharashtra", 268, "Rice, Wheat",
     "Producer company running its own rice mill & warehouse in Baramati."),
]

CONSUMERS = [
    ("priya", "Priya Sharma", "priya@example.in", "College Road, Nashik", "Nashik"),
    ("arjun", "Arjun Mehta", "arjun@example.in", "Gangapur Road, Nashik", "Nashik"),
    ("kavita", "Kavita Joshi", "kavita@example.in", "Panchavati, Nashik", "Nashik"),
]

BUYERS = [
    ("annapurna", "Annapurna Foods Pvt Ltd", "buy@annapurna.in", "Mumbai",
     "Restaurant chain — 22 outlets across Mumbai & Pune."),
    ("greenbasket", "GreenBasket Retail", "buy@greenbasket.in", "Pune",
     "Online grocer fulfilling 1,200 orders/day."),
]

SINGLES = ["suresh"]  # extra farmer defined inline below


def seed_all():
    from werkzeug.security import generate_password_hash
    from helpers import today_str
    import sqlite3

    conn = db.get_db()
    cur = conn.cursor()
    pw = generate_password_hash("farm123")

    # Fixed phone numbers for the demo farmers/FPOs/admin so the IVR
    # simulator can map a caller to the right farmer without ambiguity.
    # (Random phone numbers would also work — the lookup uses last-10-digit
    #  substring match — but fixed numbers make the demo repeatable.)
    DEMO_PHONES = {
        "admin":          "9810000001",
        "vikram":         "9820110001",
        "sharda":         "9820110002",
        "rahul":          "9820110003",
        "meena":          "9820110004",
        "suresh":         "9820110005",
        "fpo_vidarbha":   "9820110006",
        "fpo_kaveri":     "9820110007",
        "priya":          "9820120001",
        "arjun":          "9820120002",
        "kavita":         "9820120003",
        "annapurna":      "9820130001",
        "greenbasket":    "9820130002",
    }

    def add_user(name, email, role, city, state="Maharashtra",
                 phone=None, key=None):
        if phone is None:
            phone = DEMO_PHONES.get(key) or ("98" + f"{rng.randint(10000000,99999999)}")
        lat, lng = CITY_COORDS.get(city, (19.9975, 73.7898))
        cur.execute(
            "INSERT INTO users (name,email,phone,password_hash,role,city,state,lat,lng,created_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,datetime('now','localtime'))",
            (name, email, phone, pw, role, city, state, lat, lng))
        return cur.lastrowid

    # ---------------- Admin ----------------
    admin_id = add_user("Admin — FarmDirect", "admin@farmdirect.in", "admin", "Nashik",
                       key="admin")
    cur.execute("UPDATE users SET password_hash=? WHERE id=?", (generate_password_hash("admin123"), admin_id))

    # ---------------- Farmers / FPOs ----------------
    farmer_ids = {}
    for key, name, email, city, state, farm, acres, crops, bio in FARMERS:
        uid = add_user(name, email, "farmer", city, state, key=key)
        farmer_ids[key] = uid
        cur.execute("INSERT INTO farmers (user_id,farm_name,farm_size_acres,crops_grown,bio,rating,verified) "
                    "VALUES (?,?,?,?,?,?,1)", (uid, farm, acres, crops, bio, round(rng.uniform(4.3, 4.9), 1)))
    for key, name, email, city, state, members, crops, desc in FPOS:
        uid = add_user(name, email, "fpo", city, state, key=key)
        farmer_ids[key] = uid
        cur.execute("INSERT INTO fpos (user_id,fpo_name,member_count,district,state,description,verified) "
                    "VALUES (?,?,?,?,?,?,1)", (uid, name, members, city, state, desc))
    # extra individual farmer
    suid = add_user("Suresh Yadav", "suresh@farmdirect.in", "farmer", "Nagpur", key="suresh")
    farmer_ids["suresh"] = suid
    cur.execute("INSERT INTO farmers (user_id,farm_name,farm_size_acres,crops_grown,bio,rating,verified) "
                "VALUES (?,?,?,?,?,?,1)", (suid, "Yadav Farms", 7.5, "Rice, Carrot, Green Chili",
                                           "Rice specialist from Bhandara district; also grows Guntur chili.", 4.6))

    # ---------------- Consumers & Buyers ----------------
    consumer_ids = {}
    for key, name, email, addr, city in CONSUMERS:
        consumer_ids[key] = add_user(name, email, "consumer", city, key=key)
    buyer_ids = {}
    for key, name, email, city, note in BUYERS:
        buyer_ids[key] = add_user(name, email, "buyer", city, key=key)

    # ---------------- Products ----------------
    product_ids = []
    for crop, name, cat, grade, qty, price, organic, seller, hd in PRODUCT_CATALOG:
        cur.execute(
            "INSERT INTO products (seller_id,crop,name,category,grade,quantity_kg,price_per_kg,"
            "harvest_date,organic,description,created_at) VALUES (?,?,?,?,?,?,?,?,?,? ,datetime('now','localtime'))",
            (farmer_ids[seller], crop, name, cat, grade, qty, price,
             today_str(hd), organic,
             f"{name} — freshly harvested, graded & packed at farm. Cold-chain ready."))
        product_ids.append(cur.lastrowid)

    # ---------------- Sales history (180 days, seasonal + weekly pattern) --------
    base_demand = {"Tomato": 1400, "Onion": 2600, "Potato": 2200, "Rice": 1100,
                   "Banana": 1200, "Mango": 900, "Carrot": 500, "Spinach": 350,
                   "Wheat": 1500, "Green Chili": 300}   # kg per WEEK (region total)
    base_price = {"Tomato": 24, "Onion": 17, "Potato": 20, "Rice": 52, "Banana": 27,
                  "Mango": 105, "Carrot": 30, "Spinach": 20, "Wheat": 36, "Green Chili": 44}
    cities = ["Nashik", "Pune", "Mumbai", "Nagpur"]
    today = datetime.now().date()
    sales = []
    for crop, b in base_demand.items():
        bp = base_price[crop]
        for i in range(180, -1, -1):
            d = today - timedelta(days=i)
            doy = d.timetuple().tm_yday
            dow = d.weekday()
            seasonal = 1 + 0.25 * (doy / 365.0 - 0.5) * (1 if crop in ("Mango", "Tomato") else -0.6)
            weekly = 1 + 0.22 * (1 if dow in (5, 6) else (-0.4 if dow == 1 else 0))
            monsoon = 0.93 if (7 <= d.month <= 9 and crop in ("Tomato", "Spinach", "Carrot")) else 1.0
            festival = 1.12 if d.month in (9, 10, 11) else 1.0   # festive-season uplift
            growth = 1 + 0.15 * (1 - i / 180.0)                   # platform adoption growth
            noise = rng.uniform(0.9, 1.1)
            # b is the weekly regional demand -> split into 4 city-daily rows
            qty = max(4.0, b * seasonal * weekly * monsoon * festival * growth * noise / 7.0 / 4.0)
            price = bp * (1 + 0.18 * (doy / 365.0 - 0.5)) * growth * rng.uniform(0.96, 1.04)
            for city in cities:
                sales.append((crop, city, d.isoformat(), round(qty * rng.uniform(0.8, 1.2), 1),
                              round(price, 2)))
    cur.executemany("INSERT INTO sales_history (crop,city,date,quantity_kg,avg_price) VALUES (?,?,?,?,?)", sales)

    # ---------------- Orders (span last 40 days + live pipeline) -----------------
    order_defs = [
        # (buyer, items[(product_idx, qty)], status, days_ago, city_addr, drop_pt_idx)
        ("priya", [(0, 5), (8, 2)], "delivered", 12, "College Road, Nashik 422005", 0),
        ("priya", [(2, 10), (4, 8)], "delivered", 8, "College Road, Nashik 422005", 0),
        ("arjun", [(7, 6), (10, 4)], "delivered", 7, "Gangapur Road, Nashik 422013", 1),
        ("kavita", [(3, 8), (12, 3)], "delivered", 6, "Panchavati, Nashik 422003", 2),
        ("priya", [(8, 3), (13, 25)], "delivered", 5, "College Road, Nashik 422005", 0),
        ("arjun", [(1, 12), (4, 10)], "delivered", 4, "Gangapur Road, Nashik 422013", 1),
        ("kavita", [(5, 10), (9, 6)], "in_transit", 1, "Panchavati, Nashik 422003", 2),
        ("priya", [(6, 8), (14, 2)], "in_transit", 1, "College Road, Nashik 422005", 3),
        ("arjun", [(0, 6), (11, 5)], "picked_up", 0, "Gangapur Road, Nashik 422013", 4),
        ("kavita", [(7, 10), (10, 6)], "picked_up", 0, "Panchavati, Nashik 422003", 5),
        ("priya", [(2, 15), (5, 12)], "confirmed", 0, "College Road, Nashik 422005", 6),
        ("arjun", [(8, 4), (12, 4)], "confirmed", 0, "Gangapur Road, Nashik 422013", 7),
        ("kavita", [(1, 20)], "confirmed", 0, "Panchavati, Nashik 422003", 8),
        ("priya", [(4, 12), (6, 6)], "confirmed", 0, "College Road, Nashik 422005", 9),
        ("kavita", [(10, 5), (14, 3)], "confirmed", 0, "Panchavati, Nashik 422003", 12),
        ("arjun", [(3, 14), (11, 6)], "confirmed", 0, "Gangapur Road, Nashik 422013", 4),
        ("priya", [(7, 9)], "confirmed", 0, "College Road, Nashik 422005", 5),
        ("kavita", [(2, 10), (13, 20)], "confirmed", 0, "Panchavati, Nashik 422003", 1),
        ("arjun", [(9, 8), (13, 30)], "pending", 0, "Gangapur Road, Nashik 422013", 10),
        ("kavita", [(0, 8), (7, 8)], "pending", 0, "Panchavati, Nashik 422003", 11),
        ("priya", [(10, 5), (14, 3)], "pending", 0, "College Road, Nashik 422005", 12),
        # bulk orders
        ("annapurna", [(1, 800)], "delivered", 10, "Andheri East, Mumbai 400069", None),
        ("greenbasket", [(0, 500), (4, 400)], "delivered", 9, "Baner, Pune 411045", None),
        ("annapurna", [(5, 1000)], "delivered", 8, "Andheri East, Mumbai 400069", None),
        ("greenbasket", [(2, 1200)], "pending", 0, "Baner, Pune 411045", None),
        ("annapurna", [(7, 600), (9, 400)], "pending", 0, "Andheri East, Mumbai 400069", None),
        ("greenbasket", [(3, 2000)], "pending", 0, "Baner, Pune 411045", None),
    ]

    drivers = [("Ramesh Pawar", "MH15-AB-1234", "9822011223"),
               ("Sunil Kumar", "MH15-CD-5678", "9822033445"),
               ("Amit Shah", "MH15-EF-9012", "9822055667")]
    n_seq = 1000
    for buyer, items, status, days_ago, addr, drop_idx in order_defs:
        n_seq += 1
        created = (datetime.now() - timedelta(days=days_ago)).strftime("%Y-%m-%d %H:%M")
        code = f"FD-{datetime.now().strftime('%y%m%d')}-{n_seq}"
        buyer_id = consumer_ids.get(buyer) or buyer_ids.get(buyer)
        buyer_type = "bulk" if buyer in buyer_ids else "consumer"
        subtotal = sum(PRODUCT_CATALOG[i][5] * q for i, q in items)
        dfee = 25 if buyer_type == "consumer" else round(subtotal * 0.015, 0)
        fee = round(subtotal * 0.06, 0)
        total = round(subtotal + dfee + fee, 0)
        city = "Mumbai" if "Mumbai" in addr else ("Pune" if "Pune" in addr else "Nashik")
        dlat, dlng = (CITY_COORDS[city] if drop_idx is None else (DROP_POINTS[drop_idx][1], DROP_POINTS[drop_idx][2]))
        cur.execute(
            "INSERT INTO orders (order_code,buyer_id,buyer_type,total_amount,platform_fee,delivery_fee,"
            "delivery_address,delivery_city,delivery_pincode,delivery_lat,delivery_lng,order_type,status,"
            "created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,datetime('now','localtime'))",
            (code, buyer_id, buyer_type, total, fee, dfee, addr, city, "422005" if city == "Nashik" else "400069",
             dlat, dlng, "bulk" if buyer_type == "bulk" else "retail", status, created))
        oid = cur.lastrowid
        for i, q in items:
            crop, name, cat, grade, _, price, _, seller, _ = PRODUCT_CATALOG[i]
            fshare = round(price * q, 0)
            cur.execute("INSERT INTO order_items (order_id,product_id,farmer_id,crop,grade,quantity_kg,"
                        "unit_price,subtotal,item_status) VALUES (?,?,?,?,?,?,?,?,?)",
                        (oid, product_ids[i], farmer_ids[seller], crop, grade, q, price,
                         round(price * q, 0), "accepted" if status != "pending" else "pending"))
        pstatus = "completed" if status == "delivered" else "pending"
        cur.execute("INSERT INTO payments (order_id,buyer_id,farmer_id,amount,farmer_share,platform_fee,"
                    "delivery_fee,method,status,txn_code,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                    (oid, buyer_id, farmer_ids[PRODUCT_CATALOG[items[0][0]][7]], total, fshare, fee, dfee,
                     rng.choice(["UPI", "Cash on Delivery", "Card"]), pstatus,
                     f"TXN{rng.randint(100000, 999999)}", created))
        if status in ("confirmed", "picked_up", "in_transit", "delivered"):
            dstatus = status
            drv = drivers[oid % 3]
            pickup = CITY_COORDS["Nashik Rural"] if rng.random() < 0.5 else CITY_COORDS["Dindori"]
            if drop_idx is None:
                drop = CITY_COORDS[city]
                drop_name = addr
            else:
                drop = (DROP_POINTS[drop_idx][1], DROP_POINTS[drop_idx][2])
                drop_name = f"{addr}"
            import math
            def hav(a, b, c, d2):
                r = 6371.0
                import math as m
                p1, p2 = m.radians(a), m.radians(c)
                dp = m.radians(c - a); dl = m.radians(d2 - b)
                x = m.sin(dp/2)**2 + m.cos(p1)*m.cos(p2)*m.sin(dl/2)**2
                return 2*r*m.asin(m.sqrt(x))
            dist = round(hav(pickup[0], pickup[1], drop[0], drop[1]) * 1.35, 1)
            cur.execute("INSERT INTO deliveries (order_id,pickup_name,pickup_lat,pickup_lng,drop_name,"
                        "drop_lat,drop_lng,distance_km,eta_minutes,driver_name,driver_phone,vehicle,status,"
                        "updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,datetime('now','localtime'))",
                        (oid, "Farm pickup — Nashik belt", pickup[0], pickup[1], drop_name, drop[0], drop[1],
                         dist, int(dist / 26 * 60 + 12), drv[0], drv[2], drv[1], dstatus))

    # ---------------- Demo bulk quote ----------------
    cur.execute("INSERT INTO quotes (buyer_id,crop,quantity_kg,grade,city,status) VALUES (?,?,?,?,?,'open')",
                (buyer_ids["annapurna"], "Onion", 2000, "A", "Mumbai"))

    conn.commit()
    conn.close()
    print(f"Seeded OK: {len(PRODUCT_CATALOG)} products, {len(sales)} sales-history rows, "
          f"{len(order_defs)} orders.")
