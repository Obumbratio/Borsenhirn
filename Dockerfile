FROM python:3.12-slim

WORKDIR /app

# Install system dependencies for psycopg2
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev gcc && \
    rm -rf /var/lib/apt/lists/*

# Pre-install setuptools and wheel to satisfy unpinned dependencies when installing with hashes
RUN pip install --no-cache-dir setuptools wheel

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Create directories
RUN mkdir -p logs models results reports

EXPOSE 8000 8501

CMD ["python", "main.py"]
