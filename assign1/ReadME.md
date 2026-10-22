# Single-Server Key-Value Store 
Python Flask application that supports GET, PUT, and DELETE operations, concurrent requests, JSON-File persistence, and timestamped logging.

## Project Structure 
assign1/
├── server.py
├── benchmark.py
├── requirements.txt
├── ReadME.md
└── report.MD

data.json and kvstore.log are generated automatically when needed. 

### Setup Environment 
Note: these are macOS or Linux commands
1. Open terminal and navigate to project directory: 
   `cd assign1`
2. Create virtual environment: 
   `python3 -m venv .venv`
3. Activate it: 
   `source .venv/bin/activate`
4. Install dependencies: 
   `python -m pip install -r requirements.txt`
5. Start the server: 
   `python3 server.py`
   Server listens at: http://127.0.0.1:8080

Keep this terminal running while testing the application. 
Open a second terminal for client requests and benchmarking and following steps 1-3 for activating the virtual environment. 

## Tests 

#### Check server status 
`curl -i http://127.0.0.1:8080/`

#### Create a Key with PUT 
`curl -i -X PUT http://127.0.0.1:8080/name \
  -H "Content-Type: application/json" \
  -d '{"value":"John"}'`

### Create a Key with POST
`curl -i -X POST http://127.0.0.1:8080/posttest \
  -H "Content-Type: application/json" \
  -d '{"value":"POST works"}'`

#### Retrieve a Value with GET
`curl -i http://127.0.0.1:8080/name`

#### Update an Existing Key 
`curl -i -X PUT http://127.0.0.1:8080/name \
  -H "Content-Type: application/json" \
  -d '{"value":"Updated value"}'`

#### Delete a Key 
`curl -i -X DELETE http://127.0.0.1:8080/name`

#### Test a Missing Key 
`curl -i http://127.0.0.1:8080/missing`

#### Test Invalid PUT Requests 

Missing the required value field:\
`curl -i -X PUT http://127.0.0.1:8080/test \
    -H "Content-Type: application/json" \
    -d '{}'`\
Expected response: 400 Bad Request

Using an invalid content type:\
`curl -i -X PUT http://127.0.0.1:8080/test \
  -H "Content-Type: text/plain" \
  -d 'hello'`\
Expected response: 400 Bad Request


#### Verify Persistence 
Server saves successful PUT and DELETE operations to data.json

To verify persistence: 
1. Start the server
2. Store a value: 
  `curl -X PUT http://127.0.0.1:8080/persistent \
  -H "Content-Type: application/json" \
  -d '{"value":"survives restart"}'`
3. Stop the server using Ctrl+C.
4. Restart it: `python3 server.py`
5. Retrieve the saved value:
  `curl http://127.0.0.1:8080/persistent`
Server should return the previously store value. 

#### Run the Performance Benchmark
Ensure the server is running before starting the benchmark.\
`python3 benchmark.py`

#### Logging 
Server writes timestamped log messages to kvstore.log. Log records successful operations, missing-key requests, invalid PUT requests, and persistence errors where logging is implemented. 
