# Assignment 3: Enhancing Key-Value Store with Consistent Hashing Across Multiple Instances

This assignment extends the Flask key-value store from Assignment 1 and the Docker implementation from Assignment 2 into a distributed key-value store.

## Architecture

System contains four containers: 
1. Coordinator: Receives client requests, manages membership, and routes operations.
2. KV Store 1: First independent key-value storage instance.
3. KV Store 2: Second independent key-value storage instance.
4. KV Store 3: Third independent key-value storage instance.

                  Client / Benchmark
                           |
                           v
                  Coordinator :8080
                           |
                    Consistent Hashing
                           |
              +------------+------------+
              |            |            |
              v            v            v
           KV Store 1   KV Store 2   KV Store 3
             kv1          kv2          kv3
           :8080        :8080        :8080

Clients send requests to the coordinator at localhost:8080. The coordinator determines the appropriate storage node and forwards the request.

The containers communicate over the Docker Compose network using service names, such as http://kv1:8080.

### Port Configuration 

Service - Docker Service - Host Port - Container port 
Coordinator - coordinator - 8080 - 8080 
KV Store 1 - kv1 - 8081 - 8080 
KV Store 2 - kv2 - 8082 - 8080
KV Store 3 - kv3 - 8083 - 8080

The host ports allow requests from your computer to reach the individual containers. Inside the Docker network, each container uses port 8080.

## Files

```text
assign3/
│
├── Dockerfile
├── .dockerignore
├── requirements.txt
│
├── server.py                     # Flask KV storage instance
├── coordinator.py                # Request routing, membership, and migration
├── consistent_hash.py            # Consistent-hashing implementation
│
├── docker-compose.yml            # Coordinator and three KV-store containers
│
├── benchmark.py                  # Concurrent SET and GET benchmarks
├── benchmark_results.csv         # Raw benchmark measurements
├── analyze_benchmarks.py         # Benchmark analysis and chart generation
├── benchmark-analysis/           # Contains analysis and charts generated
├── requirements-analysis.txt
│
├── tests/
│   ├── hash_distribution.py      # Tests key distribution and remapping
│   ├── end_to_end_test.py        # Tests data migration and accessibility
│   └── persistence_test.py       # Tests persistence after container restarts
│
├── REPORT.md
└── README.md
```

The `tests/` directory contains the scripts used to verify key distribution, data migration, and persistence. Benchmarking and analysis scripts remain in the main project directory.

## Prerequisites 

Install the following: 
- Docker Desktop 
- Docker Compose v2
- Python 3
- pip 
Start Docker Desktop before running the assignment. 

Verify the installations: 
- docker --version
- docker compose version
- python3 --version
- pip3 --version

## How the Dockerfile meets the requirements 

From Assign 2: 
| Requirement       | Dockerfile instruction                                   |
|-------------------|----------------------------------------------------------|
| Base image        | `FROM python:3.12-alpine` (lightweight Linux + Python)   |
| Dependencies      | `COPY requirements.txt .` + `RUN pip install ...`        |
| Application files | `COPY server.py .`                                       |
| Exposure          | `ENV HOST=0.0.0.0` + `EXPOSE 8080`                        |
| Entry point       | `CMD ["python", "server.py"]`                            |

`server.py` reads `HOST`, `PORT` and `DATA_DIR` from environment variables.
Inside the container the server binds to `0.0.0.0` so clients outside the
container can reach it. Run locally (without Docker) it still defaults to
`127.0.0.1:8080` like Assignment 1.

For Assign 3: 
The image includes both the coordinator and storage application code. Docker Compose overrides the default command for the coordinator.

The storage containers run: `python3 server.py`

The coordinator runs: `python3 coordinator.py`

## Docker Compose Config 

Compose file defines four services and three persistent volumes. 

### Understanding the Config 

`build`: builds the Docker image using the root project directory as the build context. All four services use the same build configuration.

`command`: overrides the image's default command
- Coordinator: `python3 coordinator.py`
- Storage nodes: `python3 server.py`

