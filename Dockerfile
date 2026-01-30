FROM python:3.12-slim

# Install system dependencies and uv
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && pip install uv

WORKDIR /app

# Copy dependency files
COPY pyproject.toml .

# Install dependencies using uv
# --system installs into the system python environment, avoiding the need for a venv in the container
RUN uv pip install --system -r pyproject.toml

# Copy application code
COPY . .

# Create uploads directory
RUN mkdir -p uploads

# Expose ports (FastAPI: 8000, Streamlit: 8501)
EXPOSE 8000 8501

# Default command (overridden in docker-compose)
CMD ["uv", "run", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
