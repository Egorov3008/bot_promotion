# Модуль database

Модуль `database` реализует слой хранения данных на основе **SQLAlchemy Async ORM**. По умолчанию используется SQLite (через `aiosqlite`), но поддерживаются PostgreSQL и MySQL. Таблицы создаются автоматически при старте через `init_db()` — миграции не используются.

## Структура модуля

- `models.py` — ORM-модели и перечисления (Enum)
- `database.py` — все асинхронные функции для работы с БД

## Модели (`models.py`)

### Admin

Администраторы бота.

| Поле | Тип | Описание |
| --- | --- | --- |
| `id` | Integer, PK | Автоинкремент |
| `user_id` | BigInteger, unique | Telegram User ID |
| `username` | String(255) | Username в Telegram |
| `first_name` | String(255) | Имя |
| `full_name` | String(255) | Полное имя |
| `is_main_admin` | Boolean | Главный администратор (неудаляемый) |
| `created_at` | DateTime | Дата добавления |

### Channel

Telegram-каналы, подключённые к боту.

| Поле | Тип | Описание |
| --- | --- | --- |
| `id` | Integer, PK | Автоинкремент |
| `channel_id` | BigInteger, unique | Telegram Channel ID |
| `channel_name` | String(255) | Название канала |
| `channel_username` | String(255) | @username канала |
| `added_by` | BigInteger, FK → admins.user_id | Кто добавил |
| `discussion_group_id` | Integer | ID привязанной группы обсуждений |
| `created_at` | DateTime | Дата добавления |

**Связи:** `admin` (Admin), `giveaways` (Giveaway[]), `mailings` (Mailing[])

### ChannelSubscriber

Подписчики каналов (отслеживаются пока бот является админом канала).

| Поле | Тип | Описание |
| --- | --- | --- |
| `id` | Integer, PK | Автоинкремент |
| `channel_id` | BigInteger | ID канала |
| `user_id` | BigInteger | Telegram ID пользователя |
| `username` | String(255) | Username |
| `full_name` | String(255) | Полное имя |
| `first_name` | String(255) | Имя |
| `added_at` | DateTime | Время добавления/подписки |
| `left_at` | DateTime | Время отписки (NULL = активен) |
| `last_activity_at` | DateTime | Дата последней активности (комментарий, реакция) |

**Ограничение:** `UniqueConstraint('channel_id', 'user_id')` — один пользователь, одна запись на канал.

### Giveaway

Розыгрыши.

| Поле | Тип | Описание |
| --- | --- | --- |
| `id` | Integer, PK | Автоинкремент |
| `title` | String(255) | Заголовок |
| `description` | Text | Описание |
| `message_winner` | Text | Персональное сообщение победителям |
| `media_type` | String(50) | Тип медиа: photo, video, animation, document |
| `media_file_id` | String(255) | Telegram file_id |
| `channel_id` | BigInteger, FK → channels.channel_id | Канал публикации |
| `message_id` | BigInteger | ID сообщения в канале |
| `start_time` | DateTime | Время создания |
| `end_time` | DateTime | Время окончания |
| `status` | String(20) | Статус: active, finished, cancelled |
| `winner_places` | Integer | Количество призовых мест |
| `created_by` | BigInteger, FK → admins.user_id | Создатель |
| `created_at` | DateTime | Дата создания |
| `updated_at` | DateTime | Дата обновления (auto) |

**Связи:** `channel` (Channel), `creator` (Admin), `participants` (Participant[]), `winners` (Winner[])

**Свойства:** `participants_count` — количество участников.

### Participant

Участники розыгрышей.

| Поле | Тип | Описание |
| --- | --- | --- |
| `id` | Integer, PK | Автоинкремент |
| `giveaway_id` | Integer, FK → giveaways.id | Розыгрыш |
| `user_id` | BigInteger | Telegram ID |
| `username` | String(255) | Username |
| `first_name` | String(255) | Имя |
| `full_name` | String(255) | Полное имя |
| `joined_at` | DateTime | Время участия |

### Winner

Победители розыгрышей.

| Поле | Тип | Описание |
| --- | --- | --- |
| `id` | Integer, PK | Автоинкремент |
| `giveaway_id` | Integer, FK → giveaways.id | Розыгрыш |
| `user_id` | BigInteger | Telegram ID |
| `username` | String(255) | Username |
| `first_name` | String(255) | Имя |
| `full_name` | String(255) | Полное имя |
| `place` | Integer | Место (1, 2, 3...) |
| `won_at` | DateTime | Время победы |

### Mailing

Массовые рассылки.

| Поле | Тип | Описание |
| --- | --- | --- |
| `id` | Integer, PK | Автоинкремент |
| `channel_id` | BigInteger, FK → channels.channel_id | Канал-источник аудитории |
| `admin_id` | BigInteger, FK → admins.user_id | Кто запустил |
| `audience_type` | String(50) | Тип аудитории: "active_30d" / "all" |
| `message_text` | Text | Текст рассылки |
| `total_users` | Integer | Всего пользователей |
| `sent_count` | Integer | Успешно отправлено |
| `failed_count` | Integer | Неудачные попытки |
| `blocked_count` | Integer | Заблокировали бота |
| `status` | String(20) | Статус: pending, sending, done, cancelled |
| `created_at` | DateTime | Дата создания |
| `finished_at` | DateTime | Дата завершения/отмены |