`ports`: maps a host port to the container's port 8080

`environment`: the coordinator receives its initial node membership through KV_NODES
- `KV_NODES: ${KV_NODES:-http://kv1:8080}`
- This means that Docker Compose uses the value of the host environment variable KV_NODES if provided. Otherwise, it defaults to KV1.

`depends_on`: ensures that the KV-store containers are started before the coordinator container.

`volumes`: each store receives its own persistent data volume:
- kv1_data → /app/data
- kv2_data → /app/data
- kv3_data → /app/data

## Running the Assignment 

### Step 1: Navigate to project directory 
```bash
cd path/to/assign3
```

### Step 2: Build and Start the Cluster
```bash 
docker compose up -d --build
```
This command: 
1. Builds the shared Docker image using the root Dockerfile
2. Creates the Docker network.
3. Creates the three storage containers.
4. Creates the coordinator container.
5. Creates the persistent storage volumes if they do not already exist.
6. Starts the services in the background.

### Step 3: Verify that all containers are running
```bash 
docker compose ps
```
You should see:
- kv-coordinator
- kv-store-1
- kv-store-2
- kv-store-3

### Step 4: Test the services 
Check the coordinator: 
```bash 
curl -i http://localhost:8080/
```

Check the individual KV stores:
```bash 
curl -i http://localhost:8081/
curl -i http://localhost:8082/
curl -i http://localhost:8083/
```

## Test Key-Value Operations 
Send normal client requests through the coordinator 

### Create or update a key
```bash
curl -i -X PUT http://localhost:8080/name \
  -H "Content-Type: application/json" \
  -d '{"value":"John"}'
```

### Read a key
```bash
curl -i http://localhost:8080/name
```

### Delete a key
```bash
curl -i -X DELETE http://localhost:8080/name
```

### Request a missing key
```bash
curl -i http://localhost:8080/missing
```

A missing key should return the application's not-found response, normally HTTP 404.
These requests verify the basic operations through the coordinator.

## Configure the Number of Active Storage Nodes

The coordinator accepts membership updates through: `POST http://localhost:8080/admin/nodes`

The membership body contains the node URLs that should be active.

Use Docker service names because the coordinator communicates with storage containers inside the Docker network.

### One active store
```bash
curl -X POST http://localhost:8080/admin/nodes \
  -H "Content-Type: application/json" \
  -d '{"nodes":["http://kv1:8080"]}'
```

### Two active stores
```bash
curl -X POST http://localhost:8080/admin/nodes \
  -H "Content-Type: application/json" \
  -d '{"nodes":["http://kv1:8080","http://kv2:8080"]}'
```

### Three active stores
```bash
curl -X POST http://localhost:8080/admin/nodes \
  -H "Content-Type: application/json" \
  -d '{"nodes":["http://kv1:8080","http://kv2:8080","http://kv3:8080"]}'
```

Each update changes the active membership and the consistent-hash ring.

When the ring changes, keys whose owners have changed must be migrated to their new storage nodes. This allows previously stored data to remain accessible.

Important distinction:
- http://localhost:8081 is used when accessing KV1 from your host machine.
- http://kv1:8080 is used when the coordinator communicates with KV1 inside Docker.


## Run Tests 
Run the tests from the project root while the Docker Cluster is running. 

### Hash Distribution 
```bash 
python3 tests/hash_distribution.py
```
This test examines how 300 keys are distributed across one, two, and three storage nodes.

### End-to-End Migration
```bash
python3 tests/end_to_end_test.py
```
This test verifies that data remains available as storage nodes are added. 

### Persistence 
```bash
python3 tests/persistence_test.py
```
This test verifies that stored data survives Docker container restarts.

Run order: It is recommended to run the hash distribution test first, followed by the end-to-end migration test and then the persistence test.
All commands should be executed from the main assign3/ directory, not from inside tests/.

