"""Page routes (server-rendered Jinja) for all 16 screens."""
from datetime import datetime, timedelta

from flask import (Blueprint, abort, flash, g, redirect, render_template,
                   request, session, url_for)

import db
from ai.forecasting import forecast_crop, top_opportunities
from ai.pricing import recommend_price
from auth import login_required, role_required

bp = Blueprint("views", __name__)


# ---------------------------------------------------------------- Landing
@bp.route("/")
def landing():
    stats = {
        "farmers": db.query("SELECT COUNT(*) n FROM users WHERE role IN ('farmer','fpo')", one=True)["n"],
        "products": db.query("SELECT COUNT(*) n FROM products WHERE status='active'", one=True)["n"],
        "orders": db.query("SELECT COUNT(*) n FROM orders", one=True)["n"],
        "saved_pct": 34,
    }
    featured = db.query(
        "SELECT p.*, u.name AS seller_name, u.city, u.role AS seller_role "
        "FROM products p JOIN users u ON u.id=p.seller_id "
        "WHERE p.status='active' ORDER BY p.id LIMIT 8")
    return render_template("landing.html", stats=stats, featured=featured)


# ---------------------------------------------------------------- Marketplace
@bp.route("/marketplace")
def marketplace():
    crops = [r["crop"] for r in db.query(
        "SELECT DISTINCT crop FROM products WHERE status='active' ORDER BY crop")]
    cities = [r["city"] for r in db.query(
        "SELECT DISTINCT city FROM users WHERE role IN ('farmer','fpo') ORDER BY city")]
    q = request.args.get("q", "").strip()
    crop = request.args.get("crop", "")
    city = request.args.get("city", "")
    grade = request.args.get("grade", "")
    max_price = request.args.get("max_price", "")
    sort = request.args.get("sort", "recent")

    sql = ("SELECT p.*, u.name AS seller_name, u.role AS seller_role, u.city, "
           "(SELECT rating FROM farmers f WHERE f.user_id=p.seller_id) AS rating "
           "FROM products p JOIN users u ON u.id=p.seller_id WHERE p.status='active'")
    args = []
    if q:
        sql += " AND (p.name LIKE ? OR p.crop LIKE ? OR u.name LIKE ?)"
        args += [f"%{q}%"] * 3
    if crop:
        sql += " AND p.crop=?"
        args.append(crop)
    if city:
        sql += " AND u.city=?"
        args.append(city)
    if grade:
        sql += " AND p.grade=?"
        args.append(grade)
    if max_price:
        try:
            sql += " AND p.price_per_kg<=?"
            args.append(float(max_price))
        except ValueError:
            pass
    order = {"recent": "p.id DESC", "price_asc": "p.price_per_kg ASC",
             "price_desc": "p.price_per_kg DESC", "qty": "p.quantity_kg DESC"}.get(sort, "p.id DESC")
    sql += f" ORDER BY {order}"
    products = db.query(sql, args)
    cart_count = _cart_count()
    return render_template("marketplace.html", products=products, crops=crops,
                           cities=cities, filters={"q": q, "crop": crop, "city": city,
                                                   "grade": grade, "max_price": max_price,
                                                   "sort": sort},
                           cart_count=cart_count)


def _cart_count():
    if not g.get("user"):
        return 0
    return db.query("SELECT COALESCE(SUM(quantity_kg),0) n FROM cart_items WHERE user_id=?",
                    (g.user["id"],), one=True)["n"]


