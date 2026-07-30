import os
import sqlite3
from flask import Flask, render_template, request, redirect, url_for, session, jsonify

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "rewardvault_secret_key_123")

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
        conn.commit()

init_db()

@app.route("/")
def index():
    user = {"id": 0, "username": "Guest", "balance": 0.00}
    
    if "user_id" in session:
        with get_db() as conn:
            db_user = conn.execute(
                "SELECT id, username, balance FROM users WHERE id = ?", 
                (session["user_id"],)
            ).fetchone()
            if db_user:
                user = dict(db_user)

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
        except sqlite3.IntegrityError:
            pass  # Username already exists

    return redirect(url_for("index"))

@app.route("/login", methods=["POST"])
def login():
    username = request.form.get("username", "").strip()
    password = request.form.get("password", "").strip()

    with get_db() as conn:
        user = conn.execute(
            "SELECT id FROM users WHERE username = ? AND password = ?", 
            (username, password)
        ).fetchone()
        
        if user:
            session["user_id"] = user["id"]

    return redirect(url_for("index"))

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))

@app.route("/watch-ad", methods=["POST"])
def watch_ad():
    if "user_id" in session:
        with get_db() as conn:
            conn.execute(
                "UPDATE users SET balance = balance + 0.05 WHERE id = ?",
                (session["user_id"],)
            )
            conn.commit()
        return jsonify({"status": "success"}), 200
    else:
        # Credit guest session if not logged in
        session["guest_balance"] = session.get("guest_balance", 0.0) + 0.05
        return jsonify({"status": "success", "message": "Guest balance updated"}), 200

if __name__ == "__main__":
    app.run(debug=True)
