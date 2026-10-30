"""Central backend for the AI Study pages."""

import os
import re
from pathlib import Path

import mysql.connector
from flask import Flask, jsonify, request, send_from_directory, session
from mysql.connector import IntegrityError
from werkzeug.security import check_password_hash, generate_password_hash

from AI_Study_Assistant import ask_gemini


BASE_DIR = Path(__file__).resolve().parent
PROJECT_DIR = BASE_DIR.parent
app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get(
    "SECRET_KEY", "ai-study-development-secret-key"
)
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"


def get_db():
    return mysql.connector.connect(
        host=os.environ.get("MYSQL_HOST", "127.0.0.1"),
        port=int(os.environ.get("MYSQL_PORT", "3306")),
        user=os.environ.get("MYSQL_USER", "root"),
        password=os.environ.get("MYSQL_PASSWORD", "root"),
        database=os.environ.get("MYSQL_DATABASE", "ai_study"),
    )


def initialise_database():
    connection = get_db()
    try:
        cursor = connection.cursor()
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
                full_name VARCHAR(120) NOT NULL,
                email VARCHAR(254) NOT NULL,
                password_hash VARCHAR(255) NOT NULL,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (id),
                UNIQUE KEY uq_users_email (email)
            )
            ENGINE = InnoDB
            """
        )
        connection.commit()
    finally:
        connection.close()


def json_error(message, status_code):
    return jsonify({"success": False, "error": message}), status_code


initialise_database()


@app.after_request
def add_cors_headers(response):
    origin = request.headers.get("Origin")
    if origin and (
        origin == "null"
        or origin.startswith("http://localhost:")
        or origin.startswith("http://127.0.0.1:")
    ):
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Access-Control-Allow-Credentials"] = "true"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type"
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    return response


@app.route("/", methods=["GET"])
@app.route("/frontpage", methods=["GET"])
@app.route("/frontpage.html", methods=["GET"])
def home():
    return send_from_directory(PROJECT_DIR / "front_page", "frontpage.html")


@app.route("/about", methods=["GET"])
@app.route("/about.html", methods=["GET"])
def about_page():
    return send_from_directory(PROJECT_DIR / "front_page", "about.html")


@app.route("/login", methods=["GET"])
@app.route("/login.html", methods=["GET"])
def login_page():
    return send_from_directory(PROJECT_DIR / "login_page", "login.html")


@app.route("/register", methods=["GET"])
@app.route("/register.html", methods=["GET"])
def register_page():
    return send_from_directory(PROJECT_DIR / "login_page", "register.html")


@app.route("/dashboard", methods=["GET"])
@app.route("/dashboard.html", methods=["GET"])
def dashboard_page():
    if session.get("user_id") is None:
        return login_page()
    return send_from_directory(PROJECT_DIR / "front_page", "student.html")


@app.route("/api/register", methods=["OPTIONS"])
@app.route("/api/login", methods=["OPTIONS"])
@app.route("/api/logout", methods=["OPTIONS"])
@app.route("/api/ai/ask", methods=["OPTIONS"])
def api_options():
    return ("", 204)


@app.route("/api/register", methods=["POST"])
def register():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return json_error("Request body must be valid JSON.", 400)

    full_name = str(data.get("full_name", "")).strip()
    email = str(data.get("email", "")).strip().lower()
    password = str(data.get("password", ""))

    if not full_name or not email or not password:
        return json_error("Full name, email and password are required.", 400)
    if len(full_name) > 120:
        return json_error("Full name must be 120 characters or fewer.", 400)
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        return json_error("Please enter a valid email address.", 400)
    if len(password) < 8:
        return json_error("Password must contain at least 8 characters.", 400)

    try:
        connection = get_db()
        try:
            cursor = connection.cursor()
            cursor.execute(
                """
                INSERT INTO users (full_name, email, password_hash)
                VALUES (%s, %s, %s)
                """,
                (full_name, email, generate_password_hash(password)),
            )
            connection.commit()
        finally:
            connection.close()
    except IntegrityError:
        return json_error("An account with this email already exists.", 409)

    return jsonify(
        {"success": True, "message": "Account created successfully."}
    ), 201


@app.route("/api/login", methods=["POST"])
def login():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return json_error("Request body must be valid JSON.", 400)

    email = str(data.get("email", "")).strip().lower()
    password = str(data.get("password", ""))
    if not email or not password:
        return json_error("Email and password are required.", 400)

    connection = get_db()
    try:
        cursor = connection.cursor(dictionary=True)
        cursor.execute(
            """
            SELECT id, full_name, email, password_hash
            FROM users
            WHERE email = %s
            """,
            (email,),
        )
        user = cursor.fetchone()
    finally:
        connection.close()

    if user is None or not check_password_hash(user["password_hash"], password):
        return json_error("Invalid email or password.", 401)

    session["user_id"] = user["id"]
    return jsonify(
        {
            "success": True,
            "message": "Login successful.",
            "user": {
                "id": user["id"],
                "full_name": user["full_name"],
                "email": user["email"],
            },
        }
    )


@app.route("/api/me", methods=["GET"])
def current_user():
    user_id = session.get("user_id")
    if user_id is None:
        return json_error("You are not logged in.", 401)

    connection = get_db()
    try:
        cursor = connection.cursor(dictionary=True)
        cursor.execute(
            "SELECT id, full_name, email FROM users WHERE id = %s",
            (user_id,),
        )
        user = cursor.fetchone()
    finally:
        connection.close()

    if user is None:
        session.clear()
        return json_error("User account was not found.", 401)

    return jsonify({"success": True, "user": dict(user)})


@app.route("/api/dashboard", methods=["GET"])
def dashboard_data():
    user_id = session.get("user_id")
    if user_id is None:
        return json_error("You are not logged in.", 401)

    connection = get_db()
    try:
        cursor = connection.cursor(dictionary=True)
        cursor.execute(
            "SELECT id, full_name, email FROM users WHERE id = %s",
            (user_id,),
        )
        user = cursor.fetchone()
    finally:
        connection.close()

    if user is None:
        session.clear()
        return json_error("User account was not found.", 401)

    seed = int(user["id"])
    courses = [
        {
            "title": "Python for Data Science",
            "category": "Programming",
            "progress": (seed * 17) % 46 + 45,
            "lessons": 24,
            "color": "violet",
        },
        {
            "title": "Statistics Fundamentals",
            "category": "Mathematics",
            "progress": (seed * 11) % 41 + 32,
            "lessons": 18,
            "color": "blue",
        },
        {
            "title": "Academic Writing",
            "category": "Communication",
            "progress": (seed * 7) % 36 + 54,
            "lessons": 12,
            "color": "orange",
        },
    ]
    tasks = [
        {"id": 1, "title": "Finish probability quiz", "course": "Statistics Fundamentals", "due": "Today", "done": False},
        {"id": 2, "title": "Review Python functions", "course": "Python for Data Science", "due": "Tomorrow", "done": False},
        {"id": 3, "title": "Draft essay introduction", "course": "Academic Writing", "due": "Friday", "done": False},
    ]
    return jsonify(
        {
            "success": True,
            "user": user,
            "stats": {
                "weekly_progress": (seed * 9) % 25 + 64,
                "study_hours": (seed * 3) % 8 + 6,
                "completed_tasks": (seed * 2) % 7 + 4,
                "streak": (seed * 5) % 12 + 3,
            },
            "courses": courses,
            "tasks": tasks,
        }
    )


@app.route("/api/ai/ask", methods=["POST"])
def ai_ask():
    if session.get("user_id") is None:
        return json_error("You are not logged in.", 401)

    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return json_error("Request body must be valid JSON.", 400)

    question = str(data.get("question", "")).strip()
    if not question:
        return json_error("Please enter a question.", 400)
    if len(question) > 2000:
        return json_error("Question must be 2000 characters or fewer.", 400)

    answer, error_message = ask_gemini(question)
    if error_message:
        status_code = 503 if "not configured" in error_message else 502
        return json_error(error_message, status_code)
    return jsonify({"success": True, "answer": answer})


@app.route("/api/logout", methods=["POST"])
def logout():
    session.clear()
    return jsonify({"success": True, "message": "Logged out successfully."})


if __name__ == "__main__":
    app.run(
        host="127.0.0.1",
        port=int(os.environ.get("PORT", "5000")),
        debug=True,
    )
