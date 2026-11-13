
"""
Distributed KV-store benchmark.

Usage:
    python benchmark.py
    python benchmark.py set
    python benchmark.py get

Configuration:
    BASE_URL=http://127.0.0.1:8080
    NUM_THREADS=3
    OPS_PER_THREAD=100
    RUN_LABEL=1_store

The benchmark sends all requests through the coordinator.
"""

import csv
import os
import queue
import sys
import threading
import time

import requests

BASE_URL = os.getenv("BASE_URL", "http://127.0.0.1:8080").rstrip("/")
NUM_THREADS = int(os.getenv("NUM_THREADS", "3"))
OPS_PER_THREAD = int(os.getenv("OPS_PER_THREAD", "100"))
NUM_KEYS = NUM_THREADS * OPS_PER_THREAD

PRINT_INTERVAL = 3
MAX_LOGGED_PROBLEMS = 5
RUN_LABEL = os.getenv("RUN_LABEL", "manual")

CSV_FILE = "benchmark_results.csv"

_local = threading.local()
_log_lock = threading.Lock()
_logged = 0


def log_problem(msg):
    global _logged

    with _log_lock:
        _logged += 1

        if _logged <= MAX_LOGGED_PROBLEMS:
            print(msg)
        elif _logged == MAX_LOGGED_PROBLEMS + 1:
            print("  (Further errors suppressed.)")


def session():
    if not hasattr(_local, "session"):
        _local.session = requests.Session()

    return _local.session


def kv_store_operation(op_type, key, value):
    """Returns 'ok', 'mismatch', or 'error'."""

    try:
        if op_type == "set":
            response = session().post(
                f"{BASE_URL}/{key}",
                json={"value": value},
                timeout=10
            )

            response.raise_for_status()
            return "ok"

        elif op_type == "get":
            response = session().get(
                f"{BASE_URL}/{key}",
                timeout=10
            )

            response.raise_for_status()

            got = response.json().get("value")

            if got == value:
                return "ok"

            log_problem(
                f"Mismatch on get '{key}': "
                f"expected {value!r}, got {got!r}"
            )

            return "mismatch"

        else:
            raise ValueError(f"Invalid operation: {op_type}")

    except Exception as error:
        log_problem(
            f"Error during {op_type} for '{key}': {error}"
        )

        return "error"


class PhaseStats:

    def __init__(self):
        self.lock = threading.Lock()
        self.latencies = []
        self.mismatch = 0
        self.error = 0


def worker(q, stats, barrier):

    barrier.wait()

    while True:
        try:
            op, key, value = q.get_nowait()
        except queue.Empty:
            return

        start = time.perf_counter()

        status = kv_store_operation(op, key, value)

        latency = time.perf_counter() - start

        with stats.lock:
            if status == "ok":
                stats.latencies.append(latency)

            elif status == "mismatch":
                stats.mismatch += 1

            else:
                stats.error += 1


def monitor(stats, stop):

    seen = 0
    last = time.perf_counter()

    while not stop.wait(PRINT_INTERVAL):

        with stats.lock:
            window = stats.latencies[seen:]

        now = time.perf_counter()

        if window:
            throughput = len(window) / (now - last)

            avg_latency = (
                1000 * sum(window) / len(window)
            )

            print(
                f"  [last {now - last:.1f}s] "
                f"{throughput:.1f} ops/s, "
                f"avg latency {avg_latency:.2f} ms"
            )

        seen += len(window)
        last = now


def run_phase(op_type):

    q = queue.Queue()

    for i in range(NUM_KEYS):
        q.put((
            op_type,
            f"key_{i}",
            f"value_{i}"
        ))

    stats = PhaseStats()

    barrier = threading.Barrier(NUM_THREADS + 1)
    stop = threading.Event()

    workers = [
        threading.Thread(
            target=worker,
            args=(q, stats, barrier)
        )
        for _ in range(NUM_THREADS)
    ]

    monitor_thread = threading.Thread(
        target=monitor,
        args=(stats, stop),
        daemon=True
    )

    for thread in workers:
        thread.start()

    monitor_thread.start()

    barrier.wait()

    start = time.perf_counter()

    for thread in workers:
        thread.join()

    elapsed = time.perf_counter() - start

    stop.set()
    monitor_thread.join()

    return stats, elapsed


def percentile(values, percent):

    if not values:
        return float("nan")

    index = int((percent / 100) * (len(values) - 1))

    return values[index] * 1000


def report(name, stats, elapsed):

    latencies = sorted(stats.latencies)

    successful = len(latencies)

    average = (
        1000 * sum(latencies) / successful
        if successful else float("nan")
    )

    p50 = percentile(latencies, 50)
    p95 = percentile(latencies, 95)
    p99 = percentile(latencies, 99)

    throughput = (
        successful / elapsed
        if elapsed > 0 else 0
    )

    print(
        f"{name}: "
        f"ok={successful} "
        f"mismatch={stats.mismatch} "
        f"error={stats.error} "
        f"time={elapsed:.2f}s "
        f"throughput={throughput:.1f} ops/s "
        f"avg={average:.2f} ms "
        f"p50={p50:.2f} ms "
        f"p95={p95:.2f} ms "
        f"p99={p99:.2f} ms"
    )

    return {
        "phase": name,
        "successful": successful,
        "mismatches": stats.mismatch,
        "errors": stats.error,
        "elapsed_seconds": elapsed,
        "throughput_ops_sec": throughput,
        "avg_latency_ms": average,
        "p50_latency_ms": p50,
        "p95_latency_ms": p95,
        "p99_latency_ms": p99
    }


def save_results(rows):

    file_exists = os.path.exists(CSV_FILE)

    fieldnames = [
        "run_label",
        "threads",
        "operations_per_thread",
        "phase",
        "successful",
        "mismatches",
        "errors",
        "elapsed_seconds",
        "throughput_ops_sec",
        "avg_latency_ms",
        "p50_latency_ms",
        "p95_latency_ms",
        "p99_latency_ms"
    ]

    with open(CSV_FILE, "a", newline="") as file:

        writer = csv.DictWriter(
            file,
            fieldnames=fieldnames
        )

        if not file_exists:
            writer.writeheader()

        for row in rows:
            writer.writerow({
                "run_label": RUN_LABEL,
                "threads": NUM_THREADS,
                "operations_per_thread": OPS_PER_THREAD,
                **row
            })

    print(f"\nResults saved to {CSV_FILE}")


if __name__ == "__main__":

    phases = sys.argv[1:] or ["set", "get"]

    if any(phase not in ("set", "get") for phase in phases):
        sys.exit("Usage: python benchmark.py [set] [get]")

    results = []

    print("\nDistributed KV-Store Benchmark")
    print(f"Coordinator: {BASE_URL}")
    print(f"Configuration: {RUN_LABEL}")
    print(f"Threads: {NUM_THREADS}")
    print(f"Operations per thread: {OPS_PER_THREAD}")
    print(f"Total keys: {NUM_KEYS}")

    for phase in phases:

        print(f"\nRunning {phase.upper()} phase...")

        stats, elapsed = run_phase(phase)

        results.append(report(
            phase.upper(),
            stats,
            elapsed
        ))

    print("\nFinal Results")

    total_ok = sum(row["successful"] for row in results)
    total_time = sum(row["elapsed_seconds"] for row in results)

    for row in results:
        print(
            f"{row['phase']}: "
            f"{row['throughput_ops_sec']:.1f} ops/s"
        )

    print(
        f"\nTOTAL: {total_ok} successful operations "
        f"in {total_time:.2f}s"
    )

    save_results(results)
