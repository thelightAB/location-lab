from flask import Flask, request, jsonify, send_file
from datetime import datetime, timezone
import os

app = Flask(__name__)

locations = []


@app.route("/")
def index():
    return send_file("index.html")


@app.route("/access-denied")
def access_denied():
    return send_file("access-denied.html")


@app.route("/dashboard")
def dashboard():
    return send_file("dashboard.html")


@app.route("/location", methods=["POST"])
def receive_location():

    data = request.get_json(silent=True)

    if not data:
        return jsonify({
            "success": False,
            "message": "Invalid JSON"
        }), 400

    latitude = data.get("latitude")
    longitude = data.get("longitude")
    accuracy = data.get("accuracy")

    if latitude is None or longitude is None:
        return jsonify({
            "success": False,
            "message": "Latitude and longitude are required"
        }), 400

    record = {
        "latitude": latitude,
        "longitude": longitude,
        "accuracy": accuracy,
        "time": datetime.now(timezone.utc).isoformat()
    }

    locations.append(record)

    return jsonify({
        "success": True,
        "message": "Location received"
    })


@app.route("/locations")
def get_locations():
    return jsonify(locations)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))

    app.run(
        host="0.0.0.0",
        port=port,
        debug=True
    )