# ---------------------------------------------------------------- Product detail
@bp.route("/product/<int:pid>")
def product_detail(pid):
    p = db.query(
        "SELECT p.*, u.name AS seller_name, u.role AS seller_role, u.city, u.state, "
        "u.created_at AS member_since "
        "FROM products p JOIN users u ON u.id=p.seller_id WHERE p.id=?", (pid,), one=True)
    if not p:
        abort(404)
    if p["seller_role"] == "fpo":
        profile = db.query("SELECT * FROM fpos WHERE user_id=?", (p["seller_id"],), one=True)
        p = dict(p)
        p["org_name"] = profile["fpo_name"] if profile else None
        p["member_count"] = profile["member_count"] if profile else None
        p["bio"] = profile["description"] if profile else None
        p["rating"] = 4.7
    else:
        profile = db.query("SELECT * FROM farmers WHERE user_id=?", (p["seller_id"],), one=True)
        p = dict(p)
        p["org_name"] = profile["farm_name"] if profile else None
        p["farm_size_acres"] = profile["farm_size_acres"] if profile else None
        p["bio"] = profile["bio"] if profile else None
        p["rating"] = profile["rating"] if profile else 4.5

    rec = recommend_price(p["crop"], p["grade"], p["quantity_kg"], p["city"],
                          current_price=p["price_per_kg"], organic=bool(p["organic"]))
    similar = db.query(
        "SELECT p.*, u.name AS seller_name, u.city FROM products p JOIN users u ON u.id=p.seller_id "
        "WHERE p.crop=? AND p.id<>? AND p.status='active' LIMIT 4", (p["crop"], pid))
    return render_template("product_detail.html", p=p, rec=rec, similar=similar,
                           cart_count=_cart_count())


# ---------------------------------------------------------------- Cart & checkout
@bp.route("/cart")
@login_required
def cart():
    items = db.query(
        "SELECT c.id, c.quantity_kg, p.id AS product_id, p.name, p.crop, p.grade, "
        "p.price_per_kg, p.organic, p.quantity_kg AS available, u.name AS seller, u.city "
        "FROM cart_items c JOIN products p ON p.id=c.product_id JOIN users u ON u.id=p.seller_id "
        "WHERE c.user_id=? ORDER BY c.id", (g.user["id"],))
    subtotal = sum(i["price_per_kg"] * i["quantity_kg"] for i in items)
    fee = round(subtotal * 0.06, 0) if items else 0
    dfee = 25 if items else 0
    return render_template("cart.html", items=items, subtotal=subtotal,
                           platform_fee=fee, delivery_fee=dfee,
                           total=subtotal + fee + dfee, cart_count=_cart_count())


@bp.route("/checkout", methods=["GET", "POST"])
@login_required
def checkout():
    items = db.query(
        "SELECT c.id, c.quantity_kg, p.id AS product_id, p.name, p.crop, p.grade, p.price_per_kg "
        "FROM cart_items c JOIN products p ON p.id=c.product_id WHERE c.user_id=?", (g.user["id"],))
    if not items:
        flash("Your cart is empty.", "info")
        return redirect(url_for("views.marketplace"))
    subtotal = sum(i["price_per_kg"] * i["quantity_kg"] for i in items)
    fee = round(subtotal * 0.06, 0)
    dfee = 25
    if request.method == "POST":
        from api import place_order  # shared order engine
        oid, err = place_order(
            g.user["id"],
            [(i["product_id"], i["quantity_kg"]) for i in items],
            request.form.get("address", ""), request.form.get("city", "Nashik"),
            request.form.get("pincode", ""), request.form.get("pay_method", "UPI"))
        if err:
            flash(err, "danger")
            return redirect(url_for("views.checkout"))
        db.execute("DELETE FROM cart_items WHERE user_id=?", (g.user["id"],))
        order = db.query("SELECT order_code FROM orders WHERE id=?", (oid,), one=True)
        flash(f"Order {order['order_code']} placed successfully! 🎉", "success")
        return redirect(url_for("views.track_order", oid=oid))
    return render_template("checkout.html", items=items, subtotal=subtotal,
                           platform_fee=fee, delivery_fee=dfee,
                           total=subtotal + fee + dfee,
                           user=g.user, cart_count=_cart_count())


# ---------------------------------------------------------------- Orders & tracking
@bp.route("/orders")
@login_required
def my_orders():
    orders = db.query(
        "SELECT o.*, (SELECT COUNT(*) FROM order_items oi WHERE oi.order_id=o.id) AS n_items "
        "FROM orders o WHERE o.buyer_id=? ORDER BY o.id DESC", (g.user["id"],))
    return render_template("orders.html", orders=orders, cart_count=_cart_count())


