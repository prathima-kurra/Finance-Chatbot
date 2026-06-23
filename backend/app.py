from flask import Flask, request, jsonify
from flask_cors import CORS
from flask_jwt_extended import (
    JWTManager, create_access_token,
    jwt_required, get_jwt_identity
)
from groq import Groq
from dotenv import load_dotenv
import os
import bcrypt
import csv
import io
import json
from database import init_db, get_db

load_dotenv()

app = Flask(__name__)
CORS(app, origins="*")

app.config["JWT_SECRET_KEY"] = os.environ.get("JWT_SECRET_KEY", "fallback-key")
jwt = JWTManager(app)

client = Groq(api_key=os.environ.get("GROQ_API_KEY"))

init_db()


# ─────────────────────────────────────────
#  PING ROUTE
# ─────────────────────────────────────────

@app.route("/ping", methods=["GET"])
def ping():
    return jsonify({"status": "awake"})


# ─────────────────────────────────────────
#  AUTH ROUTES
# ─────────────────────────────────────────

@app.route("/register", methods=["POST"])
def register():
    data = request.json
    email = data.get("email", "").strip().lower()
    password = data.get("password", "")

    if not email or not password:
        return jsonify({"error": "Email and password are required"}), 400

    if len(password) < 6:
        return jsonify({"error": "Password must be at least 6 characters"}), 400

    hashed = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt())

    conn = get_db()
    try:
        conn.execute(
            "INSERT INTO users (email, password) VALUES (?, ?)",
            (email, hashed.decode("utf-8"))
        )
        conn.commit()
        return jsonify({"message": "Account created! Please log in."})
    except Exception:
        return jsonify({"error": "Email already exists"}), 409
    finally:
        conn.close()


@app.route("/login", methods=["POST"])
def login():
    data = request.json
    email = data.get("email", "").strip().lower()
    password = data.get("password", "")

    conn = get_db()
    user = conn.execute(
        "SELECT * FROM users WHERE email = ?", (email,)
    ).fetchone()
    conn.close()

    if not user:
        return jsonify({"error": "Invalid email or password"}), 401

    if not bcrypt.checkpw(password.encode("utf-8"), user["password"].encode("utf-8")):
        return jsonify({"error": "Invalid email or password"}), 401

    token = create_access_token(identity=str(user["id"]))
    return jsonify({"token": token, "email": email})


# ─────────────────────────────────────────
#  UPLOAD ROUTE
# ─────────────────────────────────────────

@app.route("/upload", methods=["POST"])
@jwt_required()
def upload_file():
    user_id = get_jwt_identity()
    file = request.files.get("file")

    if not file:
        return jsonify({"error": "No file uploaded"}), 400

    content = file.read().decode("utf-8")

    if file.filename.endswith(".csv"):
        reader = csv.DictReader(io.StringIO(content))
        transactions = [row for row in reader]
    else:
        transactions = [{"raw": line} for line in content.splitlines() if line.strip()]

    conn = get_db()
    conn.execute("DELETE FROM transactions WHERE user_id = ?", (user_id,))
    conn.execute(
        "INSERT INTO transactions (user_id, data, filename) VALUES (?, ?, ?)",
        (user_id, json.dumps(transactions), file.filename)
    )
    conn.commit()
    conn.close()

    return jsonify({
        "message": f"Uploaded {len(transactions)} transactions.",
        "count": len(transactions),
        "allTransactions": transactions,
        "preview": transactions[:3]
    })


# ─────────────────────────────────────────
#  HELPER: BUILD SUMMARY FOR AI
# ─────────────────────────────────────────

