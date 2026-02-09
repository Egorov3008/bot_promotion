# Pyrogram App Module Documentation

## Overview

Модуль `pyrogram_app` содержит компоненты для работы с Telegram User Bot через Pyrogram API. Этот модуль обеспечивает взаимодействие с каналами, парсинг подписчиков, мониторинг активности и рассылку сообщений.

> **Важно**: Все классы в этом модуле принимают **уже запущенный** экземпляр `Client` из Pyrogram. Инициализация и запуск клиента осуществляется через `PyrogramClient`.

---

## Architecture

```
pyrogram_app/
├── pyro_client.py          # Основной класс-обёртка PyrogramClient
├── parsing_mode.py         # Парсинг каналов и мониторинг (ParsingMode)
├── mailing_mode.py         # Рассылка сообщений (MailingMode)
└── README.md               # Документация модуля
```

### Component Responsibilities

| Компонент | Ответственность |
|-----------|-----------------|
| `PyrogramClient` | Инициализация, запуск/остановка, базовые операции с Client |
| `ParsingMode` | Парсинг каналов, проверка активности, мониторинг реакций |
| `MailingMode` | Массовая рассылка сообщений, обработка ошибок доставки |

---

## Quick Start

```python
from config import config
from pyrogram_app.pyro_client import setup_pyrogram, get_pyrogram_client
from pyrogram_app.parsing_mode import ParsingMode
from pyrogram_app.mailing_mode import MailingMode

# Инициализация и запуск (один раз в main.py)
pyro = setup_pyrogram(config)
await pyro.start()

# Получение запущенного клиента
client = pyro.export()

# Использование режимов
parser = ParsingMode(client)
mailer = MailingMode(client, delay_range=(1.5, 3.0))

# Парсинг канала
subscribers, stats = await parser.parse_full(channel_id=123456789)

# Рассылка сообщений
result = await mailer.send_bulk_messages(
    user_ids=[111, 222, 333],
    text="Привет! Это тестовая рассылка."
)
```

---

## PyrogramClient

### Description

Класс-обёртка над `pyrogram.Client`, обеспечивающий единую точку входа для работы с User Bot.

### Key Features

- Singleton-паттерн через `setup_pyrogram()`
- Безопасный запуск и остановка клиента
- Экспорт внутреннего `Client` для передачи в режимы
- Отслеживание статуса работы (`is_running`)

### Methods

#### `setup_pyrogram(config) -> PyrogramClient`

Factory-функция для создания единственного экземпляра.

```python
from config import config
from pyrogram_app.pyro_client import setup_pyrogram

pyro = setup_pyrogram(config)
```

#### `get_pyrogram_client() -> PyrogramClient`

Получение существующего экземпляра (после инициализации).

```python
from pyrogram_app.pyro_client import get_pyrogram_client

pyro = get_pyrogram_client()
```

#### `start() -> None`

Запуск клиента. Вызывается один раз перед использованием.

```python
await pyro.start()
```

#### `stop() -> None`

Остановка клиента. Вызывается при завершении работы.

```python
await pyro.stop()
```

#### `export() -> Client`

Возвращает внутренний экземпляр `Client` для передачи в `ParsingMode` или `MailingMode`.

```python
client = pyro.export()
parser = ParsingMode(client)
```

#### `send_message(chat_id, text, parse_mode=None) -> bool`

Отправка сообщения.

```python
await pyro.send_message(chat_id=123456, text="Hello!", parse_mode="HTML")
```

#### `get_message_reactions(chat_id, message_id) -> dict`

Получение реакций на сообщение.

```python
reactions = await pyro.get_message_reactions(chat_id=123456, message_id=10)
```

---

## ParsingMode

### Description

Класс для парсинга каналов и мониторинга активности пользователей.

### Data Classes

```python
@dataclass
class ParsingStats:
    total_processed: int       # Всего обработано
    with_username: int          # С username
    without_username: int       # Без username
    bots_count: int            # Боты
    added: int                 # Добавлено новых
    updated: int               # Обновлено
    start_time: datetime       # Время начала
    end_time: datetime         # Время окончания

    def duration_seconds(self) -> float:
        """Возвращает длительность парсинга в секундах"""
```

### Methods

#### `__init__(pyro_client: Client)`

Инициализация с запущенным клиентом.

