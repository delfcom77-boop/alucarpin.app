FROM python:3.12-slim

WORKDIR /app

COPY requirements-api.txt .
RUN pip install --no-cache-dir -r requirements-api.txt

COPY api_central.py autenticacion.py base_datos.py ./
RUN mkdir -p app_web
COPY login.html administrador.html ayudante.html ./app_web/
COPY empresa.db ./empresa.db

ENV ALUCARPIN_DATABASE=/app/empresa.db
ENV PORT=8000

EXPOSE 8000

CMD ["sh", "-c", "uvicorn api_central:app --host 0.0.0.0 --port ${PORT}"]