"""REST API endpoints (JSON) consumed by the frontend via fetch().

Covers: products, cart, orders, farmer actions, quotations, AI endpoints
(forecast / pricing / route optimization), logistics updates, admin stats.
"""
from flask import Blueprint, g, jsonify, request, session

import db
from ai.forecasting import forecast_crop
from ai.pricing import recommend_price
from ai.routing import optimize_from_db
from auth import login_required, role_required

bp = Blueprint("api", __name__)


# ------------------------------------------------------------------ Products
@bp.get("/products")
def list_products():
    sql = ("SELECT p.id,p.name,p.crop,p.grade,p.quantity_kg,p.price_per_kg,p.organic, "
           "u.name AS seller,u.city,u.role AS seller_role FROM products p "
           "JOIN users u ON u.id=p.seller_id WHERE p.status='active'")
    args = []
    if request.args.get("q"):
        sql += " AND (p.name LIKE ? OR p.crop LIKE ?)"
        args += [f"%{request.args['q']}%"] * 2
    if request.args.get("crop"):
        sql += " AND p.crop=?"
        args.append(request.args["crop"])
    if request.args.get("min_qty"):
        sql += " AND p.quantity_kg>=?"
        args.append(float(request.args["min_qty"]))
    rows = db.query(sql, args)
    return jsonify([dict(r) for r in rows])


@bp.get("/products/<int:pid>")
def get_product(pid):
    row = db.query("SELECT p.*, u.name AS seller FROM products p JOIN users u ON u.id=p.seller_id "
                   "WHERE p.id=?", (pid,), one=True)
    return (jsonify(dict(row)) if row else (jsonify({"error": "not found"}), 404))


# ------------------------------------------------------------------ Cart
@bp.post("/cart/add")
@login_required
def cart_add():
    data = request.get_json(silent=True) or request.form
    pid = int(data.get("product_id", 0))
    qty = float(data.get("quantity_kg", 1))
    product = db.query("SELECT * FROM products WHERE id=? AND status='active'", (pid,), one=True)
    if not product:
        return jsonify({"ok": False, "error": "Product unavailable"}), 400
    qty = max(0.5, min(qty, product["quantity_kg"]))
    existing = db.query("SELECT * FROM cart_items WHERE user_id=? AND product_id=?",
                        (g.user["id"], pid), one=True)
    if existing:
        new_qty = min(existing["quantity_kg"] + qty, product["quantity_kg"])
        db.execute("UPDATE cart_items SET quantity_kg=? WHERE id=?", (new_qty, existing["id"]))
    else:
        db.execute("INSERT INTO cart_items (user_id,product_id,quantity_kg) VALUES (?,?,?)",
                   (g.user["id"], pid, qty))
    n = db.query("SELECT COUNT(*) n FROM cart_items WHERE user_id=?", (g.user["id"],), one=True)["n"]
    return jsonify({"ok": True, "cart_items": n, "message": f"{product['name']} added to cart"})


@bp.post("/cart/update")
@login_required
def cart_update():
    data = request.get_json(silent=True) or request.form
    cid = int(data.get("cart_id", 0))
    qty = float(data.get("quantity_kg", 1))
    item = db.query("SELECT c.*, p.quantity_kg AS available FROM cart_items c "
                    "JOIN products p ON p.id=c.product_id WHERE c.id=? AND c.user_id=?",
                    (cid, g.user["id"]), one=True)
    if not item:
        return jsonify({"ok": False, "error": "Item not in cart"}), 404
    qty = max(0.5, min(qty, item["available"]))
    db.execute("UPDATE cart_items SET quantity_kg=? WHERE id=?", (qty, cid))
    return jsonify({"ok": True, "quantity_kg": qty})


@bp.post("/cart/remove")
@login_required
def cart_remove():
    data = request.get_json(silent=True) or request.form
    cid = int(data.get("cart_id", 0))
    db.execute("DELETE FROM cart_items WHERE id=? AND user_id=?", (cid, g.user["id"]))
    return jsonify({"ok": True})


@bp.get("/cart")
@login_required
def cart_get():
    rows = db.query(
        "SELECT c.id, c.quantity_kg, p.name, p.price_per_kg, p.crop, p.grade "
        "FROM cart_items c JOIN products p ON p.id=c.product_id WHERE c.user_id=?",
        (g.user["id"],))
    return jsonify([dict(r) for r in rows])


