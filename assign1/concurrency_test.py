
import concurrent.futures
import requests

BASE_URL = "http://127.0.0.1:8080"
KEY = "shared_concurrency_test"
NUM_REQUESTS = 30


def put_value(i):
    response = requests.put(
        f"{BASE_URL}/{KEY}",
        json={"value": f"value_{i}"},
        timeout=10
    )

    return response.status_code


def main():
    with concurrent.futures.ThreadPoolExecutor(
        max_workers=10
    ) as executor:
        statuses = list(
            executor.map(put_value, range(NUM_REQUESTS))
        )

    failures = [
        status for status in statuses
        if status not in (200, 201)
    ]

    final_response = requests.get(
        f"{BASE_URL}/{KEY}",
        timeout=10
    )

    print(f"PUT requests attempted: {len(statuses)}")
    print(f"Successful PUT requests: {len(statuses) - len(failures)}")
    print(f"Failed PUT requests: {len(failures)}")
    print(f"Final GET status: {final_response.status_code}")
    print(f"Final stored value: {final_response.json()}")

    assert not failures, f"Some PUT requests failed: {failures}"
    assert final_response.status_code == 200

    # Remove the test key.
    delete_response = requests.delete(f"{BASE_URL}/{KEY}")
    print(f"Cleanup status: {delete_response.status_code}")


if __name__ == "__main__":
    main()
