
from flask import Flask, request, jsonify, Response
import requests
import os
import threading
from contextlib import contextmanager
from urllib.parse import quote

from consistent_hash import ConsistentHash

app = Flask(__name__)

# CLUSTER CONFIGURATION
nodes = [
    node.strip().rstrip("/")
    for node in os.environ.get(
        "KV_NODES",
        "http://kv1:8080,http://kv2:8080,http://kv3:8080"
    ).split(",")
    if node.strip()
]

REPLICAS = 100
TIMEOUT = 5

hash_ring = ConsistentHash(nodes, replicas=REPLICAS)


# READ-WRITE LOCK
class ReadWriteLock:
    """
    Multiple normal requests can read the hash ring
    simultaneously.

    Membership updates require exclusive access.

    Waiting writers receive priority so that membership
    updates cannot be postponed indefinitely.
    """

    def __init__(self):
        self.condition = threading.Condition()

        self.active_readers = 0
        self.active_writer = False
        self.waiting_writers = 0

    @contextmanager
    def read_lock(self):

        with self.condition:
            while (
                self.active_writer
                or self.waiting_writers > 0
            ):
                self.condition.wait()

            self.active_readers += 1

        try:
            yield

        finally:
            with self.condition:
                self.active_readers -= 1

                if self.active_readers == 0:
                    self.condition.notify_all()

    @contextmanager
    def write_lock(self):

        with self.condition:
            self.waiting_writers += 1

            try:
                while (
                    self.active_writer
                    or self.active_readers > 0
                ):
                    self.condition.wait()

                self.active_writer = True

            finally:
                self.waiting_writers -= 1

        try:
            yield

        finally:
            with self.condition:
                self.active_writer = False
                self.condition.notify_all()


membership_lock = ReadWriteLock()


# MIGRATION HELPERS
def export_node(node):

    response = requests.get(
        f"{node}/internal/export",
        timeout=TIMEOUT
    )

    response.raise_for_status()

    data = response.json().get("data")

    if not isinstance(data, dict):
        raise RuntimeError(f"Invalid export from {node}")

    return data


def import_data(node, data):

    if not data:
        return

    response = requests.post(
        f"{node}/internal/import",
        json={"data": data},
        timeout=TIMEOUT
    )

    response.raise_for_status()


def delete_keys(node, keys):

    if not keys:
        return

    response = requests.post(
        f"{node}/internal/delete",
        json={"keys": keys},
        timeout=TIMEOUT
    )

    response.raise_for_status()


def migrate_data(old_nodes, new_ring):
    """
    Export existing data, transfer keys to their new owners,
    and delete old copies only after successful imports.
    """

    exported = {}

    # Step 1: Export every existing store.
    for node in old_nodes:
        exported[node] = export_node(node)

    # Step 2: Determine new ownership for every key.
    new_data = {
        node: {}
        for node in new_ring.get_nodes()
    }

    moved_keys = {
        node: []
        for node in old_nodes
    }

    for old_node, data in exported.items():

        for key, value in data.items():

            new_owner = new_ring.get_node(key)

            if new_owner is None:
                raise RuntimeError(
                    "No destination for migrated key"
                )

            new_data[new_owner][key] = value

            if new_owner != old_node:
                moved_keys[old_node].append(key)

    # Step 3: Import data before deleting old copies.
    for node, data in new_data.items():
        import_data(node, data)

    # Step 4: Delete moved keys from previous owners.
    try:

        for node, keys in moved_keys.items():
            delete_keys(node, keys)

    except Exception:

        # Restore original data if deletion fails.
        for node, original_data in exported.items():
            import_data(node, original_data)

        raise

    total_keys = sum(
        len(data) for data in exported.values()
    )

    total_moved = sum(
        len(keys) for keys in moved_keys.values()
    )

    return {
        "total_keys": total_keys,
        "moved_keys": total_moved,
        "retained_keys": total_keys - total_moved
    }


# HEALTH CHECK
@app.route("/", methods=["GET"])
def health_check():

    with membership_lock.read_lock():

        return jsonify({
            "status": "running",
            "number_of_nodes": len(nodes),
            "active_nodes": list(nodes)
        }), 200


