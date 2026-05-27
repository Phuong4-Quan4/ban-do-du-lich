#!/bin/bash
# Script khởi động ứng dụng

set -e
cd "$(dirname "$0")"

if [ ! -f .env ]; then
  cp .env.example .env
  echo "⚠  File .env chưa có. Đã tạo từ .env.example"
  echo "   Vui lòng điền TELEGRAM_TOKEN vào file .env trước khi chạy bot"
fi

mkdir -p uploads output

MODE=${1:-web}

case $MODE in
  web)
    echo "🌐 Khởi động Web UI tại http://localhost:5000"
    python web_app.py
    ;;
  bot)
    echo "🤖 Khởi động Telegram Bot..."
    python telegram_bot.py
    ;;
  all)
    echo "🚀 Khởi động cả Web + Bot..."
    python web_app.py &
    python telegram_bot.py
    ;;
  docker)
    echo "🐳 Khởi động bằng Docker Compose..."
    docker-compose up --build
    ;;
  *)
    echo "Dùng: ./start.sh [web|bot|all|docker]"
    exit 1
    ;;
esac
