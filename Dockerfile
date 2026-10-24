FROM python:3.11-slim

# ติดตั้ง ffmpeg ของจริง - ตัวอัดวิดีโอ
RUN apt-get update && apt-get install -y ffmpeg && apt-get clean

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py .

RUN mkdir -p downloads

# Render ใช้พอร์ตจาก env PORT
CMD gunicorn --bind 0.0.0.0:$PORT --workers 1 --threads 4 --timeout 600 app:app
