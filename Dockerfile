# syntax=docker/dockerfile:1
# DEMANDA-IA · imagen multi-etapa
#   docker build -t demanda-ia:1.0.0 .                 -> imagen de producción (etapa final)
#   docker build --target pruebas -t demanda-ia:test . -> corre la suite de pytest dentro del build

# ---------- Etapa 1: dependencias de ejecución en un entorno virtual ----------
FROM python:3.12-slim AS dependencias
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
COPY requirements.txt .
RUN pip install -r requirements.txt

# ---------- Etapa 2 (opcional): pruebas automatizadas ----------
FROM dependencias AS pruebas
COPY requirements-dev.txt .
RUN pip install -r requirements-dev.txt
COPY src/ src/
COPY frontend/ frontend/
COPY models/ models/
COPY reports/metricas.json reports/metricas.json
COPY tests/ tests/
RUN PYTHONPATH=src python -m pytest -q

# ---------- Etapa 3: imagen final, ligera y sin privilegios ----------
FROM python:3.12-slim AS final
LABEL org.opencontainers.image.title="DEMANDA-IA" \
      org.opencontainers.image.description="API y frontend de pronostico de demanda por SKU y sucursal" \
      org.opencontainers.image.version="1.0.0"
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH" \
    PYTHONPATH=/app/src \
    MODEL_PATH=/app/models/demanda_ia_v1.joblib \
    PORT=8000 \
    WEB_CONCURRENCY=1
WORKDIR /app
RUN useradd --create-home --uid 10001 appuser
COPY --from=dependencias /opt/venv /opt/venv
COPY src/ src/
COPY frontend/ frontend/
COPY models/ models/
USER appuser

# Puerto de la API (las plataformas PaaS pueden inyectar otro valor en $PORT)
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import os,urllib.request; urllib.request.urlopen('http://127.0.0.1:%s/api/v1/salud' % os.environ.get('PORT','8000'), timeout=4)" || exit 1

CMD ["sh", "-c", "exec uvicorn demanda_ia.api:app --host 0.0.0.0 --port ${PORT} --workers ${WEB_CONCURRENCY}"]