@bp.route("/track/<int:oid>")
@login_required
def track_order(oid):
    o = db.query(
        "SELECT o.*, u.name AS buyer_name FROM orders o JOIN users u ON u.id=o.buyer_id "
        "WHERE o.id=?", (oid,), one=True)
    if not o or (o["buyer_id"] != g.user["id"] and g.role not in ("admin",)):
        abort(404)
    items = db.query(
        "SELECT oi.*, p.name AS product_name, u.name AS seller FROM order_items oi "
        "JOIN products p ON p.id=oi.product_id JOIN users u ON u.id=oi.farmer_id "
        "WHERE oi.order_id=?", (oid,))
    dlv = db.query("SELECT * FROM deliveries WHERE order_id=?", (oid,), one=True)
    pay = db.query("SELECT * FROM payments WHERE order_id=?", (oid,), one=True)
    return render_template("track.html", o=o, items=items, dlv=dlv, pay=pay,
                           cart_count=_cart_count())


# ---------------------------------------------------------------- Consumer dashboard
@bp.route("/consumer/dashboard")
@role_required("consumer")
def consumer_dashboard():
    uid = g.user["id"]
    orders = db.query(
        "SELECT * FROM orders WHERE buyer_id=? ORDER BY id DESC LIMIT 5", (uid,))
    totals = db.query(
        "SELECT COUNT(*) n_orders, COALESCE(SUM(total_amount),0) spent FROM orders "
        "WHERE buyer_id=? AND status<>'cancelled'", (uid,), one=True)
    active = db.query(
        "SELECT COUNT(*) n FROM orders WHERE buyer_id=? AND status IN "
        "('pending','confirmed','picked_up','in_transit')", (uid,), one=True)["n"]
    picks = db.query(
        "SELECT p.*, u.name AS seller_name, u.city FROM products p "
        "JOIN users u ON u.id=p.seller_id WHERE p.status='active' "
        "ORDER BY (p.organic) DESC, p.id DESC LIMIT 4")
    return render_template("consumer/dashboard.html", orders=orders,
                           totals=totals, active=active, picks=picks,
                           cart_count=_cart_count())


# ---------------------------------------------------------------- Farmer dashboard
@bp.route("/farmer/dashboard")
@role_required("farmer", "fpo")
def farmer_dashboard():
    uid = g.user["id"]
    kpi = db.query(
        "SELECT COALESCE(SUM(subtotal),0) revenue, COUNT(*) n_items FROM order_items "
        "WHERE farmer_id=? AND item_status='accepted'", (uid,), one=True)
    pending_items = db.query(
        "SELECT oi.*, o.order_code, o.created_at, p.name AS product_name, u.name AS buyer, "
        "o.delivery_city FROM order_items oi JOIN orders o ON o.id=oi.order_id "
        "JOIN products p ON p.id=oi.product_id JOIN users u ON u.id=o.buyer_id "
        "WHERE oi.farmer_id=? AND oi.item_status='pending' ORDER BY o.id DESC", (uid,))
    listings = db.query(
        "SELECT * FROM products WHERE seller_id=? AND status<>'removed' ORDER BY id DESC", (uid,))
    monthly = db.query(
        "SELECT substr(o.created_at,1,7) ym, SUM(oi.subtotal) amt FROM order_items oi "
        "JOIN orders o ON o.id=oi.order_id WHERE oi.farmer_id=? AND oi.item_status='accepted' "
        "GROUP BY ym ORDER BY ym DESC LIMIT 6", (uid,))
    monthly = list(reversed([dict(r) for r in monthly]))
    opps = top_opportunities(4)
    live_orders = db.query(
        "SELECT oi.*, o.order_code, o.status AS order_status, u.name AS buyer, o.delivery_city "
        "FROM order_items oi JOIN orders o ON o.id=oi.order_id JOIN users u ON u.id=o.buyer_id "
        "WHERE oi.farmer_id=? AND oi.item_status='accepted' AND o.status IN "
        "('confirmed','picked_up','in_transit') ORDER BY o.id DESC LIMIT 5", (uid,))
    return render_template("farmer/dashboard.html", kpi=kpi, pending_items=pending_items,
                           listings=listings, monthly=monthly, opps=opps,
                           live_orders=live_orders, cart_count=_cart_count())