```python
from pyrogram_app.pyro_client import get_pyrogram_client

pyro = get_pyrogram_client()
parser = ParsingMode(pyro.export())
```

#### `check_admin_rights(channel_id: int) -> Tuple[bool, str]`

Проверка прав администратора в канале.

```python
has_rights, message = await parser.check_admin_rights(channel_id=123456)
print(message)  # ✅ Бот имеет права администратора
```

#### `parse_full(channel_id: int, progress_callback=None) -> Tuple[List[Dict], ParsingStats]`

Полный парсинг всех подписчиков канала.

```python
subscribers, stats = await parser.parse_full(channel_id=123456)

for sub in subscribers:
    print(f"{sub['username']}: {sub['first_name']}")
    
print(f"Время: {stats.duration_seconds()} сек")
```

#### `parse_incremental(channel_id: int, known_users: List[int], batch_size=100) -> Tuple[List[Dict], ParsingStats]`

Инкрементальный парсинг - добавление только новых подписчиков.

```python
# known_users - список уже известных user_id из БД
known = [111, 222, 333]
new_subscribers, stats = await parser.parse_incremental(
    channel_id=123456,
    known_users=known
)
```

#### `get_channel_members_count(channel_id: int) -> int`

Количество участников канала.

```python
count = await parser.get_channel_members_count(channel_id=123456)
print(f"Участников: {count}")
```

#### `get_member_info(channel_id: int, user_id: int) -> Optional[Dict]`

Информация о конкретном участнике.

```python
info = await parser.get_member_info(channel_id=123456, user_id=111)
print(info)
# {'user_id': 111, 'first_name': 'Ivan', 'username': 'ivanov', 'status': 'member', ...}
```

#### `check_user_activity(channel_id: int, user_ids: List[int], check_reactions=True) -> Dict[int, Dict]`

Проверка активности списка пользователей.

```python
report = await parser.check_user_activity(
    channel_id=123456,
    user_ids=[111, 222, 333]
)

for user_id, activity in report.items():
    if activity['in_channel']:
        print(f"{user_id}: активен, статус={activity['status']}")
    else:
        print(f"{user_id}: покинул канал")
```

#### `get_recent_message_reactions(channel_id: int, message_id: int) -> Dict[str, List[int]]`

Реакции на конкретное сообщение.

```python
reactions = await parser.get_recent_message_reactions(
    channel_id=123456,
    message_id=10
)
# {'👍': [111, 222], '🔥': [333]}
```

#### `get_channel_info(channel_id: int) -> Optional[Dict]`

Полная информация о канале.

```python
info = await parser.get_channel_info(channel_id=123456)
print(f"{info['title']} (@{info['username']}) - {info['members_count']} уч.")
```

#### `stop() -> None`

Остановка фоновых задач парсинга.

```python
parser.stop()
```

---

## MailingMode

### Description

Класс для массовой рассылки сообщений пользователям с обработкой ошибок.

### Data Classes

```python
@dataclass
class MailingStats:
    total: int                # Всего получателей
    sent: int                 # Успешно отправлено
    blocked: int              # Заблокировали бота
    failed: int               # Ошибки доставки
    start_time: datetime      # Время начала
    end_time: datetime        # Время окончания
    
    def duration_seconds(self) -> float:
        """Возвращает длительность рассылки в секундах"""
```

### Methods

#### `__init__(pyro_client: Client, delay_range=(1.0, 3.0))`

Инициализация с запущенным клиентом и диапазоном задержек.

```python
from pyrogram_app.pyro_client import get_pyrogram_client

pyro = get_pyrogram_client()
mailer = MailingMode(
    pyro.export(),
    delay_range=(1.5, 3.0)  # Задержка 1.5-3 секунды между сообщениями
)
```

#### `send_message_to_user(user_id: int, text: str, parse_mode=None, disable_web_page_preview=False) -> Tuple[bool, str]`

Отправка сообщения одному пользователю.

```python
success, message = await mailer.send_message_to_user(
    user_id=111,
    text="Привет! 👋",
    parse_mode="HTML"
)
print(message)
```

#### `send_bulk_messages(user_ids: List[int], text: str, parse_mode=None, disable_web_page_preview=False, randomize_order=True, progress_callback=None) -> MailingStats`

