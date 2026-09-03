# Track C's service layer only -- `service/api.py` served over uvicorn. Not
# used by pytest, run_all.py, or any of the graded evaluation; a cold clone
# for THAT purpose needs no container at all (see README.md's "Run it").
FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt requirements-service.txt ./
RUN pip install --no-cache-dir -r requirements.txt -r requirements-service.txt

COPY . .

# The SQLite file lives on a mounted volume (see docker-compose.yml) so it
# survives a container restart -- the whole point of Track C's persistence
# layer is that a run outlives the process that wrote it.
ENV STORE_DB_PATH=/data/recon.db
VOLUME ["/data"]

EXPOSE 8000

CMD ["python3", "-m", "uvicorn", "service.asgi:app", "--host", "0.0.0.0", "--port", "8000"]
