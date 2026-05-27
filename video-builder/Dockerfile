FROM python:3.11-slim

# Cài FFmpeg và font hỗ trợ tiếng Việt
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    fonts-dejavu-core \
    fonts-noto-cjk \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN mkdir -p uploads output

EXPOSE 5000

CMD ["python", "web_app.py"]
