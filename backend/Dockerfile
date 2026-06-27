FROM python:3.12-slim

# Install curl for the HEALTHCHECK
RUN apt-get update && apt-get install -y --no-install-recommends curl && \
    rm -rf /var/lib/apt/lists/*

# Create a non-root user and group
RUN groupadd --gid 1001 appgroup && \
    useradd --uid 1001 --gid appgroup --no-create-home appuser

WORKDIR /app

# Install Python dependencies first (layer-cache friendly)
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source
COPY stocktrack/ ./stocktrack/
COPY pyproject.toml ./

# Create the data directory and assign ownership to the non-root user.
# In production this path is a named volume; we pre-create it so the
# volume mount inherits the correct ownership.
RUN mkdir -p /data && chown appuser:appgroup /data

EXPOSE 9180

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:9180/api/health || exit 1

USER appuser

CMD ["uvicorn", "stocktrack.main:create_app", "--factory", \
     "--host", "0.0.0.0", "--port", "9180"]
