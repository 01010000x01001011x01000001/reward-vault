import os
import sqlite3
import time
import secrets
from datetime import timedelta
from flask import Flask, render_template, request, redirect, url_for, session, jsonify
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)

app.secret_key = os.environ.get("SECRET_KEY") or secrets.token_hex(32)

app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=30)
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['SESSION_COOKIE_HTTPONLY'] = True

DB_FILE = "database.db"

# Minimum seconds required between ad rewards (spam limit)
AD_COOLDOWN_SECONDS = 5

# Minimum seconds the ad must be open (visible) before a reward can be claimed.
# This should match/exceed the real duration of whatever ad unit you embed.
MIN_WATCH_SECONDS = 20

# How long an issued ad-watch token stays valid before it expires (anti-replay)
TOKEN_TTL_SECONDS = 120

# Passwords must be LONGER than 6 characters, i.e. at least 7.
MIN_PASSWORD_LENGTH = 7

# ---- Charity model -------------------------------------------------------
# Share of the ad revenue that is pledged to the cause the user picked.
# This number is shown to users on the site, so it must be the real figure.
CHARITY_SHARE = 0.50

# Rough revenue per completed view, used ONLY for the "raised (est.)" display.
# Replace it with real numbers from your ad network once you have them.
EST_REVENUE_PER_VIEW = 0.006

# Cause ids. Display names are translated in templates/index.html (cause_<id>).
CAUSES = ("hunger", "disaster", "health", "education")
DEFAULT_CAUSE = "hunger"

# Who actually receives each cause's money. Set real, named recipients
# before launch; monthly_report.py prints these next to the amounts.
RECIPIENTS = {c: "SET A NAMED RECIPIENT" for c in CAUSES}

