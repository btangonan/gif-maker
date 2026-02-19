FROM python:3.11-slim

# Install ffmpeg and libvips system libraries
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    libvips-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Install Python bindings
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

WORKDIR /app
COPY app.py .
RUN mkdir -p output

CMD ["python3", "app.py"]
