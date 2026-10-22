from flask import Flask, request, jsonify
import threading
import logging
import json
import os

app = Flask(__name__)

store = {}
lock = threading.Lock()

logging.basicConfig(
    filename="kvstore.log",
    level=logging.INFO,
    format="%(asctime)s %(message)s"
)


def save_to_disk():
    with open("data.json.tmp", "w") as f:
        json.dump(store, f)

    os.replace("data.json.tmp", "data.json")


if os.path.exists("data.json"):
    try:
        with open("data.json") as f:
            store = json.load(f)

    except ValueError:
        print("data.json is broken, please fix or delete it")
        raise


@app.route("/<key>", methods=["GET"])
def get_value(key):
    with lock:
        if key not in store:
            logging.info("GET " + key + " not found")
            return jsonify({
                "error": "key not found",
                "key": key
            }), 404

        value = store[key]

    logging.info("GET " + key)

    return jsonify({"value": value})


@app.route("/<key>", methods=["PUT", "POST"])
def put_value(key):
    data = request.get_json(silent=True)

    if not isinstance(data, dict) or "value" not in data:
        logging.info("PUT " + key + " bad request")
        return jsonify({
            "error": "need JSON like {\"value\": ...}"
        }), 400

    with lock:
        existed = key in store
        old = store.get(key)

        store[key] = data["value"]

        try:
            save_to_disk()

        except OSError:
            if existed:
                store[key] = old
            else:
                del store[key]

            logging.info("PUT " + key + " failed to save")
            return jsonify({
                "error": "could not save"
            }), 500

    logging.info("PUT " + key)

    return jsonify({
        "message": "ok",
        "key": key
    })


@app.route("/<key>", methods=["DELETE"])
def delete_value(key):
    with lock:
        if key not in store:
            logging.info("DEL " + key + " not found")
            return jsonify({
                "error": "key not found",
                "key": key
            }), 404

        old = store.pop(key)

        try:
            save_to_disk()

        except OSError:
            store[key] = old

            logging.info("DEL " + key + " failed to save")
            return jsonify({
                "error": "could not save"
            }), 500

    logging.info("DEL " + key)

    return jsonify({
        "message": "deleted",
        "key": key
    })


if __name__ == "__main__":
    print("Key-Value Store running at http://127.0.0.1:8080")

    app.run(
        host="127.0.0.1",
        port=8080,
        threaded=True
    )