def build_summary(transactions):
    # Total spent
    total_spent = sum(float(t.get('amount', 0)) for t in transactions)

    # Category totals
    category_totals = {}
    for t in transactions:
        cat = t.get('category', 'Other')
        amount = float(t.get('amount', 0))
        category_totals[cat] = category_totals.get(cat, 0) + amount

    category_summary = "\n".join(
        f"  - {cat}: ${total:.2f}"
        for cat, total in sorted(category_totals.items(), key=lambda x: -x[1])
    )

    # Monthly totals
    monthly_totals = {}
    for t in transactions:
        date = t.get('date', '')
        if date:
            # gets "2024-01" from "2024-01-15"
            month = date[:7]
            amount = float(t.get('amount', 0))
            monthly_totals[month] = monthly_totals.get(month, 0) + amount

    monthly_summary = "\n".join(
        f"  - {month}: ${total:.2f}"
        for month, total in sorted(monthly_totals.items())
    )

    # Monthly category breakdown
    monthly_category = {}
    for t in transactions:
        date = t.get('date', '')
        cat = t.get('category', 'Other')
        amount = float(t.get('amount', 0))
        if date:
            month = date[:7]
            if month not in monthly_category:
                monthly_category[month] = {}
            monthly_category[month][cat] = monthly_category[month].get(cat, 0) + amount

    return total_spent, category_summary, monthly_summary


# ─────────────────────────────────────────
#  CHAT ROUTE
# ─────────────────────────────────────────

@app.route("/chat", methods=["POST"])
@jwt_required()
def chat():
    user_id = get_jwt_identity()
    data = request.json
    user_question = data.get("question", "")
    chat_history = data.get("history", [])

    conn = get_db()
    row = conn.execute(
        "SELECT data FROM transactions WHERE user_id = ? ORDER BY uploaded_at DESC LIMIT 1",
        (user_id,)
    ).fetchone()

    if not row:
        return jsonify({"answer": "Please upload a CSV or text file first."})

    transactions = json.loads(row["data"])

    # Save user message to chat history
    conn.execute(
        "INSERT INTO chat_history (user_id, role, message) VALUES (?, ?, ?)",
        (user_id, "user", user_question)
    )
    conn.commit()

    # Build transaction text
    tx_text = "\n".join(
        ", ".join(f"{k}: {v}" for k, v in t.items())
        for t in transactions
    )

    # Build pre-calculated summaries
    total_spent, category_summary, monthly_summary = build_summary(transactions)

    system_prompt = f"""You are a personal finance assistant.
Answer questions clearly based only on the data provided below.
Format numbers as currency (e.g. $45.00).
Be concise and helpful.
IMPORTANT: Always use the pre-calculated totals for accuracy. Do not try to manually add up transactions.

--- PRE-CALCULATED TOTALS (use these for accuracy) ---
Total Spent: ${total_spent:.2f}
Number of Transactions: {len(transactions)}

Category Breakdown (sorted by highest spend):
{category_summary}

Monthly Breakdown:
{monthly_summary}
--- END PRE-CALCULATED TOTALS ---

--- FULL TRANSACTION DATA ---
{tx_text}
--- END DATA ---"""

    messages = [{"role": "system", "content": system_prompt}]
    for msg in chat_history:
        messages.append({"role": msg["role"], "content": msg["text"]})
    messages.append({"role": "user", "content": user_question})

    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=messages,
        max_tokens=1024
    )

    answer = response.choices[0].message.content

    # Save assistant response to chat history
    conn.execute(
        "INSERT INTO chat_history (user_id, role, message) VALUES (?, ?, ?)",
        (user_id, "assistant", answer)
    )
    conn.commit()
    conn.close()

    return jsonify({"answer": answer})


# ─────────────────────────────────────────
#  CHAT HISTORY ROUTE
# ─────────────────────────────────────────

@app.route("/history", methods=["GET"])
@jwt_required()
def get_history():
    user_id = get_jwt_identity()
    conn = get_db()
    rows = conn.execute(
        "SELECT role, message FROM chat_history WHERE user_id = ? ORDER BY created_at ASC",
        (user_id,)
    ).fetchall()
    conn.close()

    history = [{"role": r["role"], "text": r["message"]} for r in rows]
    return jsonify({"history": history})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", debug=False, port=port)