### Перечисления

- **`GiveawayStatus`** — `ACTIVE`, `FINISHED`, `CANCELLED`
- **`MailingStatus`** — `PENDING`, `SENDING`, `DONE`, `CANCELLED`

## Функции (`database.py`)

### Инициализация

- `init_db()` — создание таблиц и добавление главного админа
- `get_session()` — получение `AsyncSession`
- `add_main_admin()` — создание главного админа из `config.MAIN_ADMIN_ID`

### Администраторы

- `is_admin(user_id) → bool` — проверка статуса администратора
- `add_admin(user_id, username, first_name, full_name) → bool` — добавление админа
- `remove_admin(user_id) → bool` — удаление (кроме главного)
- `get_all_admins() → List[Admin]` — список всех админов
- `update_admin_profile(user)` — обновление профиля по данным Telegram

### Каналы

- `add_channel(channel_id, channel_name, ...) → bool` — добавление канала
- `add_channel_by_username(username, bot, added_by) → (bool, str)` — добавление по username с проверкой прав бота и автоопределением группы обсуждений
- `get_all_channels() → List[Channel]` — все каналы
- `get_channel(channel_id) → Channel` — канал по ID
- `remove_channel(channel_id) → bool` — удаление канала
- `get_channel_for_discussion_group(discussion_group_id) → Channel` — поиск канала по ID группы обсуждений

### Розыгрыши

- `create_giveaway(title, description, message_winner, end_time, channel_id, ...) → Giveaway` — создание розыгрыша
- `get_giveaway(giveaway_id) → Giveaway` — получение с загрузкой связей (channel, participants)
- `get_active_giveaways() → List[Giveaway]` — активные розыгрыши
- `get_finished_giveaways() → List[Giveaway]` — завершённые розыгрыши
- `get_finished_giveaways_page(page, page_size) → List[Giveaway]` — пагинация завершённых
- `count_finished_giveaways() → int` — количество завершённых
- `update_giveaway_message_id(giveaway_id, message_id)` — обновление ID сообщения в канале
- `update_giveaway_fields(giveaway_id, **fields) → Giveaway` — обновление произвольных полей (title, description, end_time, message_winner и др.)
- `finish_giveaway(giveaway_id, winners_data)` — завершение с записью победителей
- `delete_giveaway(giveaway_id) → bool` — каскадное удаление (участники → победители → розыгрыш)
- `delete_finished_older_than(days) → int` — очистка старых завершённых розыгрышей

### Участники

- `add_participant(giveaway_id, user_id, ...) → bool` — добавление участника (с проверкой дубликатов)
- `get_participants(giveaway_id) → List[Participant]` — список участников
- `get_participants_count(giveaway_id) → int` — количество участников

### Победители

- `add_winner(giveaway_id, user_id, place, ...) → bool` — добавление победителя
- `get_winners(giveaway_id) → List[Winner]` — список победителей (отсортированы по месту)

### Подписчики каналов

- `add_channel_subscriber(channel_id, user_id, ...) → bool` — добавление подписчика (обработка повторной подписки)
- `remove_channel_subscriber(channel_id, user_id) → bool` — отметка отписки (устанавливает `left_at`)
- `update_last_activity(channel_id, user_id, ...)` — обновление даты активности; если подписчика нет — создаёт запись
- `get_active_subscribers(channel_id, days) → List[ChannelSubscriber]` — подписчики, активные за последние N дней
- `get_all_active_subscribers(channel_id) → List[ChannelSubscriber]` — все активные подписчики
- `get_channel_subscribers_count(channel_id, as_of) → int` — количество активных подписчиков (опционально на конкретную дату)
- `was_user_subscriber(channel_id, user_id, at_time) → bool` — был ли подписчиком на момент времени
- `get_channel_subscribers_stats(channel_id) → Dict` — статистика: total, active, with_username, without_username
- `bulk_add_channel_subscribers(channel_id, subscribers) → (added, updated)` — массовое добавление (batch по 100)
- `update_existing_subscribers(channel_id, subscribers) → int` — обновление данных существующих подписчиков
- `clear_channel_subscribers(channel_id) → int` — полная очистка подписчиков канала

### Массовая рассылка

- `create_mailing(channel_id, admin_id, audience_type, message_text, total_users) → Mailing` — создание записи о рассылке
- `update_mailing_stats(mailing_id, sent, failed, blocked, status)` — обновление статистики и статуса
- `get_mailing(mailing_id) → Mailing` — получение рассылки по ID
- `get_mailings_by_channel(channel_id) → List[Mailing]` — все рассылки канала (новые первыми)
- `get_active_mailing(channel_id) → Mailing` — активная рассылка канала (статус "sending")

## Конфигурация подключения

```python
# config.py
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///giveaway_bot.db")
```

Движок автоматически преобразует `sqlite://` в `sqlite+aiosqlite://` для асинхронной работы. Для PostgreSQL: `postgresql+asyncpg://...`, для MySQL: `mysql+aiomysql://...`.

## Зависимости

- `sqlalchemy` — ORM и построитель запросов
- `aiosqlite` — асинхронный SQLite драйвер
- `config` — переменные окружения (DATABASE_URL, MAIN_ADMIN_ID)

Документация создана на основе анализа кода от 2026-02-15.
