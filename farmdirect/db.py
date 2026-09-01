"""SQLite database helpers for FarmDirect (stdlib sqlite3, no ORM)."""
import os
import sqlite3

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.environ.get("FARMDIRECT_DB", os.path.join(BASE_DIR, "data", "farmdirect.db"))
SCHEMA_PATH = os.path.join(BASE_DIR, "schema.sql")


def get_db():
    """Open a connection with dict-style row access. Caller must close."""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def query(sql, args=(), one=False):
    conn = get_db()
    try:
        rows = conn.execute(sql, args).fetchall()
        return (rows[0] if rows else None) if one else rows
    finally:
        conn.close()


def execute(sql, args=()):
    """Run one write statement and commit. Returns lastrowid."""
    conn = get_db()
    try:
        cur = conn.execute(sql, args)
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def executemany(sql, seq):
    conn = get_db()
    try:
        conn.executemany(sql, seq)
        conn.commit()
    finally:
        conn.close()


def init_db(force=False):
    """Create tables from schema.sql. With force=True, drop the DB file first."""
    if force and os.path.exists(DB_PATH):
        os.remove(DB_PATH)
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = get_db()
    try:
        with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
            conn.executescript(f.read())
        conn.commit()
    finally:
        conn.close()


def db_is_seeded():
    try:
        row = query("SELECT COUNT(*) AS n FROM users", one=True)
        return row and row["n"] > 0
    except sqlite3.OperationalError:
        return False