# ---------------------------------------------------------------- Farmer orders
@bp.route("/farmer/orders")
@role_required("farmer", "fpo")
def farmer_orders():
    items = db.query(
        "SELECT oi.*, o.order_code, o.status AS order_status, o.created_at, o.delivery_city, "
        "o.delivery_address, u.name AS buyer, p.name AS product_name "
        "FROM order_items oi JOIN orders o ON o.id=oi.order_id "
        "JOIN users u ON u.id=o.buyer_id JOIN products p ON p.id=oi.product_id "
        "WHERE oi.farmer_id=? ORDER BY o.id DESC", (g.user["id"],))
    return render_template("farmer/orders.html", items=items, cart_count=_cart_count())


# ---------------------------------------------------------------- Add listing
@bp.route("/farmer/listings/new", methods=["GET", "POST"])
@role_required("farmer", "fpo")
def add_listing():
    if request.method == "POST":
        f = request.form
        crop = f.get("crop", "Tomato")
        try:
            qty = max(float(f.get("quantity_kg") or 0), 1)
            price = max(float(f.get("price_per_kg") or 0), 0.5)
        except ValueError:
            flash("Please enter valid quantity and price.", "danger")
            return redirect(url_for("views.add_listing"))
        db.execute(
            "INSERT INTO products (seller_id,crop,name,category,grade,quantity_kg,price_per_kg,"
            "harvest_date,organic,description) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (g.user["id"], crop, f.get("name") or f"{crop} — {g.user['city']}",
             f.get("category", "Vegetables"), f.get("grade", "A"), qty, price,
             f.get("harvest_date") or datetime.now().strftime("%Y-%m-%d"),
             1 if f.get("organic") else 0, f.get("description") or ""))
        flash("Listing published! Buyers can now discover your produce. 🌾", "success")
        return redirect(url_for("views.farmer_dashboard"))
    rec = recommend_price("Tomato", "A", 500, g.user["city"])
    return render_template("farmer/listing_form.html", rec=rec, cart_count=_cart_count())


# ---------------------------------------------------------------- Farmer earnings
@bp.route("/farmer/earnings")
@role_required("farmer", "fpo")
def farmer_earnings():
    uid = g.user["id"]
    kpi = db.query(
        "SELECT COALESCE(SUM(oi.subtotal),0) total_sales, COUNT(*) n_orders "
        "FROM order_items oi WHERE oi.farmer_id=? AND oi.item_status='accepted'", (uid,), one=True)
    paid = db.query(
        "SELECT COALESCE(SUM(p.farmer_share),0) v FROM payments p WHERE p.farmer_id=? "
        "AND p.status='completed'", (uid,), one=True)["v"]
    pending = db.query(
        "SELECT COALESCE(SUM(p.farmer_share),0) v FROM payments p WHERE p.farmer_id=? "
        "AND p.status='pending'", (uid,), one=True)["v"]
    avg_price = db.query(
        "SELECT AVG(oi.unit_price) v FROM order_items oi WHERE oi.farmer_id=?", (uid,), one=True)["v"]
    monthly = db.query(
        "SELECT substr(o.created_at,1,7) ym, SUM(oi.subtotal) amt, COUNT(*) n "
        "FROM order_items oi JOIN orders o ON o.id=oi.order_id "
        "WHERE oi.farmer_id=? AND oi.item_status='accepted' GROUP BY ym ORDER BY ym", (uid,))
    by_crop = db.query(
        "SELECT oi.crop, SUM(oi.subtotal) amt, SUM(oi.quantity_kg) qty, AVG(oi.unit_price) avgp "
        "FROM order_items oi WHERE oi.farmer_id=? GROUP BY oi.crop ORDER BY amt DESC", (uid,))
    txns = db.query(
        "SELECT p.*, o.order_code FROM payments p JOIN orders o ON o.id=p.order_id "
        "WHERE p.farmer_id=? ORDER BY p.id DESC LIMIT 10", (uid,))
    comparison = {
        "mandi_price": 18,          # what intermediary pays (sample: tomato)
        "suggested": 24,
        "consumer_direct": 28,
        "traditional_retail": 33,
    }
    comparison["farmer_share_traditional"] = round(
        comparison["mandi_price"] / comparison["traditional_retail"] * 100)
    comparison["farmer_share_direct"] = round(
        comparison["suggested"] / comparison["consumer_direct"] * 100)
    return render_template("farmer/earnings.html", kpi=kpi, paid=paid, pending=pending,
                           avg_price=avg_price, monthly=[dict(m) for m in monthly],
                           by_crop=by_crop, txns=txns, comparison=comparison,
                           cart_count=_cart_count())


