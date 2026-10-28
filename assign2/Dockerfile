# 1. Base image: lightweight Alpine Linux with Python 3.12 preinstalled
FROM python:3.12-alpine

# All following commands run inside /app
WORKDIR /app

# 2. Dependencies: copy the requirements list first so this layer is cached
#    and Flask is not reinstalled every time server.py changes
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 3. Application files
COPY server.py .

# 4. Exposure: bind to all interfaces so clients outside the container can connect,
#    and declare the port the server listens on
ENV HOST=0.0.0.0 PORT=8080 DATA_DIR=/app/data
RUN mkdir -p /app/data
EXPOSE 8080

# 5. Entry point: start the server when the container launches
CMD ["python", "server.py"]
