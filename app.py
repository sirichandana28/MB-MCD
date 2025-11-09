from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from flask_bcrypt import Bcrypt
from pymongo import MongoClient
import os
import datetime
from werkzeug.utils import secure_filename
from PIL import Image
import requests
import urllib.parse

app = Flask(__name__, static_folder='frontend/static')
CORS(app)
bcrypt = Bcrypt(app)

# -------------------------
# 🔹 Upload folder setup
# -------------------------
UPLOAD_FOLDER = "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

# -------------------------
# 🔹 MongoDB Atlas Connection
# -------------------------
username_atlas = "plant_user_18"
password_atlas = urllib.parse.quote_plus("Test1234!Test")  # URL-encode if special chars
client = MongoClient(
    f"mongodb+srv://{username_atlas}:{password_atlas}@cluster0.i5lhstg.mongodb.net/?retryWrites=true&w=majority"
)
db = client["cropcare_ai"]
users = db["users"]
results = db["results"]

# -------------------------
# 🔹 Serve HTML pages
# -------------------------
@app.route("/")
def serve_home():
    """Landing home page"""
    return send_from_directory("frontend", "home.html")

@app.route("/login")
def serve_login():
    return send_from_directory("frontend", "login.html")

@app.route("/register")
def serve_register():
    return send_from_directory("frontend", "registration.html")

@app.route("/index")
def serve_index():
    return send_from_directory("frontend", "index.html")

@app.route("/forgot_password")
def serve_forgot_password():
    return send_from_directory("frontend", "forgot_password.html")

@app.route("/pastresults")
def serve_pastresults():
    return send_from_directory("frontend", "pastresults.html")

@app.route("/<path:path>")
def serve_frontend(path):
    return send_from_directory("frontend", path)

# -------------------------
# 🔹 Registration
# -------------------------
@app.route("/api/register", methods=["POST"])
def register_user():
    data = request.get_json()
    username = data.get("username")
    password = data.get("password")

    if not username or not password:
        return jsonify({"message": "Username and password required"}), 400

    if users.find_one({"username": username}):
        return jsonify({"message": "Username already taken!"}), 409

    hashed_pw = bcrypt.generate_password_hash(password).decode("utf-8")
    users.insert_one({
        "username": username,
        "password": hashed_pw,
        "createdAt": datetime.datetime.utcnow()
    })
    return jsonify({"message": "User registered successfully!"}), 201

# -------------------------
# 🔹 Login
# -------------------------
@app.route("/api/login", methods=["POST"])
def login_user():
    data = request.get_json()
    username = data.get("username")
    password = data.get("password")

    user = users.find_one({"username": username})
    if not user or not bcrypt.check_password_hash(user["password"], password):
        return jsonify({"message": "Invalid credentials!"}), 401

    return jsonify({
        "message": "Login successful",
        "user": {"username": username}
    }), 200

# -------------------------
# 🔹 Reset Password
# -------------------------
@app.route("/api/reset-password", methods=["POST"])
def reset_password():
    data = request.get_json()
    username = data.get("username")
    new_password = data.get("new_password")

    if not username or not new_password:
        return jsonify({"message": "Username and new password required"}), 400

    user = users.find_one({"username": username})
    if not user:
        return jsonify({"message": "Username not found!"}), 404

    hashed_pw = bcrypt.generate_password_hash(new_password).decode("utf-8")
    users.update_one({"username": username}, {"$set": {"password": hashed_pw}})
    return jsonify({"message": "Password successfully reset!"}), 200

# -------------------------
# 🔹 Prediction API (CDDM schema + Q/A)
# -------------------------
MODEL_URL = "http://127.0.0.1:8000/predict"  # optional external model

def _bullets(items):
    return "• " + "\n• ".join(items) if isinstance(items, list) else str(items)