# ------------------------------------------------------------------ Orders
def place_order(buyer_id, items, address, city, pincode, pay_method="UPI"):
    """Shared order engine. items = [(product_id, qty_kg)]. Returns (order_id, error)."""
    if not items:
        return None, "Cart is empty."
    buyer = db.query("SELECT * FROM users WHERE id=?", (buyer_id,), one=True)
    subtotal, lines, fshare_by_farmer = 0.0, [], {}
    for pid, qty in items:
        p = db.query("SELECT * FROM products WHERE id=? AND status='active'", (pid,), one=True)
        if not p:
            return None, "A product in your cart is no longer available."
        qty = min(qty, p["quantity_kg"])
        if qty <= 0:
            return None, f"Insufficient stock for {p['name']}."
        sub = round(p["price_per_kg"] * qty, 2)
        subtotal += sub
        lines.append((p, qty, sub))
        fshare_by_farmer[p["seller_id"]] = fshare_by_farmer.get(p["seller_id"], 0) + sub
    total_qty = sum(q for _, q, _ in lines)
    buyer_type = "bulk" if (buyer["role"] == "buyer" or total_qty >= 500) else "consumer"
    fee = round(subtotal * 0.06, 2)
    dfee = 25 if buyer_type == "consumer" else round(subtotal * 0.015, 2)
    total = round(subtotal + fee + dfee, 2)

    from datetime import datetime
    code = "FD-" + datetime.now().strftime("%y%m%d") + "-" + f"{buyer_id}{int(datetime.now().timestamp()) % 10000:04d}"
    lat, lng = buyer["lat"], buyer["lng"]
    oid = db.execute(
        "INSERT INTO orders (order_code,buyer_id,buyer_type,total_amount,platform_fee,delivery_fee,"
        "delivery_address,delivery_city,delivery_pincode,delivery_lat,delivery_lng,order_type,status) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,'pending')",
        (code, buyer_id, buyer_type, total, fee, dfee, address or buyer["city"],
         city or buyer["city"], pincode or "422005", lat, lng, buyer_type))
    for p, qty, sub in lines:
        db.execute("INSERT INTO order_items (order_id,product_id,farmer_id,crop,grade,quantity_kg,"
                   "unit_price,subtotal,item_status) VALUES (?,?,?,?,?,?,?,?,'pending')",
                   (oid, p["id"], p["seller_id"], p["crop"], p["grade"], qty,
                    p["price_per_kg"], sub))
        remaining = p["quantity_kg"] - qty
        db.execute("UPDATE products SET quantity_kg=?, status=? WHERE id=?",
                   (remaining, "active" if remaining > 0 else "sold_out", p["id"]))
    db.execute("INSERT INTO payments (order_id,buyer_id,amount,farmer_share,platform_fee,delivery_fee,"
               "method,status,txn_code) VALUES (?,?,?,?,?,?,?,?,?)",
               (oid, buyer_id, total, round(sum(fshare_by_farmer.values()), 2), fee, dfee,
                pay_method, "completed" if pay_method != "Cash on Delivery" else "pending",
                f"TXN{int(datetime.now().timestamp()) % 1000000}"))
    # Create the delivery record (pending pickup at first farmer / hub)
    first_farmer = db.query("SELECT u.lat,u.lng,u.city FROM order_items oi JOIN users u "
                            "ON u.id=oi.farmer_id WHERE oi.order_id=? LIMIT 1", (oid,), one=True)
    if first_farmer:
        dist = round(42.0, 1)
        db.execute(
            "INSERT INTO deliveries (order_id,pickup_name,pickup_lat,pickup_lng,drop_name,drop_lat,"
            "drop_lng,distance_km,eta_minutes,driver_name,driver_phone,vehicle,status) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,'pending')",
            (oid, f"Farm pickup — {first_farmer['city']}", first_farmer["lat"], first_farmer["lng"],
             address or buyer["city"], lat, lng, dist, int(dist / 26 * 60 + 15),
             "Unassigned", "", ""))
    return oid, None


@bp.post("/orders")
@login_required
def create_order():
    data = request.get_json(silent=True) or request.form
    items = [(int(i["product_id"]), float(i["quantity_kg"]))
             for i in (data.get("items") or [])]
    oid, err = place_order(g.user["id"], items,
                           data.get("address", ""), data.get("city", ""),
                           data.get("pincode", ""), data.get("pay_method", "UPI"))
    if err:
        return jsonify({"ok": False, "error": err}), 400
    return jsonify({"ok": True, "order_id": oid})


@bp.get("/orders")
@login_required
def list_orders():
    rows = db.query("SELECT * FROM orders WHERE buyer_id=? ORDER BY id DESC", (g.user["id"],))
    return jsonify([dict(r) for r in rows])


