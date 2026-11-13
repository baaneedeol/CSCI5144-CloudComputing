
"""Simple key-value store server (Flask).

Supports GET / PUT / POST / DELETE on /<key>, persists data to a JSON file,
and logs every operation.

Also supports internal export, import, and delete endpoints for migrating
data when the consistent-hashing cluster membership changes.

Configuration comes from environment variables so the same file works
both locally and inside Docker.
"""

from flask import Flask, request, jsonify
import threading
import logging
import json
import os

app = Flask(__name__)

# Configuration 

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

HOST = os.environ.get("HOST", "127.0.0.1")
PORT = int(os.environ.get("PORT", "8080"))
DATA_DIR = os.environ.get("DATA_DIR", BASE_DIR)

DATA_FILE = os.path.join(DATA_DIR, "data.json")
LOG_FILE = os.path.join(DATA_DIR, "kvstore.log")

# In-memory store 

store = {}
store_lock = threading.Lock()

# Logging 

os.makedirs(DATA_DIR, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler()
    ],
)

logger = logging.getLogger(__name__)


# Persistence 

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
        raise RuntimeError(
            "Cannot safely start: data file is invalid."
        ) from error


def save_data():
    """Atomically persist the store to disk.

    This function must be called while holding store_lock.
    """
    temp_file = DATA_FILE + ".tmp"

    with open(temp_file, "w", encoding="utf-8") as file:
        json.dump(store, file, indent=4, allow_nan=False)
        file.flush()
        os.fsync(file.fileno())

    os.replace(temp_file, DATA_FILE)


# Health Check 

@app.route("/", methods=["GET"])
def health_check():
    """Return server status and number of stored keys."""

    with store_lock:
        count = len(store)

    return jsonify({
        "status": "running",
        "keys": count
    }), 200


# Standard KV Operations 

@app.route("/<path:key>", methods=["GET"])
def get_value(key):
    """Retrieve a value by key."""

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
        "value": value
    }), 200


@app.route("/<path:key>", methods=["PUT", "POST"])
def put_value(key):
    """Create or update a value.

    Expected JSON body:
        {"value": ...}
    """

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

    try:
        json.dumps(value, allow_nan=False)

    except (TypeError, ValueError):
        logger.warning("PUT key=%s -> Invalid JSON value", key)

        return jsonify({
            "error": "Value must be valid JSON"
        }), 400

    with store_lock:
        key_existed = key in store
        previous_value = store.get(key)

        store[key] = value

        try:
            save_data()

        except (OSError, TypeError, ValueError) as error:

            # Restore the previous state if persistence fails.
            if key_existed:
                store[key] = previous_value
            else:
                store.pop(key, None)

            logger.exception(
                "PUT persistence failed for key=%s: %s",
                key,
                error
            )

            return jsonify({
                "error": "Could not persist value"
            }), 500

    logger.info("PUT key=%s -> SUCCESS", key)

    return jsonify({
        "message": "Key stored successfully",
        "key": key,
        "value": value
    }), 200


@app.route("/<path:key>", methods=["DELETE"])
def delete_value(key):
    """Remove a key and its value."""

    with store_lock:
        if key not in store:
            logger.warning("DELETE key=%s -> NOT FOUND", key)

            return jsonify({
                "error": "Key not found",
                "key": key
            }), 404

        deleted_value = store.pop(key)

        try:
            save_data()

        except (OSError, TypeError, ValueError) as error:

            # Restore the deleted key if persistence fails.
            store[key] = deleted_value

            logger.exception(
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


# Internal Migration Operations 

@app.route("/internal/export", methods=["GET"])
def export_data():
    """Export all stored key-value pairs for migration."""

    with store_lock:
        exported_data = store.copy()

    logger.info(
        "Exporting %d keys for migration",
        len(exported_data)
    )

    return jsonify({
        "data": exported_data
    }), 200


@app.route("/internal/import", methods=["POST"])
def import_data():
    """Import key-value pairs from another KV store.

    Expected JSON body:
        {
            "data": {
                "key1": "value1",
                "key2": "value2"
            }
        }
    """

    if not request.is_json:
        return jsonify({
            "error": "JSON required"
        }), 400

    data = request.get_json(silent=True)

    if not isinstance(data, dict):
        return jsonify({
            "error": "Expected a JSON object"
        }), 400

    incoming = data.get("data")

    if not isinstance(incoming, dict):
        return jsonify({
            "error": "Expected a data object"
        }), 400

    try:
        json.dumps(incoming, allow_nan=False)

    except (TypeError, ValueError):
        return jsonify({
            "error": "Invalid JSON values"
        }), 400

    with store_lock:
        previous_store = store.copy()

        try:
            # Add incoming keys or replace matching keys.
            store.update(incoming)

            save_data()

        except (OSError, TypeError, ValueError):
            # Restore the complete previous store.
            store.clear()
            store.update(previous_store)

            logger.exception("Import failed")

            return jsonify({
                "error": "Could not persist imported data"
            }), 500

    logger.info(
        "Successfully imported %d keys",
        len(incoming)
    )

    return jsonify({
        "message": "Import successful",
        "imported": len(incoming)
    }), 200


@app.route("/internal/delete", methods=["POST"])
def delete_migrated_keys():
    """Delete keys after they have been successfully migrated.

    Expected JSON body:
        {
            "keys": ["key1", "key2"]
        }
    """

    if not request.is_json:
        return jsonify({
            "error": "JSON required"
        }), 400

    data = request.get_json(silent=True)

    if not isinstance(data, dict):
        return jsonify({
            "error": "Expected a JSON object"
        }), 400

    keys = data.get("keys")

    if not isinstance(keys, list):
        return jsonify({
            "error": "Expected a keys list"
        }), 400

    if not all(isinstance(key, str) for key in keys):
        return jsonify({
            "error": "Keys must be strings"
        }), 400

    # Remove duplicates so the reported deletion count is accurate.
    keys = list(dict.fromkeys(keys))

    with store_lock:
        previous_store = store.copy()

        try:
            deleted_count = 0

            for key in keys:
                if key in store:
                    del store[key]
                    deleted_count += 1

            save_data()

        except (OSError, TypeError, ValueError):
            # Restore the complete store if deletion cannot be persisted.
            store.clear()
            store.update(previous_store)

            logger.exception("Migration deletion failed")

            return jsonify({
                "error": "Could not persist deletion"
            }), 500

    logger.info("Deleted %d migrated keys", deleted_count)

    return jsonify({
        "message": "Deletion successful",
        "deleted": deleted_count
    }), 200


# Entry Point 
if __name__ == "__main__":
    load_data()

    logger.info("Starting server on %s:%d", HOST, PORT)

    app.run(host=HOST, port=PORT, threaded=True)
