"""Simple key-value store server (Flask).

Supports GET / PUT / POST / DELETE on /<key>, persists data to a JSON file,
and logs every operation. Configuration comes from environment variables so
the same file works both locally and inside Docker.
"""

from flask import Flask, request, jsonify
import threading
import logging
import json
import os

app = Flask(__name__)

# --- Configuration (overridable with environment variables) -----------------
# Locally: defaults to 127.0.0.1 and the script's own folder.
# In Docker: the Dockerfile sets HOST=0.0.0.0 and DATA_DIR=/app/data.
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

HOST = os.environ.get("HOST", "127.0.0.1")
PORT = int(os.environ.get("PORT", "8080"))
DATA_DIR = os.environ.get("DATA_DIR", BASE_DIR)

DATA_FILE = os.path.join(DATA_DIR, "data.json")
LOG_FILE = os.path.join(DATA_DIR, "kvstore.log")

# --- In-memory store protected by a lock for concurrent requests ------------
store = {}
store_lock = threading.Lock()

# Log to a file and to stdout (stdout is what `docker logs` shows)
os.makedirs(DATA_DIR, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.FileHandler(LOG_FILE), logging.StreamHandler()],
)
logger = logging.getLogger(__name__)


def load_data():
    """Load saved key-value pairs from disk at startup."""
    global store

    if not os.path.exists(DATA_FILE):
        logger.info("No existing data file found. Starting empty.")
        return

    try:
        with open(DATA_FILE, "r", encoding="utf-8") as file:
            loaded = json.load(file)
        if not isinstance(loaded, dict):
            raise ValueError("Data file must contain a JSON object")
        with store_lock:
            store = loaded
        logger.info("Loaded %d keys from disk.", len(loaded))
    except (json.JSONDecodeError, OSError, ValueError) as error:
        logger.exception("Could not load existing data: %s", error)
        raise RuntimeError("Cannot safely start: data file is invalid.") from error


def save_data():
    """Write the store to disk atomically (temp file, then rename).

    Must be called while holding store_lock.
    """
    temp_file = DATA_FILE + ".tmp"
    with open(temp_file, "w", encoding="utf-8") as file:
        json.dump(store, file, indent=4, allow_nan=False)
        file.flush()
        os.fsync(file.fileno())
    os.replace(temp_file, DATA_FILE)


# --- Routes -----------------------------------------------------------------
@app.route("/", methods=["GET"])
def health_check():
    """Server status and number of stored keys."""
    with store_lock:
        count = len(store)
    return jsonify({"status": "running", "keys": count}), 200


@app.route("/<key>", methods=["GET"])
def get_value(key):
    """Retrieve a value by key."""
    with store_lock:
        if key not in store:
            logger.warning("GET key=%s -> NOT FOUND", key)
            return jsonify({"error": "Key not found", "key": key}), 404
        value = store[key]

    logger.info("GET key=%s -> SUCCESS", key)
    return jsonify({"value": value}), 200


@app.route("/<key>", methods=["PUT", "POST"])
def put_value(key):
    """Create or update a value. Body must be JSON: {"value": ...}."""
    if not request.is_json:
        logger.warning("PUT key=%s -> Invalid content type", key)
        return jsonify({"error": "Request must contain JSON data"}), 400

    data = request.get_json(silent=True)
    if not isinstance(data, dict) or "value" not in data:
        logger.warning("PUT key=%s -> Missing value", key)
        return jsonify({"error": "Request must contain a 'value' field"}), 400

    value = data["value"]
    try:
        json.dumps(value, allow_nan=False)
    except (TypeError, ValueError):
        logger.warning("PUT key=%s -> Invalid JSON value", key)
        return jsonify({"error": "Value must be valid JSON"}), 400

    with store_lock:
        key_existed = key in store
        previous_value = store.get(key)
        store[key] = value
        try:
            save_data()
        except (OSError, TypeError, ValueError) as error:
            # Roll back the in-memory change if the disk write failed
            if key_existed:
                store[key] = previous_value
            else:
                store.pop(key, None)
            logger.exception("PUT persistence failed for key=%s: %s", key, error)
            return jsonify({"error": "Could not persist value"}), 500

    logger.info("PUT key=%s -> SUCCESS", key)
    return jsonify({"message": "Key stored successfully", "key": key, "value": value}), 200


@app.route("/<key>", methods=["DELETE"])
def delete_value(key):
    """Remove a key and its value."""
    with store_lock:
        if key not in store:
            logger.warning("DELETE key=%s -> NOT FOUND", key)
            return jsonify({"error": "Key not found", "key": key}), 404

        deleted_value = store.pop(key)
        try:
            save_data()
        except (OSError, TypeError, ValueError) as error:
            # Roll back the deletion if the disk write failed
            store[key] = deleted_value
            logger.exception("DELETE persistence failed for key=%s: %s", key, error)
            return jsonify({"error": "Could not persist deletion"}), 500

    logger.info("DELETE key=%s -> SUCCESS", key)
    return jsonify({"message": "Key deleted successfully", "key": key, "value": deleted_value}), 200


# --- Entry point ------------------------------------------------------------
if __name__ == "__main__":
    load_data()
    logger.info("Starting server on %s:%d", HOST, PORT)
    app.run(host=HOST, port=PORT, threaded=True)
