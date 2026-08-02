import os
import sqlite3
from datetime import timedelta
from flask import Flask, render_template, request, redirect, url_for, session, jsonify

app = Flask(__name__)

# Fixed secret key so user sessions remain valid across app restarts/re-deploys
app.secret_key = os.environ.get("SECRET_KEY", "rewardvault_super_secret_key_2026")

# Configure 30-day session retention for "Remember Me"
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=30)
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'

DB_FILE = "database.db"

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
                balance REAL DEFAULT 0.00
            )
        ''')
        
        # Seed default admin account if it does not exist
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM users WHERE username = ?", ("admin",))
        if not cursor.fetchone():
            cursor.execute(
                "INSERT INTO users (username, password, balance) VALUES (?, ?, ?)",
                ("admin", "admin123", 50.00)
            )
        conn.commit()

init_db()

@app.route("/")
def index():
    user = {"id": 0, "username": "Guest", "balance": session.get("guest_balance", 0.00)}
    
    if "user_id" in session:
        with get_db() as conn:
            db_user = conn.execute(
                "SELECT id, username, balance FROM users WHERE id = ?", 
                (session["user_id"],)
            ).fetchone()
            if db_user:
                user = dict(db_user)
            else:
                # Clear session if the user ID no longer exists in DB
                session.pop("user_id", None)

    return render_template("index.html", user=user)

@app.route("/register", methods=["POST"])
def register():
    username = request.form.get("username", "").strip()
    password = request.form.get("password", "").strip()

    if username and password:
        try:
            with get_db() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "INSERT INTO users (username, password, balance) VALUES (?, ?, 0.00)",
                    (username, password)
                )
                conn.commit()
                session["user_id"] = cursor.lastrowid
                session.permanent = True
        except sqlite3.IntegrityError:
            pass  # Username already taken

    return redirect(url_for("index"))

@app.route("/login", methods=["POST"])
def login():
    username = request.form.get("username", "").strip()
    password = request.form.get("password", "").strip()
    remember = request.form.get("remember")

    with get_db() as conn:
        user = conn.execute(
            "SELECT id FROM users WHERE username = ? AND password = ?", 
            (username, password)
        ).fetchone()
        
        if user:
            session["user_id"] = user["id"]
            session.permanent = bool(remember)

    return redirect(url_for("index"))

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))

@app.route("/watch-ad", methods=["POST"])
def watch_ad():
    new_balance = 0.00
    if "user_id" in session:
        with get_db() as conn:
            conn.execute(
                "UPDATE users SET balance = balance + 0.05 WHERE id = ?",
                (session["user_id"],)
            )
            conn.commit()
            user = conn.execute("SELECT balance FROM users WHERE id = ?", (session["user_id"],)).fetchone()
            if user:
                new_balance = user["balance"]
    else:
        current_guest = session.get("guest_balance", 0.00)
        new_balance = round(current_guest + 0.05, 2)
        session["guest_balance"] = new_balance

    return jsonify({"status": "success", "new_balance": f"{new_balance:.2f}"}), 200

if __name__ == "__main__":
    app.run(debug=True)
