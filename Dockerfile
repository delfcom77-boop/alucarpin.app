FROM python:3.12-slim

WORKDIR /app

COPY requirements-api.txt .
RUN pip install --no-cache-dir -r requirements-api.txt

COPY api_central.py autenticacion.py base_datos.py ./
COPY app_web ./app_web
COPY empresa.db ./empresa.db

ENV ALUCARPIN_DATABASE=/data/empresa.db
ENV PORT=8000

EXPOSE 8000

CMD ["sh", "-c", "if [ ! -f \"$ALUCARPIN_DATABASE\" ]; then cp empresa.db \"$ALUCARPIN_DATABASE\"; fi; uvicorn api_central:app --host 0.0.0.0 --port ${PORT}"]