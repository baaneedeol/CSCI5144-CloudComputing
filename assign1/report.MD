# CSCI 5144 Cloud Computing — Assignment 1

## Single-Server Key-Value Store

### Design Decisions

We implemented a key-value store using Python and Flask because they provide a lightweight way to build an HTTP server with minimal dependencies. The server runs on port 8080 and supports GET, PUT, POST, and DELETE requests. Values are stored in a Python dictionary, and a thread lock protects access to shared data. Flask's threaded mode allows the server to handle multiple client requests concurrently.

For persistence, the server writes the current dictionary to a JSON file after successful PUT, POST, and DELETE operations. It writes to a temporary file and replaces the existing data file after the write completes, reducing the risk of partial writes. Timestamped logging records successful operations, missing keys, errors, and server activity.

### Challenges and Testing

An important implementation challenge was maintaining consistency when multiple requests modify the same key. This was addressed by protecting dictionary access and file updates with a thread lock. Another challenge was preventing failed disk writes from leaving the in-memory store inconsistent with the saved data. The application addresses this by retaining previous values and restoring them if persistence fails.

Request validation was another consideration. The server checks that POST and PUT requests contain JSON data with a `value` field and rejects values that cannot be serialized as valid JSON. It also returns appropriate HTTP status codes for invalid requests, missing keys, and persistence errors. Functional testing covered GET, PUT, POST, and DELETE operations, updating existing values, invalid requests, missing keys, and persistence across server restarts. Concurrent requests were also tested.

The benchmark used three concurrent client threads to write 300 keys and read them back, verifying that each retrieved value matched the value originally stored. The test completed **600 successful operations with zero errors and zero mismatches**. The write phase achieved a throughput of **615.4 operations per second**, with an average latency of **4.86 ms** and a p99 latency of **15.46 ms**. The read phase achieved a throughput of **1,551.4 operations per second**, with an average latency of **1.93 ms** and a p99 latency of **3.49 ms**. The complete benchmark took **0.68 seconds**, achieving an overall throughput of **881.2 operations per second**. These results demonstrate correct storage and retrieval under the tested concurrent workload.

**Note:** The benchmark results are from a single run on a Linux machine. Performance measurements may vary across different runs and hardware configurations.

### Assumptions and Future Improvements

The implementation assumes a single server process running locally at `127.0.0.1:8080`. The store is expected to contain JSON-compatible values, and the JSON file is assumed to be accessible and writable. A missing data file indicates that the server should start with an empty store, whereas an unreadable or invalid existing file prevents startup to avoid silently discarding saved data. The application is intended for a small-scale assignment rather than a production environment.

Potential improvements include optimizing disk persistence to reduce lock contention, supporting larger datasets through a dedicated storage engine, and adding configurable concurrency and workload settings. Benchmarking could be extended to compare performance across different thread counts and operation mixes. Further improvements could include automated tests for concurrent reads, writes, and deletes, stronger crash-recovery guarantees, request-size limits, and authentication if the service were exposed beyond the local machine.

Overall, the project demonstrates the core design of a concurrent key-value service while addressing data consistency, persistence, input validation, logging, and performance testing.