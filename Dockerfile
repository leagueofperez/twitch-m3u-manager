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

COPY start.sh .
COPY app ./app
COPY twitch ./twitch
RUN chmod +x /app/start.sh

EXPOSE 8000
CMD ["/app/start.sh"]
