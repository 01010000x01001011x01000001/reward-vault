from flask import Flask, render_template, request, redirect, url_for
import sqlite3

app = Flask(__name__)

def init_db():
    """Initializes the database table and creates a test user if one doesn't exist."""
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    
    # Standard SQL table creation
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE,
            balance REAL
        )
    ''')
    
    # Add our early tester user with $0.00 starting balance if not already present
    cursor.execute('''
        INSERT OR IGNORE INTO users (id, username, balance) 
        VALUES (1, 'EarlyTester', 0.00)
    ''')
    
    conn.commit()
    conn.close()

@app.route('/')
def home():
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    
    # Query the user's current data from the SQL table
    cursor.execute("SELECT username, balance FROM users WHERE id = 1")
    row = cursor.fetchone()
    conn.close()
    
    user_data = {
        "username": row[0],
        "balance": row[1]
    }
    return render_template('index.html', user=user_data)

@app.route('/watch-ad', methods=['POST'])
def watch_ad():
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    
    # Execute an UPDATE query to safely increment the balance in SQL
    cursor.execute("UPDATE users SET balance = balance + 0.05 WHERE id = 1")
    conn.commit()
    conn.close()
    
    return redirect(url_for('home'))

if __name__ == '__main__':
    # Build database on startup
    init_db()
    app.run(debug=True, port=5001)
