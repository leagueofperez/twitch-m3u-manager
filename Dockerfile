FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY start.sh .
COPY app ./app
COPY twitch ./twitch
RUN chmod +x /app/start.sh

EXPOSE 8000
CMD ["/app/start.sh"]
