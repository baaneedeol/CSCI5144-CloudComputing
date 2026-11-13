
import requests
import subprocess
import time
import uuid
from pathlib import Path

# CONFIGURATION
COORDINATOR_URL = "http://localhost:8080"

KV_NODES = [
    "http://kv1:8080",
    "http://kv2:8080",
    "http://kv3:8080"
]

KV_HEALTH_URLS = [
    "http://localhost:8081/",
    "http://localhost:8082/",
    "http://localhost:8083/"
]

NUM_KEYS = 300

COMPOSE_DIR = Path(__file__).resolve().parent

# Unique prefix prevents collisions with previous test runs
RUN_ID = uuid.uuid4().hex[:8]

test_data = {
    f"persistence_{RUN_ID}_{i}": f"test_value_{RUN_ID}_{i}"
    for i in range(NUM_KEYS)
}


# HELPER FUNCTIONS
def check_response(response, description):
    if response.status_code not in (200, 201):
        raise Exception(
            f"{description} failed: "
            f"{response.status_code} - {response.text}"
        )


def change_membership():
    print("\nConfiguring three KV stores...")

    response = requests.post(
        f"{COORDINATOR_URL}/admin/nodes",
        json={"nodes": KV_NODES},
        timeout=30
    )

    check_response(response, "Membership update")

    print("Three-store membership configured!")
    print("Migration results:", response.json())


def write_all_keys():
    print(f"\nWriting {NUM_KEYS} keys...")

    for key, value in test_data.items():
        response = requests.put(
            f"{COORDINATOR_URL}/{key}",
            json={"value": value},
            timeout=10
        )

        check_response(response, f"Writing {key}")

    print(f"Successfully wrote all {NUM_KEYS} keys!")


def verify_all_keys(stage):
    print(f"\nVerifying all keys {stage}...")

    for key, expected_value in test_data.items():
        response = requests.get(
            f"{COORDINATOR_URL}/{key}",
            timeout=10
        )

        if response.status_code != 200:
            raise Exception(
                f"FAILED: Could not retrieve {key}"
            )

        actual_value = response.json().get("value")

        if actual_value != expected_value:
            raise Exception(
                f"FAILED: Value mismatch for {key}. "
                f"Expected {expected_value}, got {actual_value}"
            )

    print(f"Successfully verified all {NUM_KEYS} keys!")


def show_cluster_status():
    print("\nCurrent cluster status:")

    response = requests.get(
        f"{COORDINATOR_URL}/admin/status",
        timeout=10
    )

    check_response(response, "Cluster status")

    status = response.json()
    print(status)

    if status["number_of_nodes"] != 3:
        raise Exception("Cluster does not have three active nodes!")

    return status


def show_store_health():
    print("\nChecking individual KV stores...")

    for url in KV_HEALTH_URLS:
        response = requests.get(url, timeout=5)
        check_response(response, f"Health check {url}")

        print(f"{url}: {response.json()}")


def restart_kv_containers():
    print("\n" + "=" * 60)
    print("RESTARTING KV CONTAINERS")
    print("=" * 60)

    subprocess.run(
        ["docker", "compose", "restart", "kv1", "kv2", "kv3"],
        cwd=COMPOSE_DIR,
        check=True
    )

    print("\nKV containers restarted!")
    print("Coordinator was NOT restarted.")


def wait_for_stores():
    print("\nWaiting for all KV stores to become responsive...")

    max_attempts = 30

    for attempt in range(max_attempts):
        all_ready = True

        for url in KV_HEALTH_URLS:
            try:
                response = requests.get(url, timeout=3)

                if response.status_code != 200:
                    all_ready = False
                    break

                if response.json().get("status") != "running":
                    all_ready = False
                    break

            except requests.RequestException:
                all_ready = False
                break

        if all_ready:
            print("All three KV stores are responsive!")
            return

        print(f"Waiting... ({attempt + 1}/{max_attempts})")
        time.sleep(2)

    raise Exception("KV stores did not become healthy in time!")


# MAIN PERSISTENCE TEST
def main():

    print("=" * 60)
    print("DISTRIBUTED KV STORE PERSISTENCE TEST")
    print("=" * 60)

    try:

        # STEP 1: Configure three stores
        print("\nSTEP 1: CONFIGURING THREE KV STORES")

        change_membership()

        # STEP 2: Write 300 keys
        print("\nSTEP 2: WRITING TEST DATA")

        write_all_keys()

        # STEP 3: Verify before restart
        print("\nSTEP 3: VERIFYING BEFORE RESTART")

        verify_all_keys("before restart")

        # STEP 4: Check distribution
        print("\nSTEP 4: CHECKING PHYSICAL DISTRIBUTION")

        before_status = show_cluster_status()
        show_store_health()

        # STEP 5: Restart only KV containers
        print("\nSTEP 5: RESTARTING KV CONTAINERS")

        restart_kv_containers()

        # STEP 6: Wait for containers
        print("\nSTEP 6: WAITING FOR CONTAINERS")

        wait_for_stores()

        # STEP 7: Verify persisted data
        print("\nSTEP 7: VERIFYING PERSISTED DATA")

        show_store_health()

        after_status = show_cluster_status()

        # Confirm membership was retained
        if after_status["number_of_nodes"] != 3:
            raise Exception(
                "Coordinator membership changed after restart!"
            )

        # Verify every original key-value pair
        verify_all_keys("after KV container restart")

        # STEP 8: Final results
        print("\n" + "=" * 60)
        print("PERSISTENCE TEST RESULTS")
        print("=" * 60)

        print(f"Total keys written: {NUM_KEYS}")
        print("Before restart: ALL KEYS VERIFIED")
        print("KV1 restarted successfully")
        print("KV2 restarted successfully")
        print("KV3 restarted successfully")
        print("Coordinator remained running")
        print("Three-store membership retained")
        print("After restart: ALL KEYS VERIFIED")

        print("\nBEFORE RESTART:")
        for store in before_status["stores"]:
            print(f"{store['node']}: {store['keys']} keys")

        print("\nAFTER RESTART:")
        for store in after_status["stores"]:
            print(f"{store['node']}: {store['keys']} keys")

        print("\n" + "=" * 60)
        print("ALL PERSISTENCE TESTS PASSED!")
        print("=" * 60)

    except Exception as error:
        print("\n" + "=" * 60)
        print("PERSISTENCE TEST FAILED!")
        print("=" * 60)
        print(error)
        raise


if __name__ == "__main__":
    main()
