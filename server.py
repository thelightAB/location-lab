from flask import Flask, request, jsonify, send_file, Response
from datetime import datetime, timezone
import sqlite3
import os
import base64
import hmac
from dotenv import load_dotenv

try:
    import psycopg
    from psycopg.rows import dict_row
except ImportError:
    psycopg = None
    dict_row = None


# =========================================================
# App Configuration
# =========================================================

app = Flask(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

load_dotenv(os.path.join(BASE_DIR, ".env"))

DATABASE = os.path.join(BASE_DIR, "dailysense.db")

DATABASE_URL = os.environ.get("DATABASE_URL")

app.config["MAX_CONTENT_LENGTH"] = 16 * 1024


# =========================================================
# Database Configuration
# =========================================================

def using_postgres():
    return bool(DATABASE_URL)


def get_db():

    # -----------------------------------------------------
    # PostgreSQL
    # -----------------------------------------------------

    if using_postgres():

        if psycopg is None:
            raise RuntimeError(
                "PostgreSQL driver is not installed."
            )

        return psycopg.connect(
            DATABASE_URL,
            row_factory=dict_row
        )

    # -----------------------------------------------------
    # SQLite
    # -----------------------------------------------------

    connection = sqlite3.connect(
        DATABASE,
        timeout=5
    )

    connection.row_factory = sqlite3.Row

    connection.execute(
        "PRAGMA foreign_keys = ON"
    )

    return connection


def db_query(query):
    """
    PostgreSQL uses %s placeholders.
    SQLite uses ? placeholders.

    Our application code uses ? everywhere,
    and this function adapts queries for PostgreSQL.
    """

    if using_postgres():
        return query.replace("?", "%s")

    return query


# =========================================================
# Database Initialization
# =========================================================

def init_db():

    connection = get_db()

    try:

        cursor = connection.cursor()

        # -------------------------------------------------
        # SQLite
        # -------------------------------------------------

        if not using_postgres():

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS readings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    age INTEGER NOT NULL,
                    gender TEXT NOT NULL,
                    situation TEXT NOT NULL,
                    focus TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS locations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    latitude REAL NOT NULL,
                    longitude REAL NOT NULL,
                    accuracy REAL,
                    created_at TEXT NOT NULL
                )
            """)

        # -------------------------------------------------
        # PostgreSQL
        # -------------------------------------------------

        else:

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS readings (
                    id BIGSERIAL PRIMARY KEY,
                    age INTEGER NOT NULL,
                    gender TEXT NOT NULL,
                    situation TEXT NOT NULL,
                    focus TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS locations (
                    id BIGSERIAL PRIMARY KEY,
                    latitude DOUBLE PRECISION NOT NULL,
                    longitude DOUBLE PRECISION NOT NULL,
                    accuracy DOUBLE PRECISION,
                    created_at TEXT NOT NULL
                )
            """)

        connection.commit()

    finally:

        connection.close()


# =========================================================
# Authentication
# =========================================================

def check_auth():

    username = os.environ.get("DASHBOARD_USERNAME")
    password = os.environ.get("DASHBOARD_PASSWORD")

    if not username or not password:
        return False

    auth_header = request.headers.get("Authorization")

    if not auth_header:
        return False

    try:

        scheme, encoded = auth_header.split(" ", 1)

        if scheme.lower() != "basic":
            return False

        decoded_bytes = base64.b64decode(
            encoded,
            validate=True
        )

        decoded = decoded_bytes.decode("utf-8")

        provided_username, provided_password = decoded.split(
            ":",
            1
        )

        username_match = hmac.compare_digest(
            provided_username,
            username
        )

        password_match = hmac.compare_digest(
            provided_password,
            password
        )

        return username_match and password_match

    except (ValueError, UnicodeDecodeError):
        return False

    except Exception:
        return False


def require_auth():

    return Response(
        "Authentication required",
        401,
        {
            "WWW-Authenticate":
            'Basic realm="DailySense Dashboard"'
        }
    )


# =========================================================
# Security Headers
# =========================================================

@app.after_request
def add_security_headers(response):

    response.headers["X-Content-Type-Options"] = "nosniff"

    response.headers["X-Frame-Options"] = "DENY"

    response.headers["Referrer-Policy"] = (
        "strict-origin-when-cross-origin"
    )

    response.headers["Permissions-Policy"] = (
        "geolocation=(self)"
    )

    return response


# =========================================================
# Public Pages
# =========================================================

@app.route("/")
def index():

    return send_file(
        os.path.join(BASE_DIR, "index.html")
    )


@app.route("/access-denied")
def access_denied():

    return send_file(
        os.path.join(BASE_DIR, "access-denied.html")
    )


