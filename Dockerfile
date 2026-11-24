# ── Etapa 1: Builder ─────────────────────────────────────────
# Instala dependencias en una capa aparte para aprovechar el cache de Docker.
FROM python:3.14-slim AS builder

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential libpq-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt


# ── Etapa 2: Runtime ────────────────────────────────────────
FROM python:3.14-slim

# Dependencia de runtime para psycopg2, pg_dump (respaldos) y ONNX (fastembed)
RUN apt-get update && apt-get install -y --no-install-recommends \
        libpq5 postgresql-client libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# Copiar paquetes instalados desde el builder
COPY --from=builder /install /usr/local

# Crear usuario no-root por seguridad
RUN useradd --create-home appuser
WORKDIR /app

# Copiar el código fuente
COPY . .

# Crear directorios necesarios y dar permisos
RUN mkdir -p staticfiles respaldos modelos \
    && chown -R appuser:appuser /app

# Convertir finales de línea Windows→Linux y dar permisos
RUN sed -i 's/\r$//' startup.sh && chmod +x startup.sh

# Cambiar a usuario no-root
USER appuser

# Puerto por defecto de Gunicorn
EXPOSE 8000

# Health check: verifica que la app responda
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/salud/')" || exit 1

# Arrancar la aplicación
CMD ["./startup.sh"]