@bp.post("/orders/<int:oid>/item/<int:iid>/status")
@role_required("farmer", "fpo", "admin")
def farmer_item_status(oid, iid):
    """Farmer accepts / rejects their line item."""
    data = request.get_json(silent=True) or request.form
    action = data.get("action")  # accept | reject
    item = db.query("SELECT * FROM order_items WHERE id=? AND order_id=? AND farmer_id=?",
                    (iid, oid, g.user["id"]), one=True)
    if not item:
        return jsonify({"ok": False, "error": "Order item not found"}), 404
    if action not in ("accept", "reject"):
        return jsonify({"ok": False, "error": "Invalid action"}), 400

    new_status = "accepted" if action == "accept" else "rejected"
    db.execute("UPDATE order_items SET item_status=? WHERE id=?", (new_status, iid))
    if action == "reject":
        # restore stock
        db.execute("UPDATE products SET quantity_kg=quantity_kg+? WHERE id=?",
                   (item["quantity_kg"], item["product_id"]))
        db.execute("UPDATE orders SET status='rejected' WHERE id=?", (oid,))
    else:
        # if all items accepted → confirm order & schedule delivery
        pending = db.query("SELECT COUNT(*) n FROM order_items WHERE order_id=? AND item_status='pending'",
                           (oid,), one=True)["n"]
        rejected = db.query("SELECT COUNT(*) n FROM order_items WHERE order_id=? AND item_status='rejected'",
                            (oid,), one=True)["n"]
        if pending == 0 and rejected == 0:
            db.execute("UPDATE orders SET status='confirmed', updated_at=datetime('now','localtime') "
                       "WHERE id=?", (oid,))
            db.execute("UPDATE deliveries SET status='confirmed', "
                       "driver_name=COALESCE(NULLIF(driver_name,'Unassigned'),'Ramesh Pawar'), "
                       "driver_phone=COALESCE(NULLIF(driver_phone,''),'9822011223'), "
                       "vehicle=COALESCE(NULLIF(vehicle,''),'MH15-AB-1234') WHERE order_id=?", (oid,))
    return jsonify({"ok": True, "item_status": new_status})


@bp.post("/deliveries/<int:did>/status")
@role_required("admin")
def delivery_status(did):
    """Logistics pipeline: pending → confirmed → picked_up → in_transit → delivered."""
    data = request.get_json(silent=True) or request.form
    nxt = data.get("status")
    allowed = ["pending", "confirmed", "picked_up", "in_transit", "delivered"]
    if nxt not in allowed:
        return jsonify({"ok": False, "error": "Invalid status"}), 400
    d = db.query("SELECT * FROM deliveries WHERE id=?", (did,), one=True)
    if not d:
        return jsonify({"ok": False, "error": "Delivery not found"}), 404
    if allowed.index(nxt) != allowed.index(d["status"]) + 1 and not (d["status"] == "pending" and nxt == "confirmed"):
        return jsonify({"ok": False, "error": f"Cannot skip from {d['status']} to {nxt}"}), 400
    db.execute("UPDATE deliveries SET status=?, updated_at=datetime('now','localtime') WHERE id=?",
               (nxt, did))
    order_status = {"confirmed": "confirmed", "picked_up": "picked_up",
                    "in_transit": "in_transit", "delivered": "delivered"}.get(nxt)
    if order_status:
        db.execute("UPDATE orders SET status=?, updated_at=datetime('now','localtime') WHERE id=?",
                   (order_status, d["order_id"]))
        if nxt == "picked_up":
            db.execute("UPDATE payments SET status='completed' WHERE order_id=?", (d["order_id"],))
    return jsonify({"ok": True, "status": nxt})


# ------------------------------------------------------------------ AI endpoints
@bp.get("/ai/forecast")
def ai_forecast():
    crop = request.args.get("crop", "Tomato")
    horizon = request.args.get("horizon", "7")
    horizon = int(horizon) if horizon in ("7", "30") else 7
    return jsonify(forecast_crop(crop, None, horizon))


@bp.get("/ai/price")
def ai_price():
    crop = request.args.get("crop", "Tomato")
    grade = request.args.get("grade", "B")
    try:
        qty = float(request.args.get("qty", 500))
    except ValueError:
        qty = 500.0
    rec = recommend_price(crop, grade, qty, request.args.get("city"))
    return jsonify(rec)


@bp.get("/logistics/optimize")
@role_required("admin")
def logistics_optimize():
    return jsonify(optimize_from_db())


