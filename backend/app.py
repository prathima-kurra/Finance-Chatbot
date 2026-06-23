from flask import Flask, request, jsonify
from flask_cors import CORS
from flask_jwt_extended import (
    JWTManager, create_access_token,
    jwt_required, get_jwt_identity
)
from groq import Groq
import bcrypt
import csv
import io
import json
from database import init_db, get_db
from dotenv import load_dotenv
import os

load_dotenv()

app = Flask(__name__)
CORS(app, origins=[
    "http://localhost:5173",    #local react frontend
    "https://finance-chatbot-green.vercel.app" #deployed react frontend
])

app.config["JWT_SECRET_KEY"] = os.environ.get("JWT_SECRET_KEY","fallback-key")  # change this to anything random
jwt = JWTManager(app)

client = Groq(api_key=os.environ.get("GROQ_API_KEY"))  # your groq key

# Initialize database on startup
init_db()


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

    # Hash the password before storing
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

    # Check password against stored hash
    if not bcrypt.checkpw(password.encode("utf-8"), user["password"].encode("utf-8")):
        return jsonify({"error": "Invalid email or password"}), 401

    # Create a JWT token — this is what the frontend stores to stay logged in
    token = create_access_token(identity=str(user["id"]))
    return jsonify({"token": token, "email": email})


# ─────────────────────────────────────────
#  UPLOAD ROUTE
# ─────────────────────────────────────────

@app.route("/upload", methods=["POST"])
@jwt_required()  # only logged in users can upload
def upload_file():
    user_id = get_jwt_identity()  # gets the logged-in user's ID from token
    file = request.files.get("file")

    if not file:
        return jsonify({"error": "No file uploaded"}), 400

    content = file.read().decode("utf-8")

    if file.filename.endswith(".csv"):
        reader = csv.DictReader(io.StringIO(content))
        transactions = [row for row in reader]
    else:
        transactions = [{"raw": line} for line in content.splitlines() if line.strip()]

    # Save transactions to database for this user
    conn = get_db()
    # Delete old transactions for this user first
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
#  CHAT ROUTE
# ─────────────────────────────────────────

@app.route("/chat", methods=["POST"])
@jwt_required()
def chat():
    user_id = get_jwt_identity()
    data = request.json
    user_question = data.get("question", "")
    chat_history = data.get("history", [])

    # Load this user's transactions from database
    conn = get_db()
    row = conn.execute(
        "SELECT data FROM transactions WHERE user_id = ? ORDER BY uploaded_at DESC LIMIT 1",
        (user_id,)
    ).fetchone()

    if not row:
        return jsonify({"answer": "Please upload a CSV or text file first."})

    transactions = json.loads(row["data"])

    # Save this message to chat history
    conn.execute(
        "INSERT INTO chat_history (user_id, role, message) VALUES (?, ?, ?)",
        (user_id, "user", user_question)
    )
    conn.commit()

    tx_text = "\n".join(
        ", ".join(f"{k}: {v}" for k, v in t.items())
        for t in transactions
    )

    system_prompt = f"""You are a personal finance assistant.
The user uploaded their transaction data below.
Answer questions clearly based only on this data.
Do calculations if needed. Format numbers as currency (e.g. $45.00).
Be concise and helpful.

--- TRANSACTION DATA ---
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
#  GET SAVED CHAT HISTORY
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