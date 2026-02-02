# Документация для модулей database

## Структура проекта
```
database/
├── database.py    # Функции для работы с базой данных
└── models.py      # Модели SQLAlchemy для ORM
```

## models.py - Модели базы данных

### GiveawayStatus (Enum)
Перечисление статусов розыгрыша.

- `ACTIVE` - активный розыгрыш
- `FINISHED` - завершенный розыгрыш
- `CANCELLED` - отмененный розыгрыш

### ChannelSubscriber
Модель подписчиков каналов для сбора статистики.

**Поля:**
- `id` - первичный ключ
- `channel_id` - ID канала в Telegram
- `user_id` - Telegram ID пользователя
- `username` - username пользователя в Telegram
- `first_name` - имя пользователя в Telegram
- `added_at` - дата и время добавления в канал
- `left_at` - дата и время отписки от канала (NULL если все еще подписан)

**Ограничения:**
- Уникальное ограничение по комбинации `channel_id` и `user_id` - один пользователь может быть записан как подписчик канала только один раз

**Таблица:** `channel_subscribers`

### Admin
Модель администраторов бота.

**Поля:**
- `id` - первичный ключ
- `user_id` - Telegram ID пользователя (уникальный)
- `username` - username в Telegram
- `first_name` - имя в Telegram
- `is_main_admin` - флаг главного администратора
- `created_at` - дата создания записи

**Связи:**
- `channels` - список каналов, добавленных админом (обратная связь)
- `created_giveaways` - список розыгрышей, созданных админом (обратная связь)

### Channel
Модель Telegram-каналов для проведения розыгрышей.

**Поля:**
- `id` - первичный ключ
- `channel_id` - Telegram ID канала (уникальный)
- `channel_name` - название канала
- `channel_username` - username канала (@username)
- `added_by` - ID администратора, добавившего канал
- `created_at` - дата добавления

**Связи:**
- `admin` - администратор, добавивший канал
- `giveaways` - список розыгрышей в этом канале (обратная связь)

### Giveaway
Модель розыгрыша.

**Поля:**
- `id` - первичный ключ
- `title` - заголовок розыгрыша
- `description` - описание розыгрыша
- `media_type` - тип медиа (photo, video, animation, document)
- `media_file_id` - file_id медиа в Telegram
- `channel_id` - ID канала для розыгрыша
- `message_id` - ID сообщения с розыгрышем в канале
- `start_time` - время начала
- `end_time` - время окончания
- `status` - статус розыгрыша (ACTIVE, FINISHED, CANCELLED)
- `winner_places` - количество призовых мест
- `created_by` - ID создателя (админа)
- `created_at` - дата создания
- `updated_at` - дата последнего обновления

**Связи:**
- `channel` - канал, в котором проводится розыгрыш
- `creator` - создатель розыгрыша
- `participants` - список участников (обратная связь)
- `winners` - список победителей (обратная связь)

### Participant
Модель участника розыгрыша.

**Поля:**
- `id` - первичный ключ
- `giveaway_id` - ID розыгрыша
- `user_id` - Telegram ID участника
- `username` - username участника
- `first_name` - имя участника
- `joined_at` - дата участия

**Связи:**
- `giveaway` - розыгрыш, в котором участвует пользователь

**Ограничения:**
- Уникальный индекс: один пользователь может участвовать в одном розыгрыше только один раз

### Winner
Модель победителя розыгрыша.

**Поля:**
- `id` - первичный ключ
- `giveaway_id` - ID розыгрыша
- `user_id` - Telegram ID победителя
- `username` - username победителя
- `first_name` - имя победителя
- `place` - место (1, 2, 3...)
- `won_at` - дата выигрыша

**Связи:**
- `giveaway` - розыгрыш, в котором выигран приз

**Ограничения:**
- Уникальный индекс: одно место в одном розыгрыше может быть занято только одним пользователем

## database.py - Функции работы с базой данных

### Инициализация и сессии

- `engine` - асинхронный движок SQLAlchemy
- `async_session` - фабрика асинхронных сессий
- `init_db()` - инициализация БД и создание таблиц
- `get_session()` - генератор сессий для использования в зависимостях FastAPI

### Функции для работы с администраторами

- `is_admin(user_id: int) -> bool` - проверка, является ли пользователь админом
- `add_admin(user_id: int, username: str = None, first_name: str = None) -> bool` - добавление нового админа
- `remove_admin(user_id: int) -> bool` - удаление админа (кроме главного)
- `get_all_admins() -> List[Admin]` - получение всех админов
- `update_admin_profile(user) -> None` - обновление профиля админа по данным Telegram