# ---------------------------------------------------------------- AI: demand forecast
@bp.route("/farmer/forecast")
@role_required("farmer", "fpo", "admin")
def forecast_page():
    crop = request.args.get("crop", "Tomato")
    horizon = int(request.args.get("horizon", 7))
    fc = forecast_crop(crop, None, horizon)
    crops = [r["crop"] for r in db.query(
        "SELECT DISTINCT crop FROM sales_history ORDER BY crop")]
    others = [forecast_crop(c, None, 7) for c in crops if c != crop]
    return render_template("farmer/forecast.html", fc=fc, crop=crop, horizon=horizon,
                           crops=crops, others=others, cart_count=_cart_count())


# ---------------------------------------------------------------- AI: price recommendation
@bp.route("/farmer/price")
@role_required("farmer", "fpo", "admin")
def price_page():
    crops = [r["crop"] for r in db.query(
        "SELECT DISTINCT crop FROM sales_history ORDER BY crop")]
    crop = request.args.get("crop", "Tomato")
    grade = request.args.get("grade", "A")
    qty = request.args.get("qty", "500")
    try:
        qty = float(qty)
    except ValueError:
        qty = 500
    my_products = db.query(
        "SELECT * FROM products WHERE seller_id=? AND status='active'", (g.user["id"],))
    city = (g.user["city"] or "Nashik") if g.user else "Nashik"
    rec = recommend_price(crop, grade, qty, city)
    return render_template("farmer/price.html", rec=rec, crop=crop, grade=grade, qty=qty,
                           crops=crops, my_products=my_products, cart_count=_cart_count())


# ---------------------------------------------------------------- Bulk buyer dashboard
@bp.route("/buyer/dashboard")
@role_required("buyer")
def buyer_dashboard():
    uid = g.user["id"]
    bulk_products = db.query(
        "SELECT p.*, u.name AS seller_name, u.city, u.role AS seller_role "
        "FROM products p JOIN users u ON u.id=p.seller_id "
        "WHERE p.status='active' AND p.quantity_kg>=500 ORDER BY p.quantity_kg DESC")
    quotes = db.query("SELECT * FROM quotes WHERE buyer_id=? ORDER BY id DESC", (uid,))
    quote_data = []
    for q in quotes:
        res = db.query(
            "SELECT qr.*, u.name AS seller, u.city, u.role AS seller_role "
            "FROM quote_responses qr JOIN users u ON u.id=qr.seller_id "
            "WHERE qr.quote_id=? ORDER BY qr.price_per_kg", (q["id"],))
        quote_data.append({"q": q, "responses": res})
    orders = db.query(
        "SELECT o.*, (SELECT COUNT(*) FROM order_items oi WHERE oi.order_id=o.id) n_items "
        "FROM orders o WHERE o.buyer_id=? ORDER BY o.id DESC LIMIT 6", (uid,))
    kpi = db.query(
        "SELECT COUNT(*) n_orders, COALESCE(SUM(total_amount),0) spent FROM orders "
        "WHERE buyer_id=?", (uid,), one=True)
    return render_template("buyer/dashboard.html", bulk_products=bulk_products,
                           quote_data=quote_data, orders=orders, kpi=kpi,
                           cart_count=_cart_count())


