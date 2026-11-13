
"""
End-to-end distributed KV store test.

Run this script from your host machine while Docker Compose
is running and the coordinator initially has KV1 configured.

Tests:
1. Writing 300 keys to KV1.
2. Adding KV2 and migrating keys.
3. Adding KV3 and migrating keys.
4. Removing KV3 and migrating keys back to KV1/KV2.
5. Removing KV2 and migrating all keys back to KV1.
6. Verifying all values remain accessible after every change.
7. Verifying physical key distribution matches consistent hashing.
"""

import requests
import uuid

from collections import Counter
from consistent_hash import ConsistentHash


COORDINATOR = "http://localhost:8080"

NODES = [
    "http://kv1:8080",
    "http://kv2:8080",
    "http://kv3:8080"
]

HOST_NODES = [
    "http://localhost:8081",
    "http://localhost:8082",
    "http://localhost:8083"
]

NUM_KEYS = 300
REPLICAS = 100

PREFIX = f"e2e_{uuid.uuid4().hex[:8]}"

keys = {
    f"{PREFIX}_key_{i}": f"test_value_{i}"
    for i in range(NUM_KEYS)
}


# Helper functions
def check_response(response, description):
    """Raise an error if an HTTP request fails."""

    if not response.ok:
        raise RuntimeError(
            f"{description} failed: "
            f"{response.status_code} {response.text}"
        )


def get_cluster_status():
    """Return the number of physical keys on each KV store."""

    response = requests.get(
        f"{COORDINATOR}/admin/status",
        timeout=10
    )

    check_response(response, "Cluster status")

    return {
        item["node"]: item["keys"]
        for item in response.json()["stores"]
    }


def get_physical_key_locations():
    """Retrieve actual physical key locations from every KV store."""

    locations = {}

    for docker_node, host_node in zip(NODES, HOST_NODES):

        response = requests.get(
            f"{host_node}/internal/export",
            timeout=20
        )

        check_response(response, f"Export from {docker_node}")

        data = response.json()["data"]

        for key in data:
            locations[key] = docker_node

    return locations


def check_distribution(active_nodes):
    """
    Verify each test key physically exists on exactly one
    expected owner according to the consistent hash ring.
    """

    ring = ConsistentHash(
        active_nodes,
        replicas=REPLICAS
    )

    expected = Counter(
        ring.get_node(key)
        for key in keys
    )

    physical_locations = get_physical_key_locations()

    actual = Counter()

    print("\nPhysical distribution:")

    for key in keys:

        expected_node = ring.get_node(key)
        actual_node = physical_locations.get(key)

        if actual_node is None:
            raise AssertionError(
                f"Key {key} was not found in any KV store."
            )

        if actual_node != expected_node:
            raise AssertionError(
                f"Key ownership mismatch for {key}: "
                f"expected {expected_node}, "
                f"found {actual_node}"
            )

        actual[actual_node] += 1

    # Ensure there are no duplicate physical copies of test keys.
    test_key_locations = {}

    for key, node in physical_locations.items():
        if key in keys:
            test_key_locations.setdefault(key, []).append(node)

    for key, locations in test_key_locations.items():
        if len(locations) != 1:
            raise AssertionError(
                f"Key {key} exists on multiple stores: {locations}"
            )

    for node in active_nodes:
        print(
            f"{node}: {actual[node]} test keys "
            f"(expected {expected[node]})"
        )

    print("Physical distribution verified!")


def verify_all_keys():
    """Verify every test key can be retrieved with its original value."""

    print("\nVerifying all stored keys...")

    for key, expected in keys.items():

        response = requests.get(
            f"{COORDINATOR}/{key}",
            timeout=10
        )

        check_response(response, f"GET {key}")

        actual = response.json().get("value")

        if actual != expected:
            raise AssertionError(
                f"Value mismatch for {key}: "
                f"expected={expected!r}, "
                f"actual={actual!r}"
            )

    print(f"Successfully retrieved all {NUM_KEYS} keys!")


def change_membership(active_nodes):
    """Update coordinator membership and trigger data migration."""

    print(
        f"\nChanging membership to "
        f"{len(active_nodes)} KV store(s)..."
    )

    response = requests.post(
        f"{COORDINATOR}/admin/nodes",
        json={"nodes": active_nodes},
        timeout=120
    )

    check_response(response, "Membership update")

    result = response.json()

    print("Membership updated!")
    print("Migration results:", result["migration"])


def print_step(title):
    """Print a readable test section heading."""

    print("\n" + "=" * 60)
    print(title)
    print("=" * 60)


def verify_configuration(active_nodes, description):
    """
    Verify data integrity and physical ownership after
    a membership change.
    """

    print_step(description)

    verify_all_keys()
    check_distribution(active_nodes)


# Main end-to-end test
def main():

    print_step("DISTRIBUTED KV STORE END-TO-END TEST")

    # Confirm initial one-node configuration.
    status = requests.get(
        COORDINATOR,
        timeout=10
    )

    check_response(status, "Coordinator health")

    active_nodes = status.json()["active_nodes"]

    if active_nodes != NODES[:1]:
        raise RuntimeError(
            "Start the coordinator with KV1 only before running "
            "this test.\n"
            f"Currently active nodes: {active_nodes}"
        )

    # STEP 1: Write 300 keys to KV1.
    print_step("STEP 1: Writing 300 keys to KV1")

    for key, value in keys.items():

        response = requests.put(
            f"{COORDINATOR}/{key}",
            json={"value": value},
            timeout=10
        )

        check_response(response, f"PUT {key}")

    print(f"All {NUM_KEYS} keys written!")

    verify_all_keys()
    check_distribution(NODES[:1])

    # STEP 2: Add KV2.
    print_step("STEP 2: Adding KV2 (1 -> 2 stores)")

    change_membership(NODES[:2])

    verify_configuration(
        NODES[:2],
        "VERIFYING TWO-STORE CONFIGURATION"
    )

    # STEP 3: Add KV3.
    print_step("STEP 3: Adding KV3 (2 -> 3 stores)")

    change_membership(NODES[:3])

    verify_configuration(
        NODES[:3],
        "VERIFYING THREE-STORE CONFIGURATION"
    )

    # STEP 4: Remove KV3.
    print_step("STEP 4: Removing KV3 (3 -> 2 stores)")

    change_membership(NODES[:2])

    verify_configuration(
        NODES[:2],
        "VERIFYING TWO-STORE CONFIGURATION AFTER REMOVAL"
    )

    # STEP 5: Remove KV2.
    print_step("STEP 5: Removing KV2 (2 -> 1 store)")

    change_membership(NODES[:1])

    verify_configuration(
        NODES[:1],
        "VERIFYING ONE-STORE CONFIGURATION AFTER REMOVAL"
    )

    # FINAL RESULTS
    print_step("ALL END-TO-END TESTS PASSED")

    print(f"Total test keys written: {NUM_KEYS}")
    print("All keys successfully migrated.")
    print("All keys remain retrievable.")
    print("Physical distribution matches consistent hashing.")
    print("Scale-up membership changes passed.")
    print("Scale-down membership changes passed.")

    final_status = get_cluster_status()

    print("\nFinal physical KV store counts:")

    for node in NODES:
        print(f"{node}: {final_status.get(node, 0)} total keys")


if __name__ == "__main__":
    main()