### Функции для работы с каналами

- `add_channel(channel_id: int, channel_name: str, channel_username: str = None, added_by: int = None) -> bool` - добавление канала
- `add_channel_by_username(channel_username: str, bot, added_by: int = None) -> tuple[bool, str]` - добавление канала по username с проверкой прав бота
- `get_all_channels() -> List[Channel]` - получение всех каналов со связанными админами
- `remove_channel(channel_id: int) -> bool` - удаление канала

### Функции для работы с розыгрышами

- `create_giveaway(title: str, description: str, end_time, channel_id: int, created_by: int, winner_places: int = 1, media_type: str = None, media_file_id: str = None) -> Optional[Giveaway]` - создание нового розыгрыша
- `get_giveaway(giveaway_id: int) -> Optional[Giveaway]` - получение розыгрыша по ID со связями
- `get_active_giveaways() -> List[Giveaway]` - получение активных розыгрышей
- `get_finished_giveaways() -> List[Giveaway]` - получение завершенных розыгрышей
- `get_finished_giveaways_page(page: int, page_size: int) -> List[Giveaway]` - пагинация завершенных розыгрышей
- `count_finished_giveaways() -> int` - подсчет количества завершенных розыгрышей
- `delete_finished_older_than(days: int) -> int` - удаление розыгрышей, завершенных более N дней назад
- `update_giveaway_message_id(giveaway_id: int, message_id: int)` - обновление ID сообщения розыгрыша
- `update_giveaway_fields(giveaway_id: int, **fields) -> Optional[Giveaway]` - обновление произвольных полей розыгрыша
- `finish_giveaway(giveaway_id: int, winners_data: List[dict] = None)` - завершение розыгрыша и добавление победителей
- `delete_giveaway(giveaway_id: int) -> bool` - полное удаление розыгрыша (включая участников и победителей)

### Функции для работы с участниками

- `add_participant(giveaway_id: int, user_id: int, username: str = None, first_name: str = None) -> bool` - добавление участника в розыгрыш
- `get_participants_count(giveaway_id: int) -> int` - получение количества участников
- `get_participants(giveaway_id: int) -> List[Participant]` - получение всех участников розыгрыша

### Функции для работы с подписчиками каналов

- `add_channel_subscriber(channel_id: int, user_id: int, username: str = None, first_name: str = None)` - добавление пользователя как подписчика канала. Если запись уже есть с `left_at`, обновляет её (считает повторную подписку). Возвращает False если пользователь уже подписан или при ошибке.
- `remove_channel_subscriber(channel_id: int, user_id: int) -> bool` - отмечает пользователя как отписавшегося от канала (устанавливает `left_at`). Возвращает True при успехе.
- `get_channel_subscribers_count(channel_id: int, as_of: datetime = None) -> int` - получает количество активных подписчиков канала на указанную дату/время. Если `as_of` не указан — возвращает текущее количество.
- `get_active_subscribers(channel_id: int) -> List[ChannelSubscriber]` - возвращает список всех активных подписчиков канала (у которых `left_at` is NULL).
- `was_user_subscriber(channel_id: int, user_id: int, at_time: datetime) -> bool` - проверяет, был ли пользователь подписчиком канала на определённый момент времени.

### Функции для работы с победителями

- `get_winners(giveaway_id: int) -> List[Winner]` - получение победителей розыгрыша, отсортированных по местам
- `add_winner(giveaway_id: int, user_id: int, place: int, username: str = None, first_name: str = None) -> bool` - добавление победителя

## Использование

Модули используются вместе для асинхронной работы с базой данных SQLite через SQLAlchemy ORM. Основные принципы:

1. Все функции асинхронные и используют `async/await`
2. Для инициализации БД вызывается `init_db()`
3. Для работы с данными используются контекстные менеджеры сессий
4. Модели связаны между собой через relationships для удобного доступа к связанным данным
5. При удалении розыгрыша автоматически удаляются связанные участники и победители
6. При добавлении канала по username выполняется проверка существования канала и прав бота
7. Усовершенствованная модель ChannelSubscriber позволяет собирать детальную статистику по подписчикам каналов, включая отслеживание отписок и историю подписок во времени

Документация создана на основе анализа кода от 2026-02-02.