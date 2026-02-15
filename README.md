# Telegram Giveaway Bot

Платформа для проведения розыгрышей в Telegram-каналах. Совмещает **Aiogram 3** (Bot API для взаимодействия с пользователями) и **Pyrogram** (Client API для операций с каналами: парсинг подписчиков, массовая рассылка, отслеживание реакций).

## Возможности

- Создание и управление розыгрышами через интерактивные диалоги
- Автоматическое завершение розыгрышей по расписанию
- Напоминания о розыгрышах (за 3 дня, 1 день, 3 часа)
- Проверка подписки участников на канал
- Персональные сообщения победителям через Pyrogram
- Парсинг подписчиков и мониторинг активности в каналах
- Массовая рассылка сообщений
- Управление администраторами и каналами
- Автоочистка завершённых розыгрышей (15+ дней)

## Требования

- Python 3.10+
- Telegram Bot Token (через [@BotFather](https://t.me/BotFather))
- Telegram API ID и API Hash (через [my.telegram.org](https://my.telegram.org))
- Номер телефона для Pyrogram-сессии

## Установка

```bash
git clone <repo-url>
cd bot_promotion

pip install -r requirements.txt
pip install pyrogram tgcrypto  # устанавливается отдельно
```

## Конфигурация

Создайте файл `.env` в корне проекта:

```env
# Aiogram Bot
BOT_TOKEN=your_bot_token
MAIN_ADMIN_ID=123456789

# Pyrogram Client
API_ID=your_api_id
API_HASH=your_api_hash
PHONE_NUMBER=+79001234567

# Опционально
DATABASE_URL=sqlite:///giveaway_bot.db   # по умолчанию SQLite
TIMEZONE=Europe/Moscow                    # по умолчанию Москва
SESSION_NAME=pyrogram_session             # имя файла сессии
```

## Запуск

```bash
python main.py
```

При первом запуске Pyrogram запросит код авторизации по SMS.

## Архитектура

### Dual Telegram API

- **Aiogram 3** (`main.py`, `handlers/`, `dialogs/`) — Bot API: команды, инлайн-кнопки, FSM-диалоги
- **Pyrogram** (`pyrogram_app/`) — Client API (MTProto): парсинг подписчиков, рассылка, отслеживание реакций

Оба клиента работают параллельно в одном asyncio event loop.

### Структура проекта

```
bot_promotion/
├── main.py                  # Точка входа, запуск обоих клиентов
├── config.py                # Конфигурация (singleton)
├── database/
│   ├── models.py            # SQLAlchemy модели (Admin, Channel, Giveaway, Participant, Winner, ChannelSubscriber)
│   └── database.py          # Все операции с БД, кэширование через aiocache
├── dialogs/                 # Aiogram-dialog интерфейсы
│   ├── __init__.py          # Регистрация всех диалогов
│   ├── admin_main.py        # Главное меню администратора
│   ├── admins.py            # Управление администраторами
│   ├── channels.py          # Управление каналами
│   ├── giveaway_create.py   # Мастер создания розыгрыша
│   ├── giveaway_view.py     # Просмотр розыгрышей
│   ├── giveaway_edit.py     # Редактирование розыгрышей
│   └── mailing.py           # Рассылка сообщений
├── handlers/                # Обработчики команд и событий
│   ├── basic_handlers.py    # /start, /clear
│   └── chat_member_handlers.py  # Отслеживание подписок, реакций, комментариев
├── pyrogram_app/
│   ├── pyro_client.py       # Pyrogram клиент (singleton)
│   ├── parsing_mode.py      # Парсинг подписчиков и мониторинг активности
│   └── mailing_mode.py      # Массовая рассылка с анти-flood защитой
├── states/
│   └── admin_states.py      # FSM состояния (13 StatesGroup)
├── texts/
│   └── messages.py          # Все тексты и кнопки бота (MESSAGES, BUTTONS)
├── utils/
│   ├── datetime_utils.py    # Работа с датами и часовыми поясами
│   ├── keyboards.py         # Инлайн-клавиатуры
│   └── scheduler.py         # APScheduler: завершение розыгрышей, напоминания, очистка
└── docs/                    # Подробная документация по модулям
    ├── DATABASE.md
    ├── DIALOGS.md
    ├── PYROGRAM.md
    └── UTILS.md
```

### Поток обработки запросов

```
Запрос пользователя → AdminMiddleware (проверка доступа) → PyrogramMiddleware (инъекция Pyrogram клиента) → Router/Dialog → Ответ
```

Публичные эндпоинты (`/start`, участие в розыгрыше) обходят проверку администратора.

### Модуль dialogs

Административные интерфейсы реализованы на базе **aiogram-dialog** — декларативный подход с автоматическим управлением стеком состояний, встроенными виджетами и динамическим рендерингом через `getter`. Подробнее: [docs/DIALOGS.md](docs/DIALOGS.md).

### Модуль pyrogram_app

Операции через MTProto, недоступные в Bot API: парсинг подписчиков каналов, отслеживание реакций через raw-обновления, массовая рассылка с анти-flood защитой (случайные задержки, обработка FloodWait, retry). Подробнее: [docs/PYROGRAM.md](docs/PYROGRAM.md).

### Модуль utils

Планировщик задач (APScheduler), утилиты для дат/часовых поясов, генерация инлайн-клавиатур. Подробнее: [docs/UTILS.md](docs/UTILS.md).

### База данных

SQLAlchemy async ORM с поддержкой SQLite (по умолчанию), PostgreSQL и MySQL. Таблицы создаются автоматически при старте через `init_db()`. Кэширование через aiocache. Подробнее: [docs/DATABASE.md](docs/DATABASE.md).

## Тестирование

```bash
pytest           # все тесты
pytest -v        # с подробным выводом
pytest tests/test_database.py  # конкретный файл
```

Тесты используют in-memory SQLite (`sqlite+aiosqlite:///:memory:`) с отдельной БД на каждый тест. Async mode: `auto` (настроен в `pytest.ini`).

## Зависимости

| Пакет | Назначение |
|---|---|
| aiogram 3.25 | Bot API фреймворк |
| aiogram-dialog 2.4 | Многошаговые диалоги |
| pyrogram + tgcrypto | Client API (MTProto) |
| sqlalchemy 2.0 + aiosqlite | Async ORM + SQLite драйвер |
| apscheduler 3.10 | Планировщик задач |
| aiocache 0.12 | Кэширование запросов к БД |
| python-dotenv | Загрузка .env |
| pytz | Часовые пояса |