Массовая рассылка сообщений списку пользователей.

```python
result = await mailer.send_bulk_messages(
    user_ids=[111, 222, 333, 444, 555],
    text="🎉 Специальное предложение для вас!",
    parse_mode="HTML",
    randomize_order=True
)

print(f"Отправлено: {result.sent}/{result.total}")
print(f"Заблокировано: {result.blocked}")
print(f"Ошибки: {result.failed}")
```

#### `send_personalized_messages(user_messages: List[Dict], delay_range=None, progress_callback=None) -> MailingStats`

Персонализированная рассылка (разные сообщения разным пользователям).

```python
messages = [
    {"user_id": 111, "text": "Привет, Иван!"},
    {"user_id": 222, "text": "Привет, Петр!"},
    {"user_id": 333, "text": "Привет, Алексей!"}
]

result = await mailer.send_personalized_messages(messages)
```

#### `estimate_delivery_time(user_count: int, delay_range=None) -> float`

Оценка времени рассылки.

```python
seconds = mailer.estimate_delivery_time(1000)
print(f"Рассылка 1000 сообщений займёт ~{seconds/60:.1f} минут")
```

#### `stop() -> None`

Остановка фоновых задач рассылки.

```python
mailer.stop()
```

---

## Error Handling

### Common Error Types

| Тип ошибки | Причина | Решение |
|------------|---------|---------|
| `FloodWait` | Слишком много запросов | Подождать указанное время |
| `UserNotFound` | Пользователь удалён | Исключить из списка |
| `BotBlocked` | Пользователь заблокировал бота | Исключить из рассылок |
| `ChatAdminRequired` | Нет прав администратора | Добавить бота в админы |
| `UserDeactivated` | Аккаунт деактивирован | Исключить из базы |

### Example: Safe Mailing

```python
from pyrogram_app.pyro_client import get_pyrogram_client
from pyrogram_app.mailing_mode import MailingMode

pyro = get_pyrogram_client()
mailer = MailingMode(pyro.export())

try:
    result = await mailer.send_bulk_messages(
        user_ids=[111, 222, 333],
        text="Тестовое сообщение"
    )
    
    if result.blocked > 0:
        print(f"Внимание: {result.blocked} пользователей заблокировали бота")
        
except Exception as e:
    print(f"Критическая ошибка: {e}")
finally:
    mailer.stop()
```

---

## Best Practices

### 1. Реиспользование клиента

```python
# ❌ Неправильно: создание нового клиента для каждой операции
for channel_id in channels:
    parser = ParsingMode(await create_new_client())
    await parser.parse_full(channel_id)

# ✅ Правильно: один клиент для всех операций
pyro = setup_pyrogram(config)
await pyro.start()
client = pyro.export()

parser = ParsingMode(client)
for channel_id in channels:
    await parser.parse_full(channel_id)
```

### 2. Остановка клиента

```python
# ❌ Неправильно: забыли остановить
await pyro.start()
# ... работа ...
print("Готово!")

# ✅ Правильно: try/finally
await pyro.start()
try:
    # ... работа ...
    await parser.parse_full(123)
    await mailer.send_bulk_messages([111, 222], "Hello")
finally:
    await pyro.stop()
```

### 3. Rate Limiting

```python
# ✅ Используйте delay_range для рассылки
mailer = MailingMode(
    client,
    delay_range=(2.0, 5.0)  # 2-5 секунд между сообщениями
)
```

---

## Integration with Handlers

### Пример интеграции в handlers/admin_handlers.py

```python
from pyrogram_app.pyro_client import get_pyrogram_client
from pyrogram_app.parsing_mode import ParsingMode
from pyrogram_app.mailing_mode import MailingMode

@router.callback_query(F.data.startswith("start_parsing_"))
async def callback_start_parsing(callback: CallbackQuery, state: FSMContext):
    channel_id = int(callback.data.split("_")[-1])
    
    # Получаем клиент
    pyro = get_pyrogram_client()
    client = pyro.export()
    
    # Создаём парсер
    parser = ParsingMode(client)
    
    # Запускаем парсинг
    asyncio.create_task(_run_parsing(callback.message, state, parser))
```

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.0.0 | 2024 | Initial release |

---

## License

Pyrogram App Module - Part of Giveaway Bot Project