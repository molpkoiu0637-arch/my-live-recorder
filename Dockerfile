FROM python:3.11-slim
ENV PYTHONHTTPSVERIFY=0
RUN apt-get update && apt-get install -y ffmpeg ca-certificates && update-ca-certificates --fresh && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD gunicorn app:app --bind 0.0.0.0:$PORT --timeout 300