def get_db():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_db() as conn:
        conn.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,
                balance REAL DEFAULT 0.00,
                theme_dark INTEGER NOT NULL DEFAULT 1
            )
        ''')

        conn.execute('''
            CREATE TABLE IF NOT EXISTS ad_views (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                cause TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%d %H:%M:%S','now'))
            )
        ''')

        # Migration: add theme_dark to existing databases created before this column existed
        existing_cols = [row["name"] for row in conn.execute("PRAGMA table_info(users)")]
        if "theme_dark" not in existing_cols:
            conn.execute("ALTER TABLE users ADD COLUMN theme_dark INTEGER NOT NULL DEFAULT 1")

        if "cause" not in existing_cols:
            conn.execute("ALTER TABLE users ADD COLUMN cause TEXT NOT NULL DEFAULT 'hunger'")

        # The built-in "admin" account (password "admin123") is no longer created.
        # If an older database still contains that default account, remove it.
        # An account that is merely named "admin" but has a different password is kept.
        legacy = conn.execute(
            "SELECT id, password FROM users WHERE username = ?", ("admin",)
        ).fetchone()
        if legacy and check_password_hash(legacy["password"], "admin123"):
            conn.execute("DELETE FROM users WHERE id = ?", (legacy["id"],))
        conn.commit()

init_db()

@app.route("/")
def index():
    user = {"id": 0, "username": "Guest", "balance": 0.00, "theme_dark": 1, "cause": DEFAULT_CAUSE, "views": 0, "raised": 0.0}
    
    if "user_id" in session:
        with get_db() as conn:
            db_user = conn.execute(
                "SELECT id, username, balance, theme_dark, cause FROM users WHERE id = ?", 
                (session["user_id"],)
            ).fetchone()
            if db_user:
                user = dict(db_user)
                user["views"] = conn.execute(
                    "SELECT COUNT(*) FROM ad_views WHERE user_id = ?", (db_user["id"],)
                ).fetchone()[0]
                user["raised"] = user["views"] * EST_REVENUE_PER_VIEW * CHARITY_SHARE
            else:
                session.pop("user_id", None)

    login_error = request.args.get("login_error")
    if login_error not in ("no_account", "wrong_password"):
        login_error = None

    register_error = request.args.get("register_error")
    if register_error not in ("password_short", "username_taken"):
        register_error = None

    return render_template("index.html", user=user, login_error=login_error, register_error=register_error,
                           causes=CAUSES, charity_percent=round(CHARITY_SHARE * 100))

@app.route("/cause/set", methods=["POST"])
def cause_set():
    if "user_id" not in session:
        return jsonify({"status": "error", "message": "Not logged in."}), 401
    cause = (request.get_json(silent=True) or {}).get("cause")
    if cause not in CAUSES:
        return jsonify({"status": "error", "message": "Unknown cause."}), 400
    with get_db() as conn:
        conn.execute("UPDATE users SET cause = ? WHERE id = ?", (cause, session["user_id"]))
        conn.commit()
    return jsonify({"status": "success"}), 200

@app.route("/theme/set", methods=["POST"])
def theme_set():
    if "user_id" not in session:
        return jsonify({"status": "error", "message": "Not logged in."}), 401

    data = request.get_json(silent=True) or {}
    dark = 1 if data.get("dark") else 0

    with get_db() as conn:
        conn.execute(
            "UPDATE users SET theme_dark = ? WHERE id = ?",
            (dark, session["user_id"])
        )
        conn.commit()

    return jsonify({"status": "success", "theme_dark": dark}), 200

@app.route("/register", methods=["POST"])
def register():
    # Honeypot Check: If hidden field is filled out, it's a bot
    if request.form.get("website_hp"):
        return redirect(url_for("index"))

    username = request.form.get("username", "").strip()
    password = request.form.get("password", "").strip()

    if password and len(password) < MIN_PASSWORD_LENGTH:
        return redirect(url_for("index", register_error="password_short"))

    if username and password:
        try:
            with get_db() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "INSERT INTO users (username, password, balance, theme_dark) VALUES (?, ?, 0.00, 1)",
                    (username, generate_password_hash(password))
                )
                conn.commit()
                session["user_id"] = cursor.lastrowid
                session.permanent = True
        except sqlite3.IntegrityError:
            return redirect(url_for("index", register_error="username_taken")) 

    return redirect(url_for("index"))

@app.route("/login", methods=["POST"])
def login():
    # Honeypot Check: Drop request if bot filled out honeypot field
    if request.form.get("website_hp"):
        return redirect(url_for("index"))

    username = request.form.get("username", "").strip()
    password = request.form.get("password", "").strip()
    remember = request.form.get("remember")

    with get_db() as conn:
        user = conn.execute(
            "SELECT id, password FROM users WHERE username = ?",
            (username,)
        ).fetchone()

        if not user:
            return redirect(url_for("index", login_error="no_account"))

        if not check_password_hash(user["password"], password):
            return redirect(url_for("index", login_error="wrong_password"))

        session["user_id"] = user["id"]
        session.permanent = bool(remember)

    return redirect(url_for("index"))

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))

@app.route("/ad/start", methods=["POST"])
def ad_start():
    """
    Called the moment the ad is displayed to the user (ad actually rendered
    in-page, not just a link opened). Issues a one-time token binding this
    specific ad impression to a start timestamp. No reward is granted here.
    """
    if "user_id" not in session:
        return jsonify({"status": "error", "message": "You must be logged in to watch ads."}), 401

    now = time.time()
    last_watch_time = session.get("last_ad_time", 0)
    time_passed = now - last_watch_time

    if time_passed < AD_COOLDOWN_SECONDS:
        remaining = int(AD_COOLDOWN_SECONDS - time_passed)
        return jsonify({
            "status": "error",
            "message": f"Cooldown active. Please wait {remaining} seconds."
        }), 429

    token = secrets.token_urlsafe(24)
    session["ad_token"] = token
    session["ad_token_started"] = now

    return jsonify({"status": "ok", "token": token, "min_watch_seconds": MIN_WATCH_SECONDS}), 200


@app.route("/ad/claim", methods=["POST"])
def ad_claim():
    """
    Called after the ad finishes (or the required watch duration elapses)
    with the token issued by /ad/start. Reward is only granted if:
      - the token matches what the server issued for this session
      - enough real wall-clock time has passed since /ad/start
      - the token hasn't expired or already been used
      - the page was actually visible for that duration (client reports this;
        this is a UX-level check, the server timing check above is what
        actually prevents abuse)
    """
    data = request.get_json(silent=True) or {}
    token = data.get("token")
    was_visible = bool(data.get("was_visible", False))

    if "user_id" not in session:
        return jsonify({"status": "error", "message": "You must be logged in to claim rewards."}), 401

    stored_token = session.get("ad_token")
    started_at = session.get("ad_token_started")

    if not stored_token or not started_at or token != stored_token:
        return jsonify({"status": "error", "message": "Invalid or expired ad session."}), 400

    elapsed = time.time() - started_at

    # Invalidate the token immediately so it can't be replayed
    session.pop("ad_token", None)
    session.pop("ad_token_started", None)

    if elapsed > TOKEN_TTL_SECONDS:
        return jsonify({"status": "error", "message": "Ad session expired."}), 400

    if elapsed < MIN_WATCH_SECONDS:
        return jsonify({"status": "error", "message": "Ad was not watched long enough."}), 400

    if not was_visible:
        return jsonify({"status": "error", "message": "Ad tab was not visible for the full duration."}), 400

    session["last_ad_time"] = time.time()

    with get_db() as conn:
        row = conn.execute("SELECT cause FROM users WHERE id = ?", (session["user_id"],)).fetchone()
        conn.execute(
            "INSERT INTO ad_views (user_id, cause) VALUES (?, ?)",
            (session["user_id"], row["cause"] if row else DEFAULT_CAUSE)
        )
        conn.commit()
        views = conn.execute(
            "SELECT COUNT(*) FROM ad_views WHERE user_id = ?", (session["user_id"],)
        ).fetchone()[0]

    raised = views * EST_REVENUE_PER_VIEW * CHARITY_SHARE
    return jsonify({"status": "success", "views": views, "raised": f"{raised:.2f}"}), 200

if __name__ == "__main__":
    app.run(debug=True)
