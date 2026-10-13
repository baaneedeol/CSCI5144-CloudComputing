from flask import Flask, request, jsonify
import threading
import logging
import json
import os

app = Flask(__name__)

HOST = "127.0.0.1"
PORT = 8080

DATA_FILE = "data.json"
LOG_FILE = "kvstore.log"

store = {}
store_lock = threading.Lock()

logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

logger = logging.getLogger(__name__)


# Load saved key-value pairs from disk
def load_data():
    global store

    if not os.path.exists(DATA_FILE):
        logger.info("No existing data file found. Starting empty.")
        return

    try:
        with open(DATA_FILE, "r", encoding="utf-8") as file:
            loaded_data = json.load(file)

        if not isinstance(loaded_data, dict):
            raise ValueError("Data file must contain a JSON object")

        with store_lock:
            store = loaded_data

        logger.info("Loaded %d keys from disk.", len(loaded_data))

    except (json.JSONDecodeError, OSError, ValueError) as error:
        logger.error("Could not load data: %s", error)
        with store_lock:
            store = {}


# Persist the current store safely to a JSON file
def save_data():
    try:
        with store_lock:
            temp_file = DATA_FILE + ".tmp"

            with open(temp_file, "w", encoding="utf-8") as file:
                json.dump(store, file, indent=4)

            os.replace(temp_file, DATA_FILE)

        logger.info("Store saved to disk.")

    except (OSError, TypeError, ValueError) as error:
        logger.error("Could not save data: %s", error)


# Server status and number of stored keys
@app.route("/", methods=["GET"])
def health_check():
    with store_lock:
        number_of_keys = len(store)

    return jsonify({
        "status": "running",
        "keys": number_of_keys
    }), 200


# Retrieve a value by key
@app.route("/<key>", methods=["GET"])
def get_value(key):
    with store_lock:
        if key not in store:
            logger.warning("GET key=%s -> NOT FOUND", key)
            return jsonify({
                "error": "Key not found",
                "key": key
            }), 404

        value = store[key]

    logger.info("GET key=%s -> SUCCESS", key)

    return jsonify({
        "key": key,
        "value": value
    }), 200


# Create or update a value
@app.route("/<key>", methods=["PUT"])
def put_value(key):
    if not request.is_json:
        logger.warning("PUT key=%s -> Invalid content type", key)
        return jsonify({
            "error": "Request must contain JSON data"
        }), 400

    data = request.get_json(silent=True)

    if not isinstance(data, dict) or "value" not in data:
        logger.warning("PUT key=%s -> Missing value", key)
        return jsonify({
            "error": "Request must contain a 'value' field"
        }), 400

    value = data["value"]

    # Validate that the value can be serialized as JSON.
    try:
        json.dumps(value)
    except (TypeError, ValueError):
        return jsonify({
            "error": "Value must be JSON-serializable"
        }), 400

    with store_lock:
        store[key] = value

        # Keep the update and persistence operation serialized
        # against other modifications.
        try:
            temp_file = DATA_FILE + ".tmp"

            with open(temp_file, "w", encoding="utf-8") as file:
                json.dump(store, file, indent=4)

            os.replace(temp_file, DATA_FILE)

        except (OSError, TypeError, ValueError) as error:
            logger.error("PUT persistence failed for key=%s: %s", key, error)
            return jsonify({
                "error": "Could not persist value"
            }), 500

    logger.info("PUT key=%s -> SUCCESS", key)

    return jsonify({
        "message": "Key stored successfully",
        "key": key,
        "value": value
    }), 200


# Remove a key and its value
@app.route("/<key>", methods=["DELETE"])
def delete_value(key):
    with store_lock:
        if key not in store:
            logger.warning("DELETE key=%s -> NOT FOUND", key)
            return jsonify({
                "error": "Key not found",
                "key": key
            }), 404

        deleted_value = store.pop(key)

        try:
            temp_file = DATA_FILE + ".tmp"

            with open(temp_file, "w", encoding="utf-8") as file:
                json.dump(store, file, indent=4)

            os.replace(temp_file, DATA_FILE)

        except (OSError, TypeError, ValueError) as error:
            # Restore the in-memory value if persistence fails.
            store[key] = deleted_value
            logger.error(
                "DELETE persistence failed for key=%s: %s",
                key,
                error
            )
            return jsonify({
                "error": "Could not persist deletion"
            }), 500

    logger.info("DELETE key=%s -> SUCCESS", key)

    return jsonify({
        "message": "Key deleted successfully",
        "key": key,
        "value": deleted_value
    }), 200


if __name__ == "__main__":
    load_data()

    logger.info("Starting server on port %d", PORT)

    print(f"Key-Value Store running at http://{HOST}:{PORT}")
    print("Press CTRL+C to stop.")

    app.run(
        host=HOST,
        port=PORT,
        threaded=True
    )