@app.route("/predict", methods=["POST"])
def predict():
    """
    Save results under the correct username.
    Accept username from multipart/form-data or JSON; fallback to 'guest'.
    """
    # Accept from form-data or JSON body (robust)
    json_body = {}
    try:
        if request.is_json:
            json_body = request.get_json(silent=True) or {}
    except Exception:
        json_body = {}

    username = (
        request.form.get("username")
        or json_body.get("username")
        or "guest"
    )
    question = (request.form.get("question") or json_body.get("question") or "").strip()

    # Ensure there's an image (multipart/form-data)
    image_file = request.files.get("image")
    if image_file is None:
        return jsonify({"error": "No image uploaded"}), 400

    # Save image to disk
    filename = secure_filename(image_file.filename or f"upload_{int(datetime.datetime.utcnow().timestamp())}.jpg")
    filepath = os.path.join(app.config["UPLOAD_FOLDER"], filename)
    image_file.save(filepath)

    try:
        # Optional: compress/resize
        try:
            img = Image.open(filepath).convert("RGB")
            img.thumbnail((512, 512))
            img.save(filepath)
        except Exception:
            pass

        # Optional: call external model
        ai_result = None
        try:
            with open(filepath, "rb") as f:
                resp = requests.post(MODEL_URL, files={"image": f})
            if resp.ok:
                ai_result = resp.json()
        except Exception:
            ai_result = None

        # Build consistent CDDM-like object
        cddm = {
            "image_id": filename,
            "crop": "Tomato",
            "disease_name": "Early Blight",
            "scientific_name": "Alternaria solani",
            "symptoms": [
                "Dark brown concentric (target-like) spots on older leaves",
                "Yellowing and drying of lower leaves",
                "Dark, sunken lesions on stems near soil line",
                "Fruit shows dark, leathery spots near stem end"
            ],
            "causes": [
                "Fungal infection caused by Alternaria solani",
                "Warm and humid conditions (24–29°C)",
                "Splashing water spreading fungal spores from soil",
                "Overhead irrigation and poor air circulation",
                "Infected crop debris or seeds left in the field"
            ],
            "solutions": {
                "cultural": [
                    "Rotate crops; avoid planting tomato/potato in same field for 2–3 years",
                    "Use resistant or tolerant varieties",
                    "Water using drip irrigation, avoid wetting leaves",
                    "Apply mulch to reduce soil splash",
                    "Remove and destroy infected plant residues"
                ],
                "biological": [
                    "Apply bio-fungicides like Trichoderma harzianum or Bacillus subtilis"
                ],
                "chemical": [
                    "Spray copper oxychloride or chlorothalonil as protectant fungicide",
                    "Use azoxystrobin or mancozeb if infection is severe"
                ]
            },
            "prevention_summary": "Keep foliage dry, rotate crops, use resistant varieties, remove infected debris, and monitor weather for humid periods."
        }

        # Q/A extraction
        q = question.lower()
        qa_type = "summary"
        qa_answer = (
            f"{cddm['disease_name']} on {cddm['crop']} ({cddm['scientific_name']}).\n"
            f"Key symptom: {cddm['symptoms'][0]}\n"
            f"Prevention: {cddm['prevention_summary']}"
        )

        if any(k in q for k in ["symptom", "sign"]):
            qa_type = "symptoms"
            qa_answer = _bullets(cddm["symptoms"])
        elif any(k in q for k in ["cause", "reason", "why"]):
            qa_type = "causes"
            qa_answer = _bullets(cddm["causes"])
        elif "cultural" in q:
            qa_type = "solutions.cultural"
            qa_answer = _bullets(cddm["solutions"]["cultural"])
        elif "biological" in q or "bio" in q:
            qa_type = "solutions.biological"
            qa_answer = _bullets(cddm["solutions"]["biological"])
        elif any(k in q for k in ["chemical", "spray", "fungicide", "medicine", "treat", "cure"]):
            qa_type = "solutions.chemical"
            qa_answer = _bullets(cddm["solutions"]["chemical"])
        elif any(k in q for k in ["solution", "treatment", "manage", "control"]):
            qa_type = "solutions"
            all_solutions = (
                ["CULTURAL:"] + cddm["solutions"]["cultural"] +
                ["", "BIOLOGICAL:"] + cddm["solutions"]["biological"] +
                ["", "CHEMICAL:"] + cddm["solutions"]["chemical"]
            )
            qa_answer = _bullets(all_solutions)
        elif any(k in q for k in ["prevent", "avoid", "prevention"]):
            qa_type = "prevention_summary"
            qa_answer = cddm["prevention_summary"]
        elif any(k in q for k in ["scientific", "species", "name"]):
            qa_type = "scientific_name"
            qa_answer = cddm["scientific_name"]

        response = {
            **cddm,
            "question": question,
            "qa_type": qa_type,
            "qa_answer": qa_answer
        }

        # Save result with ISO-convertible createdAt
        now = datetime.datetime.utcnow()
        results.insert_one({
            "user": username,
            "filename": filename,
            "prediction": {
                "disease": cddm["disease_name"],
                "confidence": 93  # fixed demo confidence
            },
            "record": response,
            "createdAt": now
        })

        # Cleanup local file
        try:
            if os.path.exists(filepath):
                os.remove(filepath)
        except Exception:
            pass

        return jsonify(response), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500

# -------------------------
# 🔹 Get Past Results
# -------------------------
@app.route("/api/past-results", methods=["GET"])
def get_past_results():
    username = request.args.get("username")
    if not username:
        return jsonify({"message": "Username is required"}), 400

    past = list(results.find({"user": username}).sort("createdAt", -1).limit(10))

    # Convert ObjectId and datetime to strings
    out = []
    for r in past:
        r["_id"] = str(r.get("_id"))
        if isinstance(r.get("createdAt"), datetime.datetime):
            r["createdAt"] = r["createdAt"].isoformat()
        out.append(r)

    return jsonify(out), 200

# -------------------------
# 🔹 Clear History
# -------------------------
@app.route("/api/clear-history", methods=["DELETE"])
def clear_history():
    username = request.args.get("username")
    if not username:
        return jsonify({"message": "Username is required"}), 400

    delete_result = results.delete_many({"user": username})
    return jsonify({
        "message": f"Deleted {delete_result.deleted_count} past results.",
        "deleted_count": delete_result.deleted_count
    }), 200

# -------------------------
# 🔹 Debug: counts by user (optional)
# -------------------------
@app.route("/api/debug-counts", methods=["GET"])
def debug_counts():
    pipeline = [
        {"$group": {"_id": "$user", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}}
    ]
    agg = list(results.aggregate(pipeline))
    # reshape for nicer JSON
    for a in agg:
        a["user"] = a.pop("_id")
    return jsonify(agg), 200

# -------------------------
# 🔹 Run Flask App
# -------------------------
if __name__ == "__main__":
    print("Connected to MongoDB:", client.list_database_names())
    app.run(debug=True, port=5000)
