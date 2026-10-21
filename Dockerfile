FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

RUN apt-get update \
    && apt-get install -y --no-install-recommends sqlite3 \
    && rm -rf /var/lib/apt/lists/* \
    && mkdir -p /app/data \
    && ln -s /app/data/.sqliterc /root/.sqliterc

COPY start.sh healthcheck.py ./
COPY app ./app
COPY twitch ./twitch
RUN chmod +x /app/start.sh /app/healthcheck.py

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD ["python", "/app/healthcheck.py"]
CMD ["/app/start.sh"]
