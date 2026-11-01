# syntax=docker/dockerfile:1
FROM python:3.14-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Install dependencies first to leverage Docker layer caching
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy the backend application code and models config
COPY models.json ./models.json
COPY backend/ ./backend/

# Ensure runtime directories exist (populated volumes are excluded from the build)
RUN mkdir -p /app/backend/uploads /app/backend/faiss_indexes

EXPOSE 8000

CMD ["uvicorn", "backend.server:app", "--host", "0.0.0.0", "--port", "8000"]