# MEMBERSHIP MANAGEMENT
@app.route("/admin/nodes", methods=["POST"])
def update_membership():
    """
    Update active KV stores and migrate existing data.

    Example request:
    {
        "nodes": [
            "http://kv1:8080",
            "http://kv2:8080"
        ]
    }
    """

    global nodes, hash_ring

    if not request.is_json:
        return jsonify({
            "error": "JSON required"
        }), 400

    data = request.get_json(silent=True)

    if (
        not isinstance(data, dict)
        or not isinstance(data.get("nodes"), list)
    ):
        return jsonify({
            "error": "Expected a nodes list"
        }), 400

    new_nodes = [
        node.strip().rstrip("/")
        for node in data["nodes"]
        if isinstance(node, str) and node.strip()
    ]

    if len(new_nodes) != len(data["nodes"]):
        return jsonify({
            "error": "Invalid node URL"
        }), 400

    if (
        not new_nodes
        or len(set(new_nodes)) != len(new_nodes)
    ):
        return jsonify({
            "error": "Nodes must be nonempty and unique"
        }), 400

    # Exclusive lock: normal requests wait until migration finishes.
    with membership_lock.write_lock():

        if set(new_nodes) == set(nodes):

            return jsonify({
                "message": "Membership unchanged",
                "active_nodes": list(nodes)
            }), 200

        new_ring = ConsistentHash(
            new_nodes,
            replicas=REPLICAS
        )

        try:

            migration = migrate_data(
                nodes,
                new_ring
            )

        except Exception as error:

            app.logger.exception(
                "Membership migration failed"
            )

            return jsonify({
                "error": "Membership update failed",
                "details": str(error),
                "active_nodes": list(nodes)
            }), 500

        # Activate the new membership only after migration succeeds.
        nodes = new_nodes
        hash_ring = new_ring

        return jsonify({
            "message": "Membership updated successfully",
            "active_nodes": list(nodes),
            "migration": migration
        }), 200


# PHYSICAL CLUSTER STATUS
@app.route("/admin/status", methods=["GET"])
def cluster_status():
    """
    Report actual physical key counts on each active KV store.
    """

    with membership_lock.read_lock():

        results = []

        for node in nodes:

            try:

                response = requests.get(
                    node + "/",
                    timeout=TIMEOUT
                )

                response.raise_for_status()

                health = response.json()

                results.append({
                    "node": node,
                    "status": health.get("status"),
                    "keys": health.get("keys")
                })

            except requests.RequestException:

                results.append({
                    "node": node,
                    "status": "unavailable",
                    "keys": None
                })

        return jsonify({
            "number_of_nodes": len(nodes),
            "stores": results
        }), 200


# NORMAL KV REQUEST ROUTING
@app.route(
    "/<path:key>",
    methods=["GET", "PUT", "POST", "DELETE"]
)
def route_request(key):

    # Shared lock: multiple client requests can execute concurrently.
    with membership_lock.read_lock():

        node = hash_ring.get_node(key)

        if node is None:

            return jsonify({
                "error": "No KV stores available"
            }), 503

        encoded_key = quote(key, safe="")

        target_url = f"{node}/{encoded_key}"

        try:

            response = requests.request(
                method=request.method,
                url=target_url,
                data=request.get_data(),
                params=request.args,
                headers={
                    "Content-Type": request.content_type
                } if request.content_type else {},
                timeout=TIMEOUT
            )

            return Response(
                response.content,
                status=response.status_code,
                content_type=response.headers.get(
                    "Content-Type",
                    "application/json"
                )
            )

        except requests.RequestException as error:

            app.logger.error(
                "Error contacting %s: %s",
                node,
                error
            )

            return jsonify({
                "error": "KV store unavailable",
                "node": node
            }), 503

if __name__ == "__main__":

    print("Starting KV coordinator...")
    print("Active nodes:", nodes)

    app.run(
        host="0.0.0.0",
        port=8080,
        threaded=True
    )
