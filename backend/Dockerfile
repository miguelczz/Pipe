# Dockerfile para Pipe Backend
# Incluye Python, tshark y todas las dependencias necesarias

FROM python:3.11-slim

# Metadatos
LABEL maintainer="Pipe Team"
LABEL description="Pipe Backend API - Análisis inteligente de capturas Wireshark para Band Steering y protocolos 802.11k/v/r"

# Variables de entorno
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Instalar dependencias del sistema y tshark
RUN apt-get update && apt-get install -y --no-install-recommends \
    # Herramientas básicas
    curl \
    wget \
    ca-certificates \
    # tshark y herramientas de red
    tshark \
    wireshark-common \
    # Dependencias para compilación de paquetes Python
    gcc \
    g++ \
    libpq-dev \
    # Limpieza
    && rm -rf /var/lib/apt/lists/*

# Crear usuario no root para seguridad
RUN useradd -m -u 1000 pipe && \
    mkdir -p /app /app/databases/uploads /app/data/fragments /app/data/analyses && \
    chown -R pipe:pipe /app

# Establecer directorio de trabajo
WORKDIR /app

# Copiar archivos de dependencias primero (para cache de Docker)
COPY requirements.txt .

# Instalar dependencias de Python
RUN pip install --upgrade pip && \
    pip install -r requirements.txt

# Copiar código de la aplicación (asegurar que src se copia)
COPY src/ ./src/
COPY main.py .
COPY index_docs.py .
COPY langgraph.json .
COPY requirements.txt .

# Copiar frontend construido si existe (opcional, para producción)
# Si no existe, el backend funcionará sin frontend (solo API)
# Crear el directorio primero
RUN mkdir -p ./frontend_dist
# Nota: Si frontend_dist no existe en el contexto de build, esta línea fallará
# Para hacerlo opcional, se debe usar un .dockerignore o un script de build
# Por ahora, comentamos esta línea y el frontend se servirá desde otro lugar si es necesario
# COPY frontend_dist ./frontend_dist/

# Cambiar propiedad de archivos
RUN chown -R pipe:pipe /app

# Cambiar a usuario no root
USER pipe

# Exponer puerto
EXPOSE 8000

# Healthcheck (curl ya está instalado arriba)
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8000/ || exit 1

# Comando de inicio
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
