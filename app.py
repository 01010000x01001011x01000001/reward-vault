-.  session.pop("ad_token_started", None)

    if elapsed > TOKEN_TTL_SECONDS:
        return jsonify({"status": "error", "message": "Ad session expired."}), 400

    if elapsed < MIN_WATCH_SECONDS:
        return jsonify({"status": "error", "message": "Ad was not watched long enough."}), 400

    if not was_visible:
        return jsonify({"status": "error", "message": "Ad tab was not visible for the full duration."}), 400

    session["last_ad_time"] = time.time()

    with get_db() as conn:
        conn.execute(
            "UPDATE users SET balance = balance + 0.05 WHERE id = ?",
            (session["user_id"],)
        )
        conn.commit()
        user = conn.execute("SELECT balance FROM users WHERE id = ?", (session["user_id"],)).fetchone()
        new_balance = user["balance"] if user else 0.00

    return jsonify({"status": "success", "new_balance": f"{new_balance:.2f}"}), 200

if __name__ == "__main__":
    app.run(debug=True)