# =========================================================
# Dashboard
# =========================================================

@app.route("/dashboard")
def dashboard():

    if not check_auth():
        return require_auth()

    return send_file(
        os.path.join(BASE_DIR, "dashboard.html")
    )


# =========================================================
# Reading API
# =========================================================

@app.route("/reading", methods=["POST"])
def create_reading():

    data = request.get_json(silent=True)

    if not isinstance(data, dict):

        return jsonify({
            "success": False,
            "message": "Invalid request"
        }), 400

    age = data.get("age")
    gender = data.get("gender")
    situation = data.get("situation")
    focus = data.get("focus")

    # -----------------------------------------------------
    # Age validation
    # -----------------------------------------------------

    try:
        age = int(age)

    except (TypeError, ValueError):

        return jsonify({
            "success": False,
            "message": "Invalid age"
        }), 400

    if age < 1 or age > 120:

        return jsonify({
            "success": False,
            "message": "Age must be between 1 and 120"
        }), 400

    # -----------------------------------------------------
    # String validation
    # -----------------------------------------------------

    if not isinstance(gender, str):

        return jsonify({
            "success": False,
            "message": "Invalid gender"
        }), 400

    if not isinstance(situation, str):

        return jsonify({
            "success": False,
            "message": "Invalid situation"
        }), 400

    if not isinstance(focus, str):

        return jsonify({
            "success": False,
            "message": "Invalid focus"
        }), 400

    gender = gender.strip()
    situation = situation.strip()
    focus = focus.strip().lower()

    if not gender:

        return jsonify({
            "success": False,
            "message": "Gender is required"
        }), 400

    if not situation:

        return jsonify({
            "success": False,
            "message": "Situation is required"
        }), 400

    # -----------------------------------------------------
    # Length validation
    # -----------------------------------------------------

    if len(gender) > 50:

        return jsonify({
            "success": False,
            "message": "Gender value is too long"
        }), 400

    if len(situation) > 500:

        return jsonify({
            "success": False,
            "message": "Situation is too long"
        }), 400

    # -----------------------------------------------------
    # Allowed focus values
    # -----------------------------------------------------

    allowed_focuses = {
        "career",
        "relationships",
        "money",
        "personal"
    }

    if focus not in allowed_focuses:

        return jsonify({
            "success": False,
            "message": "Invalid focus"
        }), 400

    # -----------------------------------------------------
    # Reading content
    # -----------------------------------------------------

    readings = {

        "career": {
            "title": "A day for direction",
            "text": (
                "You may find yourself thinking "
                "more seriously about where you "
                "want to go next. Instead of trying "
                "to solve everything at once, focus "
                "on one decision that could move "
                "you forward."
            )
        },

        "relationships": {
            "title": "A day for connection",
            "text": (
                "Small conversations may carry "
                "more meaning than you expect today. "
                "Pay attention to the people who make "
                "you feel comfortable being yourself."
            )
        },

        "money": {
            "title": "A day for opportunity",
            "text": (
                "A useful opportunity may appear "
                "through something you have previously "
                "overlooked. Take your time, look at "
                "the details, and avoid making decisions "
                "too quickly."
            )
        },

        "personal": {
            "title": "A day for growth",
            "text": (
                "Today is a good moment to step back "
                "and notice how much you have already "
                "learned. One small improvement can "
                "be more valuable than trying to change "
                "everything at once."
            )
        }

    }

    reading = readings[focus]

    # -----------------------------------------------------
    # Save Reading
    # -----------------------------------------------------

    connection = get_db()

    try:

        connection.execute(
            db_query("""
                INSERT INTO readings (
                    age,
                    gender,
                    situation,
                    focus,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?)
            """),
            (
                age,
                gender,
                situation,
                focus,
                datetime.now(timezone.utc).isoformat()
            )
        )

        connection.commit()

    finally:

        connection.close()

    return jsonify({
        "success": True,
        "reading": reading
    })


# =========================================================
# Location API
# =========================================================

