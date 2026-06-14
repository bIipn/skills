FROM python:3.12-slim

WORKDIR /app

# Install deps first for layer caching.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Defaults to safe paper-trading simulation; override via -e PM_* env vars.
ENV PM_DATA_MODE=paper \
    PM_EXECUTION_MODE=paper \
    PM_DB_PATH=/data/arb_trades.db

VOLUME ["/data"]
EXPOSE 8000

# Run the dashboard + engine. Bind to 0.0.0.0 so the port is reachable.
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
