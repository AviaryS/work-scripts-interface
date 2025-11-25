#!/bin/bash
# Скрипт для запуска бекенда

# Активация виртуального окружения если оно существует
if [ -d "venv" ]; then
    source venv/bin/activate
fi

# Запуск сервера
uvicorn main:app --reload --host 0.0.0.0 --port 8000

