# ==========================================
# Pipe Backend - Dockerfile
# ==========================================

FROM python:3.11-slim

LABEL maintainer="Pipe Team"
LABEL description="Pipe - Análisis inteligente de capturas Wireshark"

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Instalar dependencias del sistema
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    wget \
    ca-certificates \
    tshark \
    wireshark-common \
    gcc \
    g++ \
    libpq-dev \
    libpango-1.0-0 \
    libpangoft2-1.0-0 \
    libcairo2 \
    libgdk-pixbuf-xlib-2.0-0 \
    libffi-dev \
    shared-mime-info \
    && rm -rf /var/lib/apt/lists/*

# Crear usuario no-root y directorios
RUN useradd -m -u 1000 pipe && \
    mkdir -p /app /app/databases/uploads /app/data/fragments /app/data/analyses /app/frontend_dist && \
    chown -R pipe:pipe /app

WORKDIR /app

# Instalar dependencias Python
COPY backend/requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

# Copiar código fuente del backend
COPY backend/src/ ./src/
COPY backend/main.py .
COPY backend/index_docs.py .
COPY backend/langgraph.json .

RUN chown -R pipe:pipe /app

USER pipe

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8000/ || exit 1

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]