# CSci 5144 Cloud Computing - Assignment 1

## Single-Server Key-Value Store 

### Design Decisions
We implemented a key-value store using Python and Flask because they provide a simple way to build an HTTP server with minimal dependencies. The server runs on port 8080 and supports individual GET, PUT, and DELETE requests. Values are stored in a Python dictionary, and a thread lock protects the concurrent access to the shared data. Flask's threaded mode allows the server to handle multiple client requests concurrently. 

For persistence, the server write the current dictionary to a JSON file after successful PUT and DELETE operations. It writes to a temporary file and replaces the exisitng data file after the write completes. Timestamped logging records successful operations, missing keys, errors, and server activity. 

### Challenges and Testing 

### Assumptions and Future Improvements 


https://dev.to/devasservice/python-key-value-store-tutorial-build-encrypt-and-optimize-your-data-storage-62f
