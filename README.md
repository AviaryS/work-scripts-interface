# Work Scripts Interface

Веб-интерфейс для автоматизации подсчета времени разработки по нескольким периодам с генерацией Excel отчетов.

## Структура проекта

```
work-scripts-interface/
├── backend/          # FastAPI бекенд
│   ├── main.py      # Основной файл API
│   └── requirements.txt
└── frontend/        # React фронтенд
    ├── src/
    │   ├── App.tsx
    │   └── main.tsx
    └── package.json
```

## Установка и запуск

### Backend (FastAPI)

1. Перейдите в папку backend:
```bash
cd backend
```

2. Создайте виртуальное окружение:
```bash
python -m venv venv
source venv/bin/activate  # для macOS/Linux
# или
venv\Scripts\activate  # для Windows
```

3. Установите зависимости:
```bash
pip install -r requirements.txt
```

4. Запустите сервер:
```bash
python main.py
# или
uvicorn main:app --reload
```

API будет доступен по адресу: `http://localhost:8000`

### Frontend (React)

1. Перейдите в папку frontend:
```bash
cd frontend
```

2. Установите зависимости:
```bash
npm install
```

3. Запустите dev сервер:
```bash
npm run dev
```

Интерфейс будет доступен по адресу: `http://localhost:3000`

## Использование

1. Откройте веб-интерфейс в браузере
2. Загрузите JSON файл с данными (формат как в `example_table_release.json`)
3. Настройте периоды для анализа (можно добавить несколько)
4. При необходимости введите session cookie для доступа к API
5. Нажмите "Сгенерировать Excel" - файл автоматически скачается

## API Endpoints

- `GET /` - Проверка работы API
- `POST /api/upload-json` - Загрузка JSON файла с данными
- `POST /api/process` - Обработка данных и генерация Excel
- `GET /api/download/{filepath}` - Скачивание сгенерированного файла

## Формат данных

JSON файл должен содержать массив `items` с объектами, имеющими поля:
- `key` - ключ задачи
- `name` - название задачи
- `workspaceId` - ID рабочего пространства
- `workitemId` - ID элемента работы
- `assignee` - объект с полем `displayName` (имя исполнителя)

## Особенности

- Учитываются только рабочие дни (Пн-Пт)
- Рабочие часы: 08:00 - 17:00 МСК
- Подсчитывается время в статусе "in progress"
- Поддержка нескольких периодов в одном отчете
- Каждый период выводится на отдельный лист Excel

