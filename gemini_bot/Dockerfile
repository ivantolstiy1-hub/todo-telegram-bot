FROM python:3.11-slim

# Установка системных зависимостей
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Копирование зависимостей и установка
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копирование исходного кода бота
COPY . .

# Порт по умолчанию для Render
ENV PORT=10000
EXPOSE 10000

# Запуск бота с встроенным health-сервером
CMD ["python", "main.py"]
