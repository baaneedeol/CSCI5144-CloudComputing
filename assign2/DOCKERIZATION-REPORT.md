# Dockerization Report

The `assign2` key-value store meets the five Dockerization requirements:

- **Base image:** `python:3.12-alpine`.
- **Application files:** `server.py` is copied into the image.
- **Dependencies:** Flask is installed from `requirements.txt`.
- **Port:** The server binds to `0.0.0.0:8080`, and the image declares `EXPOSE 8080`.
- **Startup:** The container starts the server with `python server.py`.

The README's directory references were corrected to `assign2`. The image build
could not be verified because the Docker Desktop Linux engine was unavailable.