## Run Performance Benchmarks 
| Parameter     | Values                                  |
|-------------------|----------------------------------------------------------|
| Active storage nodes      | 1, 2, 3       |
| Client Threads            | 3, 10, 20     |
| Operations per thread     | 100           |
| Operation types           | SET and GET   |
| Trials per configuration  | 5             |

Each configuration measures SET and GET separately.

### Step 1: Set the active cluster size

#### For one store:
```bash
curl -X POST http://localhost:8080/admin/nodes \
  -H "Content-Type: application/json" \
  -d '{"nodes":["http://kv1:8080"]}'
```

#### For two stores:
```bash
curl -X POST http://localhost:8080/admin/nodes \
  -H "Content-Type: application/json" \
  -d '{"nodes":["http://kv1:8080","http://kv2:8080"]}'
```

#### For three stores:
```bash
curl -X POST http://localhost:8080/admin/nodes \
  -H "Content-Type: application/json" \
  -d '{"nodes":["http://kv1:8080","http://kv2:8080","http://kv3:8080"]}'
```

### Step 2: Configure benchmark threads
Open benchmark.py and set the desired thread count and operations per thread.

Use:
- 3 threads, 100 operations per thread.
- 10 threads, 100 operations per thread.
- 20 threads, 100 operations per thread.

Check the benchmark's actual configuration variable names before editing.

### Step 3: Run five trials per configuration

For example, with one active store and three threads:
```bash
for i in 1 2 3 4 5; do
  RUN_LABEL="1_store_run_$i" python3 benchmark.py
done
```

For two stores:
```bash
for i in 1 2 3 4 5; do
  RUN_LABEL="2_stores_run_$i" python3 benchmark.py
done
```

For three stores:
```bash
for i in 1 2 3 4 5; do
  RUN_LABEL="3_stores_run_$i" python3 benchmark.py
done
```
Repeat for 10 and 20 threads, using unique labels that include the thread count, such as:
- 10t_1_store_run_1
- 10t_2_stores_run_1
- 10t_3_stores_run_1
- 20t_1_store_run_1
- 20t_2_stores_run_1
- 20t_3_stores_run_1

Make sure each trial appends its results to `benchmark_results.csv`. Do not overwrite the CSV between configurations.

The experiment increases the total number of operations as the thread count increases. It therefore measures performance under increasing load rather than fixed-total-work concurrency.


## Analyze Benchmark Results
Run:
```bash
pip3 install -r requirements-analysis.txt 

python3 analyze_benchmarks.py \
  --input benchmark_results.csv \
  --output-dir benchmark_analysis
```

The script generates summary tables, validation results, and charts.

Expected outputs:
```
benchmark_analysis/
│
├── summary_by_threads_and_stores.csv
├── summary_by_threads_and_stores.md
├── validation.txt
│
├── throughput_set.png
├── throughput_get.png
├── avg_latency_set.png
├── avg_latency_get.png
├── latency_percentiles_set.png
├── latency_percentiles_get.png
│
└── generated_report.md
```

| Metric     | Meaning                                  |
|-------------------|----------------------------------------------------------|
| Throughput   | Number of operations completed per second. Higher is generally better.      |
| Average latency | Average time required for an operation. Lower is generally better.   |
| P50 latency | Median request latency.        |
| P95 latency | 95% of requests completed within this time.   |
| P99 latency  | 99% of requests completed within this time.    |
| Successful | Number of successful operations. | 
| Mismatches | Number of operations that returned unexpected data. | 
| Errors | Number of failed requests or exceptions. | 

## Stop the Cluster
When finished, stop and remove the containers and network: `docker compose down`

This preserves named volumes, so stored data remains available when the cluster is started again.

To start the cluster again: `docker compose up -d --build`

### Remove persistent data

If you intentionally want a completely clean setup, run: `docker compose down -v`

Warning: The -v option deletes the named volumes containing the KV-store data. Use it only when you want to remove persisted data and start fresh.

To inspect Docker images: `docker images`

To remove an image after the containers have been removed, use its actual image name or ID: `docker rmi IMAGE_NAME_OR_ID`
