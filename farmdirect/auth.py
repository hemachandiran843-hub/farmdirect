"""Authentication: register / login / logout with 4 user roles."""
import functools

from flask import (Blueprint, flash, g, redirect, render_template, request,
                   session, url_for)
from werkzeug.security import check_password_hash, generate_password_hash

import db

bp = Blueprint("auth", __name__)

ROLE_HOME = {
    "farmer": "views.farmer_dashboard", "fpo": "views.farmer_dashboard",
    "consumer": "views.consumer_dashboard", "buyer": "views.buyer_dashboard",
    "admin": "views.admin_dashboard",
}


@bp.before_app_request
def load_logged_in_user():
    uid = session.get("uid")
    g.user = None
    g.role = None
    if uid:
        row = db.query("SELECT * FROM users WHERE id=? AND active=1", (uid,), one=True)
        if row:
            g.user = row
            g.role = row["role"]
            # farmer/fpo profile enrichment
            if row["role"] in ("farmer", "fpo"):
                table = "fpos" if row["role"] == "fpo" else "farmers"
                g.profile = db.query(f"SELECT * FROM {table} WHERE user_id=?", (uid,), one=True)
            else:
                g.profile = None


def login_required(view):
    @functools.wraps(view)
    def wrapped(**kwargs):
        if g.user is None:
            return redirect(url_for("auth.login", next=request.path))
        return view(**kwargs)
    return wrapped


def role_required(*roles):
    def deco(view):
        @functools.wraps(view)
        def wrapped(**kwargs):
            if g.user is None:
                return redirect(url_for("auth.login", next=request.path))
            if g.role not in roles:
                flash("You do not have access to that page.", "warning")
                return redirect(url_for(ROLE_HOME.get(g.role, "views.landing")))
            return view(**kwargs)
        return wrapped
    return deco


@bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        password = request.form.get("password") or ""
        row = db.query("SELECT * FROM users WHERE lower(email)=?", (email,), one=True)
        if row and row["active"] and check_password_hash(row["password_hash"], password):
            session.clear()
            session["uid"] = row["id"]
            flash(f"Welcome back, {row['name'].split('—')[0].strip()}!", "success")
            nxt = request.args.get("next") or request.form.get("next")
            if nxt and nxt.startswith("/"):
                return redirect(nxt)
            return redirect(url_for(ROLE_HOME.get(row["role"], "views.landing")))
        flash("Invalid email or password.", "danger")
    return render_template("auth/login.html")


@bp.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        f = request.form
        name = (f.get("name") or "").strip()
        email = (f.get("email") or "").strip().lower()
        password = f.get("password") or ""
        role = f.get("role") or "consumer"
        city = (f.get("city") or "Nashik").strip()
        state = (f.get("state") or "Maharashtra").strip()

        if not name or not email or len(password) < 4:
            flash("Please fill name, a valid email and a 4+ char password.", "danger")
        elif db.query("SELECT id FROM users WHERE lower(email)=?", (email,), one=True):
            flash("That email is already registered — try logging in.", "warning")
        else:
            pw = generate_password_hash(password)
            uid = db.execute(
                "INSERT INTO users (name,email,phone,password_hash,role,city,state) "
                "VALUES (?,?,?,?,?,?,?)",
                (name, email, f.get("phone") or "", pw, role, city, state))
            if role == "farmer":
                db.execute("INSERT INTO farmers (user_id,farm_name,farm_size_acres,crops_grown,bio) "
                           "VALUES (?,?,?,?,?)",
                           (uid, f.get("farm_name") or f"{name}'s Farm",
                            float(f.get("farm_size") or 2.0),
                            f.get("crops_grown") or "", f.get("bio") or ""))
            elif role == "fpo":
                db.execute("INSERT INTO fpos (user_id,fpo_name,member_count,district,state,description) "
                           "VALUES (?,?,?,?,?,?)",
                           (uid, f.get("fpo_name") or f"{name} FPO",
                            int(f.get("member_count") or 25), city, state, ""))
            session.clear()
            session["uid"] = uid
            flash("Account created — welcome to FarmDirect! 🌱", "success")
            return redirect(url_for(ROLE_HOME.get(role, "views.landing")))
    return render_template("auth/register.html")


@bp.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.", "info")
    return redirect(url_for("views.landing"))
