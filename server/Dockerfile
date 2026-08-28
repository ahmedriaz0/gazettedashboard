FROM python:3.11-slim

# Prevent Python from writing .pyc files & buffer output for real-time Docker logs
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Install Poppler and clean up apt cache in the same layer to minimize image size
RUN apt-get update && apt-get install -y --no-install-recommends \
    poppler-utils \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install dependencies using layer caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend application source
COPY . .

# Ensure temp_uploads directory exists with write permissions
RUN mkdir -p /app/temp_uploads

EXPOSE 8000

# Use array syntax for cleaner process signal handling (SIGTERM)
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}"]