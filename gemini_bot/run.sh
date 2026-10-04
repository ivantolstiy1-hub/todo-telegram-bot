#!/bin/bash
# Скрипт быстрого запуска Telegram-бота Gemini

set -e

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
cd "$DIR"

echo "=================================================="
echo "🚀 Запуск Gemini Telegram Bot..."
echo "=================================================="

# Активация виртуального окружения
if [ -d "venv" ]; then
    source venv/bin/activate
fi

# Проверка наличия .env файла
if [ ! -f ".env" ]; then
    echo "❌ Ошибка: Файл .env не найден!"
    echo "Скопируйте .env.example в .env и заполните TELEGRAM_BOT_TOKEN и GEMINI_API_KEY."
    exit 1
fi

# Экспорт переменных Antigravity Language Server
if [ -z "$ANTIGRAVITY_LS_ADDRESS" ]; then
    export ANTIGRAVITY_LS_ADDRESS="localhost:56105"
    export ANTIGRAVITYLSADDRESS="localhost:56105"
    export ANTIGRAVITY_CSRF_TOKEN="12f77acd-b384-49eb-87ef-69caac06371a"
fi

# Запуск основного скрипта
python3 main.py
