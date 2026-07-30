from flask import Flask, render_template, request, redirect, url_for, session
import sqlite3

app = Flask(__name__)
app.secret_key = 'reward_vault_super_secret_key'  # Needed for user sessions

def init_db():
    """Creates database tables for permanent user profile storage."""
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            balance REAL DEFAULT 0.00
        )
    ''')
    conn.commit()
    conn.close()

# Initialize Database at startup
init_db()

def get_db():
    conn = sqlite3.connect('database.db')
    conn.row_factory = sqlite3.Row
    return conn

@app.route('/')
def home():
    user_id = session.get('user_id')
    user_data = {"id": 0, "username": "Guest", "balance": 0.00}

    if user_id:
        conn = get_db()
        user = conn.execute("SELECT id, username, balance FROM users WHERE id = ?", (user_id,)).fetchone()
        conn.close()
        if user:
            user_data = dict(user)

    return render_template('index.html', user=user_data)

@app.route('/register', methods=['POST'])
def register():
    username = request.form.get('username')
    password = request.form.get('password')

    if username and password:
        try:
            conn = get_db()
            cursor = conn.cursor()
            cursor.execute("INSERT INTO users (username, password, balance) VALUES (?, ?, 0.00)", (username, password))
            conn.commit()
            
            # Log the new user in automatically
            user_id = cursor.lastrowid
            session['user_id'] = user_id
            conn.close()
        except sqlite3.IntegrityError:
            # Username already exists
            pass

    return redirect(url_for('home'))

@app.route('/login', methods=['POST'])
def login():
    username = request.form.get('username')
    password = request.form.get('password')

    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE username = ? AND password = ?", (username, password)).fetchone()
    conn.close()

    if user:
        session['user_id'] = user['id']

    return redirect(url_for('home'))

@app.route('/logout')
def logout():
    """Clears the user session and redirects back to the homepage as Guest."""
    session.clear()
    return redirect(url_for('home'))

@app.route('/watch-ad', methods=['POST'])
def watch_ad():
    user_id = session.get('user_id')
    
    conn = get_db()
    if user_id:
        # Credit the logged-in user's balance in SQLite
        conn.execute("UPDATE users SET balance = balance + 0.05 WHERE id = ?", (user_id,))
    conn.commit()
    conn.close()

    return redirect(url_for('home'))

if __name__ == '__main__':
    app.run(debug=True, port=5001)