@app.route("/location", methods=["POST"])
def receive_location():

    data = request.get_json(silent=True)

    if not isinstance(data, dict):

        return jsonify({
            "success": False,
            "message": "Invalid JSON"
        }), 400

    latitude = data.get("latitude")
    longitude = data.get("longitude")
    accuracy = data.get("accuracy")

    # -----------------------------------------------------
    # Required values
    # -----------------------------------------------------

    if latitude is None or longitude is None:

        return jsonify({
            "success": False,
            "message": "Latitude and longitude are required"
        }), 400

    # -----------------------------------------------------
    # Numeric validation
    # -----------------------------------------------------

    try:

        latitude = float(latitude)
        longitude = float(longitude)

        if accuracy is not None:
            accuracy = float(accuracy)

    except (TypeError, ValueError):

        return jsonify({
            "success": False,
            "message": "Invalid location data"
        }), 400

    # -----------------------------------------------------
    # Coordinate validation
    # -----------------------------------------------------

    if not (
        -90 <= latitude <= 90
        and
        -180 <= longitude <= 180
    ):

        return jsonify({
            "success": False,
            "message": "Invalid coordinates"
        }), 400

    # -----------------------------------------------------
    # Accuracy validation
    # -----------------------------------------------------

    if accuracy is not None:

        if accuracy < 0 or accuracy > 100000:

            return jsonify({
                "success": False,
                "message": "Invalid accuracy value"
            }), 400

    # -----------------------------------------------------
    # Save Location
    # -----------------------------------------------------

    connection = get_db()

    try:

        connection.execute(
            db_query("""
                INSERT INTO locations (
                    latitude,
                    longitude,
                    accuracy,
                    created_at
                )
                VALUES (?, ?, ?, ?)
            """),
            (
                latitude,
                longitude,
                accuracy,
                datetime.now(timezone.utc).isoformat()
            )
        )

        connection.commit()

    finally:

        connection.close()

    return jsonify({
        "success": True,
        "message": "Location received"
    })


# =========================================================
# Dashboard Statistics
# =========================================================

@app.route("/dashboard/stats")
def dashboard_stats():

    if not check_auth():
        return require_auth()

    connection = get_db()

    try:

        readings_count = connection.execute(
            db_query("""
                SELECT COUNT(*) AS count
                FROM readings
            """)
        ).fetchone()["count"]

        locations_count = connection.execute(
            db_query("""
                SELECT COUNT(*) AS count
                FROM locations
            """)
        ).fetchone()["count"]

        latest_reading = connection.execute(
            db_query("""
                SELECT created_at
                FROM readings
                ORDER BY id DESC
                LIMIT 1
            """)
        ).fetchone()

        latest_location = connection.execute(
            db_query("""
                SELECT created_at
                FROM locations
                ORDER BY id DESC
                LIMIT 1
            """)
        ).fetchone()

    finally:

        connection.close()

    return jsonify({
        "readings": readings_count,
        "locations": locations_count,

        "latest_reading": (
            latest_reading["created_at"]
            if latest_reading
            else None
        ),

        "latest_location": (
            latest_location["created_at"]
            if latest_location
            else None
        )
    })


# =========================================================
# Dashboard Readings
# =========================================================

@app.route("/dashboard/readings")
def dashboard_readings():

    if not check_auth():
        return require_auth()

    connection = get_db()

    try:

        rows = connection.execute(
            db_query("""
                SELECT
                    id,
                    situation,
                    focus,
                    created_at
                FROM readings
                ORDER BY id DESC
                LIMIT 50
            """)
        ).fetchall()

    finally:

        connection.close()

    readings = [
        dict(row)
        for row in rows
    ]

    return jsonify(readings)


# =========================================================
# Dashboard Locations
# =========================================================

@app.route("/locations")
def get_locations():

    if not check_auth():
        return require_auth()

    connection = get_db()

    try:

        rows = connection.execute(
            db_query("""
                SELECT
                    id,
                    latitude,
                    longitude,
                    accuracy,
                    created_at
                FROM locations
                ORDER BY id DESC
                LIMIT 50
            """)
        ).fetchall()

    finally:

        connection.close()

    locations = [
        dict(row)
        for row in rows
    ]

    return jsonify(locations)


# =========================================================
# Error Handling
# =========================================================

@app.errorhandler(400)
def bad_request(error):

    return jsonify({
        "success": False,
        "message": "Bad request"
    }), 400


@app.errorhandler(413)
def request_too_large(error):

    return jsonify({
        "success": False,
        "message": "Request too large"
    }), 413


@app.errorhandler(404)
def not_found(error):

    return jsonify({
        "success": False,
        "message": "Not found"
    }), 404


@app.errorhandler(405)
def method_not_allowed(error):

    return jsonify({
        "success": False,
        "message": "Method not allowed"
    }), 405


@app.errorhandler(500)
def internal_server_error(error):

    return jsonify({
        "success": False,
        "message": "Internal server error"
    }), 500


# =========================================================
# Start Server
# =========================================================

if __name__ == "__main__":

    init_db()

    port = int(
        os.environ.get("PORT", 5000)
    )

    app.run(
        host="0.0.0.0",
        port=port,
        debug=False
    )