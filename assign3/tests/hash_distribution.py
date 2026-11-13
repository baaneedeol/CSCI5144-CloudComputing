
"""
Test consistent hashing distribution and key remapping.

This script:
1. Generates 300 keys.
2. Measures distribution across 1, 2, and 3 KV stores.
3. Measures how many keys move when stores are added.
4. Reports the percentage of keys assigned to each store.

Run:
    python hash_distribution_test.py
"""

from collections import Counter

from consistent_hash import ConsistentHash


NUM_KEYS = 300
REPLICAS = 100

NODES = [
    "http://kv1:8080",
    "http://kv2:8080",
    "http://kv3:8080"
]

# Generate the same style of keys used by benchmark.py.
keys = [f"key_{i}" for i in range(NUM_KEYS)]


def measure_distribution(nodes):
    """Count how many keys are assigned to each node."""

    ring = ConsistentHash(nodes, replicas=REPLICAS)

    assignments = {
        key: ring.get_node(key)
        for key in keys
    }

    counts = Counter(assignments.values())

    print(f"\nConfiguration: {len(nodes)} KV store(s)")
    print("-" * 50)

    for node in nodes:
        count = counts[node]
        percentage = count / NUM_KEYS * 100

        print(
            f"{node}: {count} keys "
            f"({percentage:.2f}%)"
        )

    return assignments


def measure_remapping(old_assignments, new_assignments):
    """Count keys that change owners after adding a node."""

    moved = 0

    for key in keys:
        if old_assignments[key] != new_assignments[key]:
            moved += 1

    percentage = moved / NUM_KEYS * 100

    print(f"\nKeys remapped: {moved}/{NUM_KEYS}")
    print(f"Percentage remapped: {percentage:.2f}%")
    print(f"Percentage retained: {100 - percentage:.2f}%")


if __name__ == "__main__":

    print("=" * 50)
    print("CONSISTENT HASHING DISTRIBUTION TEST")
    print("=" * 50)

    # Test one store.
    one_store = measure_distribution(NODES[:1])

    # Test two stores.
    two_stores = measure_distribution(NODES[:2])

    # Test three stores.
    three_stores = measure_distribution(NODES[:3])

    # Measure changes when adding a second store.
    print("\n" + "=" * 50)
    print("MEMBERSHIP CHANGE: 1 STORE -> 2 STORES")
    print("=" * 50)

    measure_remapping(one_store, two_stores)

    # Measure changes when adding a third store.
    print("\n" + "=" * 50)
    print("MEMBERSHIP CHANGE: 2 STORES -> 3 STORES")
    print("=" * 50)

    measure_remapping(two_stores, three_stores)

    print("\nTest completed.")
