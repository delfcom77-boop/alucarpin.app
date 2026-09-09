FROM python:3.12-slim

WORKDIR /app

COPY requirements-api.txt .
RUN pip install --no-cache-dir -r requirements-api.txt

COPY api_central.py autenticacion.py base_datos.py ./
RUN mkdir -p app_web
COPY app_web/login.html app_web/inicio.html app_web/mi_control.html app_web/agenda.html app_web/administrador.html app_web/ayudante.html app_web/manifest.json app_web/pwa.js app_web/sw.js app_web/icon.svg app_web/icon-192.png app_web/icon-512.png ./app_web/
COPY empresa.db ./empresa.db

ENV ALUCARPIN_DATABASE=/app/empresa.db
ENV PORT=8000

EXPOSE 8000

CMD ["sh", "-c", "uvicorn api_central:app --host 0.0.0.0 --port ${PORT}"]