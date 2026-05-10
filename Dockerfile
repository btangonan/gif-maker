FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1

# Install ffmpeg and libvips system libraries
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    gifski \
    libvips-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Install Python bindings
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

WORKDIR /app
COPY app.py .
RUN mkdir -p output

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python3 -c "import os, urllib.request; port=os.environ.get('PORT','7878'); urllib.request.urlopen(f'http://127.0.0.1:{port}/healthz', timeout=3).read()"

CMD ["python3", "app.py"]