# ------------------------------------------------------------------ Quotations (bulk)
@bp.post("/quotes")
@role_required("buyer")
def create_quote():
    data = request.get_json(silent=True) or request.form
    crop = data.get("crop", "Onion")
    try:
        qty = float(data.get("quantity_kg", 1000))
    except ValueError:
        return jsonify({"ok": False, "error": "Invalid quantity"}), 400
    grade = data.get("grade", "A")
    city = data.get("city", "Mumbai")
    qid = db.execute("INSERT INTO quotes (buyer_id,crop,quantity_kg,grade,city) VALUES (?,?,?,?,?)",
                     (g.user["id"], crop, qty, grade, city))
    # Auto-generate responses from matching sellers (simulated negotiation)
    sellers = db.query(
        "SELECT p.*, u.city, u.name FROM products p JOIN users u ON u.id=p.seller_id "
        "WHERE p.crop=? AND p.status='active' AND p.quantity_kg>=? ORDER BY p.grade LIMIT 5",
        (crop, min(qty, 500)))
    seen = set()
    for s in sellers:
        if s["seller_id"] in seen:
            continue
        seen.add(s["seller_id"])
        rec = recommend_price(crop, s["grade"], qty, s["city"])
        price = round(rec["suggested_price"] * (0.95 if qty >= 1000 else 0.98), 1)
        eta = 2 if s["city"] == city else (3 if (s["city"] in ("Pune", "Nashik")) else 4)
        db.execute("INSERT INTO quote_responses (quote_id,seller_id,price_per_kg,total_amount,eta_days) "
                   "VALUES (?,?,?,?,?)", (qid, s["seller_id"], price, round(price * qty, 0), eta))
    return jsonify({"ok": True, "quote_id": qid})


@bp.post("/quotes/<int:qid>/accept/<int:rid>")
@role_required("buyer")
def accept_quote(qid, rid):
    q = db.query("SELECT * FROM quotes WHERE id=? AND buyer_id=?", (qid, g.user["id"]), one=True)
    resp = db.query("SELECT * FROM quote_responses WHERE id=? AND quote_id=?", (rid, qid), one=True)
    if not q or not resp:
        return jsonify({"ok": False, "error": "Quote not found"}), 404
    product = db.query("SELECT id FROM products WHERE seller_id=? AND crop=? AND status='active' "
                       "ORDER BY id LIMIT 1", (resp["seller_id"], q["crop"]), one=True)
    if not product:
        return jsonify({"ok": False, "error": "Seller listing unavailable"}), 400
    oid, err = place_order(g.user["id"], [(product["id"], min(q["quantity_kg"], 20000))],
                           f"{g.user['city']} — bulk dock", g.user["city"], "", "Bank Transfer")
    if err:
        return jsonify({"ok": False, "error": err}), 400
    db.execute("UPDATE quote_responses SET status='accepted' WHERE id=?", (rid,))
    db.execute("UPDATE quote_responses SET status='declined' WHERE quote_id=? AND id<>?", (qid, rid))
    db.execute("UPDATE quotes SET status='converted' WHERE id=?", (qid,))
    return jsonify({"ok": True, "order_id": oid})


# ------------------------------------------------------------------ Admin
@bp.get("/admin/stats")
@role_required("admin")
def admin_stats():
    kpi = {
        "users": db.query("SELECT COUNT(*) n FROM users", one=True)["n"],
        "orders": db.query("SELECT COUNT(*) n FROM orders", one=True)["n"],
        "gmv": db.query("SELECT COALESCE(SUM(total_amount),0) v FROM orders", one=True)["v"],
        "active": db.query("SELECT COUNT(*) n FROM products WHERE status='active'", one=True)["n"],
    }
    return jsonify(kpi)


@bp.post("/admin/users/<int:uid>/toggle")
@role_required("admin")
def admin_toggle_user(uid):
    u = db.query("SELECT * FROM users WHERE id=?", (uid,), one=True)
    if not u or u["role"] == "admin":
        return jsonify({"ok": False, "error": "Cannot modify this account"}), 400
    db.execute("UPDATE users SET active=? WHERE id=?", (0 if u["active"] else 1, uid))
    return jsonify({"ok": True, "active": 0 if u["active"] else 1})


@bp.post("/admin/products/<int:pid>/status")
@role_required("admin")
def admin_product_status(pid):
    data = request.get_json(silent=True) or request.form
    status = data.get("status")
    if status not in ("active", "removed"):
        return jsonify({"ok": False, "error": "Invalid status"}), 400
    db.execute("UPDATE products SET status=? WHERE id=?", (status, pid))
    return jsonify({"ok": True})