# ---------------------------------------------------------------- Logistics
@bp.route("/logistics")
@role_required("admin")
def logistics_dashboard():
    drivers = db.query(
        "SELECT driver_name, driver_phone, vehicle, status, COUNT(*) n_jobs FROM deliveries "
        "WHERE status IN ('confirmed','picked_up','in_transit') GROUP BY driver_name, driver_phone, vehicle, status")
    pickups = db.query(
        "SELECT d.*, o.order_code, o.delivery_city, o.order_type, u.name AS buyer "
        "FROM deliveries d JOIN orders o ON o.id=d.order_id JOIN users u ON u.id=o.buyer_id "
        "WHERE d.status='confirmed' ORDER BY d.id")
    dropoffs = db.query(
        "SELECT d.*, o.order_code, o.delivery_city, o.order_type, u.name AS buyer "
        "FROM deliveries d JOIN orders o ON o.id=d.order_id JOIN users u ON u.id=o.buyer_id "
        "WHERE d.status IN ('picked_up','in_transit') ORDER BY d.id")
    recent = db.query(
        "SELECT d.*, o.order_code FROM deliveries d JOIN orders o ON o.id=d.order_id "
        "WHERE d.status='delivered' ORDER BY d.id DESC LIMIT 6")
    kpi = db.query(
        "SELECT COUNT(*) total, "
        "SUM(CASE WHEN status='delivered' THEN 1 ELSE 0 END) delivered, "
        "COALESCE(AVG(distance_km),0) avg_dist FROM deliveries", (), one=True)
    return render_template("logistics/dashboard.html", drivers=drivers, pickups=pickups,
                           dropoffs=dropoffs, recent=recent, kpi=kpi,
                           cart_count=_cart_count())


@bp.route("/logistics/routes")
@role_required("admin")
def route_optimizer_page():
    import json

    from ai.routing import optimize_from_db, HUB
    result = optimize_from_db()
    map_data = json.dumps({
        "hub": HUB,
        "routes": result.get("routes", []),
        "unassigned": [],
        "animate": True,
    })
    return render_template("logistics/routes.html", result=result, hub=HUB,
                           map_data=map_data,
                           cart_count=_cart_count())


# ---------------------------------------------------------------- Admin dashboard
@bp.route("/admin")
@role_required("admin")
def admin_dashboard():
    kpi = {
        "users": db.query("SELECT COUNT(*) n FROM users WHERE active=1", one=True)["n"],
        "farmers": db.query("SELECT COUNT(*) n FROM users WHERE role IN ('farmer','fpo')", one=True)["n"],
        "consumers": db.query("SELECT COUNT(*) n FROM users WHERE role='consumer'", one=True)["n"],
        "buyers": db.query("SELECT COUNT(*) n FROM users WHERE role='buyer'", one=True)["n"],
        "gmv": db.query("SELECT COALESCE(SUM(total_amount),0) v FROM orders WHERE status<>'cancelled'", one=True)["v"],
        "orders": db.query("SELECT COUNT(*) n FROM orders", one=True)["n"],
        "active_listings": db.query("SELECT COUNT(*) n FROM products WHERE status='active'", one=True)["n"],
        "farmer_payout": db.query("SELECT COALESCE(SUM(farmer_share),0) v FROM payments", one=True)["v"],
    }
    kpi["farmer_share_pct"] = round(kpi["farmer_payout"] / max(kpi["gmv"], 1) * 100)
    monthly = db.query(
        "SELECT substr(created_at,1,7) ym, COUNT(*) n, SUM(total_amount) amt "
        "FROM orders GROUP BY ym ORDER BY ym")
    by_crop = db.query(
        "SELECT crop, SUM(subtotal) amt FROM order_items GROUP BY crop ORDER BY amt DESC LIMIT 6")
    orders = db.query(
        "SELECT o.*, u.name AS buyer FROM orders o JOIN users u ON u.id=o.buyer_id "
        "ORDER BY o.id DESC LIMIT 12")
    users = db.query("SELECT * FROM users ORDER BY id DESC LIMIT 12")
    products = db.query(
        "SELECT p.*, u.name AS seller FROM products p JOIN users u ON u.id=p.seller_id "
        "ORDER BY p.id DESC LIMIT 12")
    txns = db.query(
        "SELECT p.*, o.order_code FROM payments p JOIN orders o ON o.id=p.order_id "
        "ORDER BY p.id DESC LIMIT 10")
    deliveries = db.query(
        "SELECT d.*, o.order_code FROM deliveries d JOIN orders o ON o.id=d.order_id "
        "ORDER BY d.id DESC LIMIT 10")
    return render_template("admin/dashboard.html", kpi=kpi, monthly=[dict(m) for m in monthly],
                           by_crop=by_crop, orders=orders, users=users, products=products,
                           txns=txns, deliveries=deliveries, cart_count=_cart_count())


