#!/bin/bash
# Скрипт для запуска фронтенда

# Установка зависимостей если нужно
if [ ! -d "node_modules" ]; then
    echo "Устанавливаю зависимости..."
    npm install
fi

# Запуск dev сервера
npm run dev

