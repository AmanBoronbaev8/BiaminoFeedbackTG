# Установка и запуск проекта

## Требования

- Docker и Docker Compose
- Доступ к Google Sheets API
- Telegram Bot Token

## Пошаговая установка

### 1. Настройка Google Sheets API

Поместите файл `service_account.json` с учетными данными Google Sheets API в корневую папку проекта:

```
BiaminoFeedbackTG/
├── service_account.json  ← Ваш файл с credentials
├── docker-compose.yml
├── .env.example
└── ...
```

### 2. Настройка переменных окружения

Создайте файл `.env` в корне проекта на основе `.env.example`:

```bash
cp .env.example .env
```

Заполните необходимые параметры в `.env`:

```env
BOT_TOKEN=your_telegram_bot_token
ADMIN_IDS=123456789,987654321
SPREADSHEET_ID=your_google_sheet_id
SERVICE_ACCOUNT_FILE=service_account.json
REDIS_URL=redis://redis:6379/0
```

### 3. Запуск проекта

Запустите проект через Docker Compose:

```bash
docker compose up --build -d
```

Проект будет доступен в фоновом режиме.

### 4. Проверка работы

Проверить логи можно командой:

```bash
docker compose logs -f bot
```

Остановить проект:

```bash
docker compose down
```

## Архитектура хранения данных

Сервис использует **Redis** для хранения состояний FSM (Finite State Machine) Telegram бота.

- **Redis** обеспечивает персистентное хранение состояний пользователей между сессиями
- Состояния включают: процесс авторизации, заполнение отчетов, административные операции
- При перезапуске контейнера все пользовательские сессии сохраняются
- Конфигурация Redis задается через переменную `REDIS_URL` в `.env`

Это позволяет боту корректно восстанавливать диалоги с пользователями после перезапуска сервиса.