# ---------------------------------------------------------------- IVR Simulator
@bp.route("/ivr/simulator")
@login_required
def ivr_simulator():
    """In-app IVR simulator — same backend APIs as a real phone call."""
    # Suggest caller numbers that map to existing demo farmers/FPOs
    farmers = db.query(
        "SELECT u.id, u.name, u.phone, u.role, u.city, "
        "f.farm_name FROM users u LEFT JOIN farmers f ON f.user_id=u.id "
        "WHERE u.role IN ('farmer','fpo') AND u.phone<>'' ORDER BY u.id LIMIT 12")
    return render_template("ivr/simulator.html", farmers=[dict(r) for r in farmers],
                           cart_count=_cart_count())


# ---------------------------------------------------------------- IVR Admin Dashboard
@bp.route("/admin/ivr")
@role_required("admin")
def ivr_admin():
    """Admin IVR analytics page (server-rendered shell + AJAX data)."""
    import db as _db
    # KPIs straight from DB (so the page works even without JS)
    kpi = {
        "total_calls": _db.query("SELECT COUNT(*) n FROM ivr_call_logs", one=True)["n"],
        "successful": _db.query("SELECT COUNT(*) n FROM ivr_call_logs WHERE success=1", one=True)["n"],
        "failed": _db.query("SELECT COUNT(*) n FROM ivr_call_logs WHERE had_error=1 OR success=0", one=True)["n"],
        "tamil": _db.query("SELECT COUNT(*) n FROM ivr_call_logs WHERE language='ta'", one=True)["n"],
        "english": _db.query("SELECT COUNT(*) n FROM ivr_call_logs WHERE language='en'", one=True)["n"],
        "listings_created": _db.query("SELECT COALESCE(SUM(listings_created),0) v FROM ivr_call_logs", one=True)["v"],
        "bulk_accepted": _db.query("SELECT COALESCE(SUM(bulk_accepted),0) v FROM ivr_call_logs", one=True)["v"],
        "price_requests": _db.query("SELECT COALESCE(SUM(price_requests),0) v FROM ivr_call_logs", one=True)["v"],
        "active_sessions": _db.query("SELECT COUNT(*) n FROM ivr_sessions WHERE status='active'", one=True)["n"],
    }
    recent = _db.query(
        "SELECT c.id, c.session_id, c.caller_number, c.farmer_name, c.language, "
        "c.intent, c.success, c.had_error, c.duration_sec, c.listings_created, "
        "c.bulk_accepted, c.start_time, c.end_time "
        "FROM ivr_call_logs c ORDER BY c.id DESC LIMIT 20")
    # top intents from events (last 500)
    top_intents = _db.query(
        "SELECT intent, COUNT(*) n FROM ivr_events WHERE intent IS NOT NULL "
        "AND intent<>'UNKNOWN' GROUP BY intent ORDER BY n DESC LIMIT 8")
    # provider mode info
    from ivr.providers import mode_info
    return render_template("ivr/admin.html", kpi=kpi,
                           recent=[dict(r) for r in recent],
                           top_intents=[dict(r) for r in top_intents],
                           mode=mode_info(),
                           cart_count=_cart_count())


@bp.route("/admin/ivr/call/<int:call_id>")
@role_required("admin")
def ivr_call_detail(call_id):
    import json as _json
    import db as _db
    call = _db.query("SELECT * FROM ivr_call_logs WHERE id=?", (call_id,), one=True)
    if not call:
        abort(404)
    events = _db.query("SELECT * FROM ivr_events WHERE session_id=? ORDER BY id",
                      (call["session_id"],))
    transcript = []
    if call["transcript"]:
        try:
            transcript = _json.loads(call["transcript"])
        except _json.JSONDecodeError:
            transcript = []
    sess = _db.query("SELECT * FROM ivr_sessions WHERE id=?", (call["session_id"],), one=True)
    return render_template("ivr/call_detail.html",
                           call=dict(call),
                           events=[dict(e) for e in events],
                           transcript=transcript,
                           session=dict(sess) if sess else None,
                           cart_count=_cart_count())
