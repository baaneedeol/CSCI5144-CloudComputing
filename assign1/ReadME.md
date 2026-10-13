# Run the Single-Server Key-Value Store 

From the assign 1 Directory: 

1. Activate virtual environment: 
   `source .venv/bin/activate`
2. Install dependencies: 
   `pip install -r requirements.txt`
3. Start the server: 
   `python3 server.py`
4. Open a second terminal
5. Activate virtual environment: 
   `source .venv/bin/activate`
6. Test a PUT: 
   `curl -i -X PUT http://127.0.0.1:8080/student \
  -H "Content-Type: application/json" \
  -d '{"value":"John"}'`
7. Test a GET: 
   `curl -i http://127.0.0.1:8080/student`
8. Test a DELETE: 
   `curl -i -X DELETE http://127.0.0.1:8080/student`
9.  Run benchmark: 
    `python3 benchmark.py`