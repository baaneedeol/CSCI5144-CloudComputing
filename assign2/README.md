# Assignment 2: Dockerizing the Key-Value Store

The Flask key-value store from Assignment 1, packaged as a Docker image.

## Files

```
hw2/
├── Dockerfile          # Recipe for building the image
├── .dockerignore       # Files that must not be copied into the image
├── requirements.txt    # Python dependencies (Flask)
├── server.py           # Key-value store server
└── README.md
```

## How the Dockerfile meets the requirements

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

## Build the image

```bash
cd hw2
docker build -t kvstore .
```

## Run the container

```bash
docker run --rm -p 8080:8080 --name kv kvstore
```

`-p 8080:8080` forwards port 8080 on your machine to port 8080 in the container.

Optional: keep `data.json` on the host so data survives when the container is removed:

```bash
docker run --rm -p 8080:8080 --name kv -v "$(pwd)/data:/app/data" kvstore
```

## Test (from a second terminal)

```bash
# status
curl -i http://localhost:8080/

# create / update
curl -i -X PUT http://localhost:8080/name \
  -H "Content-Type: application/json" -d '{"value":"John"}'

# read
curl -i http://localhost:8080/name

# delete
curl -i -X DELETE http://localhost:8080/name

# missing key -> 404
curl -i http://localhost:8080/missing
```

## Stop and clean up

```bash
docker stop kv          # stop the container (--rm removes it automatically)
docker images           # list images
docker rmi kvstore      # remove the image
```
