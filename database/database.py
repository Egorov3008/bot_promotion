import logging
from datetime import datetime, timedelta, timezone
from typing import Optional, List, Dict, Tuple, Dict, Tuple, Dict, Tuple

from sqlalchemy import select, delete, update, func, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import selectinload

from config import config
from database.models import Base, Admin, Channel, Giveaway, Participant, Winner, GiveawayStatus, ChannelSubscriber
from database.cache import cached_with_ttl

# Создаем асинхронный движок БД
engine = create_async_engine(
    config.DATABASE_URL.replace("sqlite://", "sqlite+aiosqlite://"),
    echo=False  # Установите True для отладки SQL запросов
)

# Создаем фабрику сессий
async_session = async_sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)


async def init_db():
    """Инициализация базы данных - создание таблиц"""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        logging.info("База данных инициализирована")

    # Добавляем главного админа, если его нет
    await add_main_admin()


async def get_session() -> AsyncSession:
    """Получение сессии для работы с БД"""
    async with async_session() as session:
        yield session


async def add_main_admin():
    """Добавляем главного администратора в БД"""
    async with async_session() as session:
        # Проверяем, есть ли уже главный админ
        result = await session.execute(
            select(Admin).where(Admin.user_id == config.MAIN_ADMIN_ID)
        )
        admin = result.scalar_one_or_none()

        if not admin:
            # Создаем главного админа
            main_admin = Admin(
                user_id=config.MAIN_ADMIN_ID,
                username="main_admin",
                first_name="Главный администратор",
                full_name="Главный администратор",
                is_main_admin=True
            )
            session.add(main_admin)
            await session.commit()
            logging.info(f"Главный администратор добавлен: {config.MAIN_ADMIN_ID}")


# Функции для работы с администраторами
async def is_admin(user_id: int) -> bool:
    """Проверка, является ли пользователь администратором"""
    async with async_session() as session:
        result = await session.execute(
            select(Admin).where(Admin.user_id == user_id)
        )
        return result.scalar_one_or_none() is not None


async def add_admin(user_id: int, username: str = None, first_name: str = None, full_name: str = None) -> bool:
    """Добавление нового администратора"""
    async with async_session() as session:
        try:
            admin = Admin(
                user_id=user_id,
                username=username,
                first_name=first_name,
                full_name=full_name,
                is_main_admin=False
            )
            session.add(admin)
            await session.commit()
            return True
        except IntegrityError:
            await session.rollback()
            return False


async def remove_admin(user_id: int) -> bool:
    """Удаление администратора (кроме главного)"""
    async with async_session() as session:
        result = await session.execute(
            select(Admin).where(
                Admin.user_id == user_id,
                Admin.is_main_admin == False  # Главного админа удалить нельзя
            )
        )
        admin = result.scalar_one_or_none()

        if admin:
            await session.delete(admin)
            await session.commit()
            return True
        return False


async def get_all_admins() -> List[Admin]:
    """Получение списка всех администраторов"""
    async with async_session() as session:
        result = await session.execute(select(Admin))
        return result.scalars().all()


async def update_admin_profile(user) -> None:
    """Обновляет username/first_name/full_name администратора по данным Telegram пользователя."""
    async with async_session() as session:
        result = await session.execute(select(Admin).where(Admin.user_id == user.id))
        admin = result.scalar_one_or_none()
        if not admin:
            return
        changed = False
        if admin.username != user.username:
            admin.username = user.username
            changed = True
        if admin.first_name != user.first_name:
            admin.first_name = user.first_name
            changed = True
        # Формируем полное имя из first_name и last_name, если есть
        full_name = user.full_name or (user.first_name + (" " + user.last_name if user.last_name else ""))
        if admin.full_name != full_name:
            admin.full_name = full_name
            changed = True
        if changed:
            await session.commit()


# Функции для работы с каналами
async def add_channel(channel_id: int, channel_name: str,
                      channel_username: str = None, added_by: int = None,
                      discussion_group_id: int = None) -> bool:
    """Добавление канала"""
    async with async_session() as session:
        try:
            channel = Channel( 
                channel_id=channel_id,
                channel_name=channel_name,
                channel_username=channel_username,
                added_by=added_by,
                discussion_group_id=discussion_group_id,
            )
            session.add(channel)
            await session.commit()
            return True
        except IntegrityError:
            await session.rollback()
            return False


async def add_channel_by_username(channel_username: str, bot, added_by: int = None) -> tuple[bool, str]:
    """Добавление канала по username/ссылке + автоматическое получение discussion group"""
    try:
        clean_username = channel_username.replace('@', '').replace('https://t.me/', '').replace('http://t.me/', '')

        # Получаем информацию о канале
        try:
            chat = await bot.get_chat(f"@{clean_username}")
        except Exception as e:
            return False, f"❌ Канал не найден: {str(e)}"

        if chat.type != "channel":
            return False, "❌ Это не канал!"

        # Проверяем права бота
        try:
            bot_member = await bot.get_chat_member(chat.id, bot.id)
            if bot_member.status not in ["administrator", "creator"]:
                return False, "❌ Бот не является администратором этого канала!"
        except Exception:
            return False, "❌ Нет доступа к каналу! Добавьте бота как администратора."

        # ←←← ОПРЕДЕЛЯЕМ ГРУППУ ОБСУЖДЕНИЯ ←←←
        discussion_group_id = chat.linked_chat_id  # Может быть None

        # Добавляем или обновляем канал
        success = await add_channel(
            channel_id=chat.id,
            channel_name=chat.title,
            channel_username=clean_username,
            added_by=added_by,
            discussion_group_id=discussion_group_id  # ← автоматически!
        )

        if success:
            status = f"✅ Канал '{chat.title}' добавлен!"
            if discussion_group_id:
                status += f"\n🔗 Привязана группа обсуждений: {discussion_group_id}"
            else:
                status += "\nℹ️ У канала нет группы обсуждений."
            return True, status
        else:
            return False, "⚠️ Канал уже добавлен (обновлены данные)."

    except Exception as e:
        return False, f"❌ Ошибка при добавлении канала: {str(e)}"


@cached_with_ttl(ttl=300)
async def get_all_channels() -> List[Channel]:
    """Получение списка всех каналов"""
    async with async_session() as session:
        result = await session.execute(
            select(Channel).options(selectinload(Channel.admin))
        )
        return result.scalars().all()


async def remove_channel(channel_id: int) -> bool:
    """Удаление канала"""
    async with async_session() as session:
        result = await session.execute(
            select(Channel).where(Channel.channel_id == channel_id)
        )
        channel = result.scalar_one_or_none()

        if channel:
            await session.delete(channel)
            await session.commit()
            return True
        return False


# Функции для работы с розыгрышами
async def create_giveaway(title: str, description: str, message_winner: str, end_time,
                          channel_id: int, created_by: int, winner_places: int = 1,
                          media_type: str = None, media_file_id: str = None) -> Optional[Giveaway]:
    """Создание нового розыгрыша"""
    async with async_session() as session:
        giveaway = Giveaway(
            title=title,
            description=description,
            message_winner=message_winner,
            end_time=end_time,
            channel_id=channel_id,
            created_by=created_by,
            winner_places=winner_places,
            media_type=media_type,
            media_file_id=media_file_id
        )
        session.add(giveaway)
        await session.commit()
        await session.refresh(giveaway)
        return giveaway


@cached_with_ttl(ttl=300)
async def get_giveaway(giveaway_id: int) -> Optional[Giveaway]:
    """Получение розыгрыша по ID"""
    async with async_session() as session:
        result = await session.execute(
            select(Giveaway)
            .options(selectinload(Giveaway.channel), selectinload(Giveaway.participants))
            .where(Giveaway.id == giveaway_id)
        )
        return result.scalar_one_or_none()


@cached_with_ttl(ttl=60)
async def get_active_giveaways() -> List[Giveaway]:
    """Получение активных розыгрышей"""
    async with async_session() as session:
        result = await session.execute(
            select(Giveaway)
            .options(
                selectinload(Giveaway.channel),
                selectinload(Giveaway.participants)
            )
            .where(Giveaway.status == GiveawayStatus.ACTIVE.value)
        )
        return result.scalars().all()


async def get_finished_giveaways() -> List[Giveaway]:
    """Получение завершенных розыгрышей"""
    async with async_session() as session:
        result = await session.execute(
            select(Giveaway)
            .options(
                selectinload(Giveaway.channel),
                selectinload(Giveaway.participants)
            )
            .where(Giveaway.status == GiveawayStatus.FINISHED.value)
        )
        return result.scalars().all()


async def get_finished_giveaways_page(page: int, page_size: int) -> List[Giveaway]:
    """Получение страницы завершенных розыгрышей (пагинация)."""
    if page < 1:
        page = 1
    offset = (page - 1) * page_size
    async with async_session() as session:
        result = await session.execute(
            select(Giveaway)
            .options(
                selectinload(Giveaway.channel),
                selectinload(Giveaway.participants)
            )
            .where(Giveaway.status == GiveawayStatus.FINISHED.value)
            .order_by(Giveaway.end_time.desc())
            .offset(offset)
            .limit(page_size)
        )
        return result.scalars().all()


async def count_finished_giveaways() -> int:
    """Количество завершенных розыгрышей."""
    async with async_session() as session:
        result = await session.execute(
            select(func.count(Giveaway.id)).where(Giveaway.status == GiveawayStatus.FINISHED.value)
        )
        return int(result.scalar() or 0)


async def delete_finished_older_than(days: int) -> int:
    """Удаляет из базы розыгрыши, завершенные более чем days дней назад. Возвращает кол-во удаленных розыгрышей.
    Удаляются также их участники и победители."""
    threshold = datetime.now(timezone.utc) - timedelta(days=days)
    async with async_session() as session:
        # Найдем id таких розыгрышей
        result = await session.execute(
            select(Giveaway.id).where(
                Giveaway.status == GiveawayStatus.FINISHED.value,
                Giveaway.end_time < threshold
            )
        )
        ids = [gid for (gid,) in result.all()]
        if not ids:
            return 0
        # Удаляем участников и победителей для этих розыгрышей
        await session.execute(delete(Participant).where(Participant.giveaway_id.in_(ids)))
        await session.execute(delete(Winner).where(Winner.giveaway_id.in_(ids)))
        # Удаляем сами розыгрыши
        await session.execute(delete(Giveaway).where(Giveaway.id.in_(ids)))
        await session.commit()
        return len(ids)


async def update_giveaway_message_id(giveaway_id: int, message_id: int):
    """Обновление ID сообщения розыгрыша в канале"""
    async with async_session() as session:
        await session.execute(
            update(Giveaway)
            .where(Giveaway.id == giveaway_id)
            .values(message_id=message_id)
        )
        await session.commit()


async def update_giveaway_fields(giveaway_id: int, **fields) -> Optional[Giveaway]:
    """Обновляет произвольные поля розыгрыша и возвращает обновленный объект."""
    if not fields:
        return await get_giveaway(giveaway_id)
    async with async_session() as session:
        await session.execute(
            update(Giveaway)
            .where(Giveaway.id == giveaway_id)
            .values(**fields)
        )
        await session.commit()
        # Вернем обновленный объект с нужными связями
        result = await session.execute(
            select(Giveaway)
            .options(selectinload(Giveaway.channel), selectinload(Giveaway.participants))
            .where(Giveaway.id == giveaway_id)
        )
        return result.scalar_one_or_none()


async def finish_giveaway(giveaway_id: int, winners_data: List[dict] = None):
    """Завершение розыгрыша с несколькими победителями"""
    async with async_session() as session:
        # Обновляем статус розыгрыша
        await session.execute(
            update(Giveaway)
            .where(Giveaway.id == giveaway_id)
            .values(status=GiveawayStatus.FINISHED.value)
        )

        # Добавляем победителей
        if winners_data:
            for winner_data in winners_data:
                winner = Winner(
                    giveaway_id=giveaway_id,
                    user_id=winner_data["user_id"],
                    username=winner_data.get("username"),
                    first_name=winner_data.get("first_name"),
                    place=winner_data["place"],
                    full_name=winner_data.get("full_name")
                )
                session.add(winner)

        await session.commit()


async def delete_giveaway(giveaway_id: int) -> bool:
    """Удаление розыгрыша"""
    async with async_session() as session:
        # Сначала удаляем победителей
        await session.execute(
            delete(Winner).where(Winner.giveaway_id == giveaway_id)
        )
        # Затем удаляем участников
        await session.execute(
            delete(Participant).where(Participant.giveaway_id == giveaway_id)
        )
        # Затем удаляем розыгрыш
        result = await session.execute(
            select(Giveaway).where(Giveaway.id == giveaway_id)
        )
        giveaway = result.scalar_one_or_none()

        if giveaway:
            await session.delete(giveaway)
            await session.commit()
            return True
        await session.commit()
        return False


# Функции для работы с участниками
async def add_participant(giveaway_id: int, user_id: int,
                          username: str = None, first_name: str = None, full_name: str = None) -> bool:
    """Добавление участника в розыгрыш"""
    async with async_session() as session:
        try:
            # Проверяем, не участвует ли уже пользователь
            result = await session.execute(
                select(Participant).where(
                    Participant.giveaway_id == giveaway_id,
                    Participant.user_id == user_id
                )
            )
            existing = result.scalar_one_or_none()

            if existing:
                return False  # Уже участвует

            participant = Participant(
                giveaway_id=giveaway_id,
                user_id=user_id,
                username=username,
                first_name=first_name,
                full_name=full_name
            )
            session.add(participant)
            await session.commit()
            return True
        except IntegrityError:
            await session.rollback()
            return False


@cached_with_ttl(ttl=20)
async def get_participants_count(giveaway_id: int) -> int:
    """Получение количества участников розыгрыша"""
    async with async_session() as session:
        result = await session.execute(
            select(func.count(Participant.id)).where(Participant.giveaway_id == giveaway_id)
        )
        return result.scalar()


async def get_participants(giveaway_id: int) -> List[Participant]:
    """Получение списка участников розыгрыша"""
    async with async_session() as session:
        result = await session.execute(
            select(Participant).where(Participant.giveaway_id == giveaway_id)
        )
        return result.scalars().all()


# Функции для работы с победителями
@cached_with_ttl(ttl=600)
async def get_winners(giveaway_id: int) -> List[Winner]:
    """Получение списка победителей розыгрыша"""
    async with async_session() as session:
        result = await session.execute(
            select(Winner)
            .where(Winner.giveaway_id == giveaway_id)
            .order_by(Winner.place)
        )
        return result.scalars().all()


async def add_winner(giveaway_id: int, user_id: int, place: int,
                     username: str = None, first_name: str = None, full_name: str = None) -> bool:
    """Добавление победителя"""
    async with async_session() as session:
        try:
            winner = Winner(
                giveaway_id=giveaway_id,
                user_id=user_id,
                username=username,
                first_name=first_name,
                full_name=full_name,
                place=place
            )
            session.add(winner)
            await session.commit()
            return True
        except IntegrityError:
            await session.rollback()
            return False


async def add_channel_subscriber(channel_id: int, user_id: int, username: str = None, first_name: str = None,
                                 full_name: str = None):
    """
    Добавляет пользователя как подписчика канала.
    Если запись уже есть, но с left_at — обновляет её (считаем повторную подписку).
    """
    async with async_session() as session:
        try:
            # Проверяем, существует ли уже запись
            result = await session.execute(
                select(ChannelSubscriber).where(
                    ChannelSubscriber.channel_id == channel_id,
                    ChannelSubscriber.user_id == user_id
                )
            )
            subscriber = result.scalar_one_or_none()

            if subscriber:
                # Если пользователь уже есть, но отписался — обновляем как повторную подписку
                if subscriber.left_at is not None:
                    subscriber.left_at = None
                    subscriber.username = username
                    subscriber.first_name = first_name
                    subscriber.full_name = full_name
                    await session.commit()
                    return True
                else:
                    # Уже состоит — ничего не делаем
                    return False
            else:
                # Новый подписчик
                subscriber = ChannelSubscriber(
                    channel_id=channel_id,
                    user_id=user_id,
                    username=username,
                    first_name=first_name,
                    full_name=full_name
                )
                session.add(subscriber)
                await session.commit()
                return True
        except Exception as e:
            await session.rollback()
            print(f"Ошибка при добавлении подписчика: {e}")
            return False


async def update_last_activity(channel_id: int, user_id: int, username: str = None, first_name: str = None,
                               full_name: str = None):
    async with async_session() as session:
        stmt = select(ChannelSubscriber).where(
            ChannelSubscriber.channel_id == channel_id,
            ChannelSubscriber.user_id == user_id,
            ChannelSubscriber.left_at.is_(None)
        )
        result = await session.execute(stmt)
        sub = result.scalar_one_or_none()
        if sub:
            sub.last_activity_at = datetime.now()
            await session.commit()
            logging.info("Пользователь %s активен в канале %s", user_id, channel_id)
            return

        await add_channel_subscriber(
            channel_id=channel_id,
            user_id=user_id,
            username=username,
            first_name=first_name,
            full_name=full_name,
        )
        logging.info("Добавлен новый подписчик %s в канале %s", user_id, channel_id)


async def get_active_subscribers(channel_id: int, days: int = 30) -> List[ChannelSubscriber]:
    """
    Возвращает пользователей, которые были активны за последние N дней.
    Активность — участие в розыгрыше или комментарий.
    """
    cutoff = datetime.utcnow() - timedelta(days=days)
    async with get_session() as session:
        stmt = select(ChannelSubscriber).where(
            ChannelSubscriber.channel_id == channel_id,
            ChannelSubscriber.left_at.is_(None),
            ChannelSubscriber.last_activity_at >= cutoff
        )
        result = await session.execute(stmt)
        return result.scalars().all()


async def remove_channel_subscriber(channel_id: int, user_id: int) -> bool:
    """
    Отмечает пользователя как отписавшегося от канала (устанавливает left_at).
    """
    async with async_session() as session:
        try:
            result = await session.execute(
                select(ChannelSubscriber).where(
                    ChannelSubscriber.channel_id == channel_id,
                    ChannelSubscriber.user_id == user_id,
                    ChannelSubscriber.left_at.is_(None)  # Только активные
                )
            )
            subscriber = result.scalar_one_or_none()

            if subscriber:
                subscriber.left_at = func.now()
                await session.commit()
                return True
            return False
        except Exception as e:
            await session.rollback()
            print(f"Ошибка при удалении подписчика: {e}")
            return False


async def get_channel_subscribers_count(channel_id: int, as_of: datetime = None) -> int:
    """
    Получает количество *активных* подписчиков канала на указанную дату/время.
    Если as_of не указан — возвращает текущее количество.
    """
    async with async_session() as session:
        query = select(func.count(ChannelSubscriber.id)).where(
            ChannelSubscriber.channel_id == channel_id,
            ChannelSubscriber.added_at <= (as_of or func.now())
        )
        if as_of:
            query = query.where(
                or_(
                    ChannelSubscriber.left_at.is_(None),
                    ChannelSubscriber.left_at > as_of
                )
            )
        else:
            query = query.where(ChannelSubscriber.left_at.is_(None))

        result = await session.execute(query)
        return result.scalar_one()


async def get_active_subscribers(channel_id: int) -> List[ChannelSubscriber]:
    """
    Возвращает список всех активных подписчиков канала.
    """
    async with async_session() as session:
        result = await session.execute(
            select(ChannelSubscriber).where(
                ChannelSubscriber.channel_id == channel_id,
                ChannelSubscriber.left_at.is_(None)
            )
        )
        return result.scalars().all()


async def was_user_subscriber(channel_id: int, user_id: int, at_time: datetime) -> bool:
    """
    Проверяет, был ли пользователь подписчиком канала на определённый момент времени.
    """
    async with async_session() as session:
        result = await session.execute(
            select(ChannelSubscriber).where(
                ChannelSubscriber.channel_id == channel_id,
                ChannelSubscriber.user_id == user_id,
                ChannelSubscriber.added_at <= at_time
            )
        )
        subscriber = result.scalar_one_or_none()

        if not subscriber:
            return False

        # Если left_at позже времени проверки — значит, всё ещё был подписан
        if subscriber.left_at is None:
            return True
        return subscriber.left_at > at_time


@cached_with_ttl(ttl=600)
async def get_channel(channel_id: int) -> Optional[Channel]:
    async with async_session() as session:
        result = await session.execute(
            select(Channel)
            .options(selectinload(Channel.admin))  # ← Загружаем админа!
            .where(Channel.channel_id == channel_id)
        )
        return result.scalar_one_or_none()

async def get_channel_for_discussion_group(discussion_group_id: int) -> Optional[Channel]:
    """Получает основой канал для по discussion_group_id"""
    async with async_session() as session:
        result = await session.execute(
            select(Channel).
            where(Channel.discussion_group_id == discussion_group_id)
        )
        return result.scalar_one_or_none()


# ==================== ФУНКЦИИ ДЛЯ ПАРСИНГА ПОДПИСЧИКОВ ====================

async def bulk_add_channel_subscribers(channel_id: int, subscribers: List[Dict]) -> Tuple[int, int]:
    """
    Массовое добавление подписчиков канала с оптимизированной batch-вставкой.
    Обновляет существующие записи (вернувшихся пользователей).

    Args:
        channel_id: ID канала
        subscribers: Список словарей с данными подписчиков
                    [{"user_id": int, "username": str, "first_name": str, "last_name": str}, ...]

    Returns:
        Tuple[int, int]: (количество добавленных, количество обновленных)
    """
    if not subscribers:
        return 0, 0

    added_count = 0
    updated_count = 0
    batch_size = 100  # Оптимизированный размер batch для SQLite

    async with async_session() as session:
        try:
            for i in range(0, len(subscribers), batch_size):
                batch = subscribers[i:i + batch_size]

                for sub_data in batch:
                    user_id = sub_data.get("user_id")
                    if not user_id:
                        continue

                    # Проверяем, существует ли запись
                    result = await session.execute(
                        select(ChannelSubscriber).where(
                            ChannelSubscriber.channel_id == channel_id,
                            ChannelSubscriber.user_id == user_id
                        )
                    )
                    existing = result.scalar_one_or_none()

                    if existing:
                        # Пользователь уже есть в базе
                        if existing.left_at is not None:
                            # Пользователь отписался - обновляем как вернувшегося
                            existing.left_at = None
                            existing.username = sub_data.get("username")
                            existing.first_name = sub_data.get("first_name")
                            existing.full_name = sub_data.get("full_name")
                            existing.added_at = datetime.now()
                            updated_count += 1
                        # Если уже активен - ничего не делаем (не считаем как updated)
                    else:
                        # Новый подписчик
                        subscriber = ChannelSubscriber(
                            channel_id=channel_id,
                            user_id=user_id,
                            username=sub_data.get("username"),
                            first_name=sub_data.get("first_name"),
                            full_name=sub_data.get("full_name")
                        )
                        session.add(subscriber)
                        added_count += 1

            await session.commit()
            logging.info(f"Batch insert completed for channel {channel_id}: added={added_count}, updated={updated_count}")

        except Exception as e:
            await session.rollback()
            logging.error(f"Error in bulk_add_channel_subscribers for channel {channel_id}: {e}")
            raise

    return added_count, updated_count


@cached_with_ttl(ttl=300)
async def get_channel_subscribers_stats(channel_id: int) -> Dict[str, int]:
    """
    Получение статистики по подписчикам канала.

    Returns:
        Dict с ключами:
        - total: общее количество записей (включая отписавшихся)
        - active: количество активных подписчиков
        - with_username: количество с username
        - without_username: количество без username (только активные)
    """
    async with async_session() as session:
        # Общее количество записей
        total_result = await session.execute(
            select(func.count(ChannelSubscriber.id)).where(
                ChannelSubscriber.channel_id == channel_id
            )
        )
        total = total_result.scalar() or 0

        # Активные подписчики (не отписавшиеся)
        active_result = await session.execute(
            select(func.count(ChannelSubscriber.id)).where(
                ChannelSubscriber.channel_id == channel_id,
                ChannelSubscriber.left_at.is_(None)
            )
        )
        active = active_result.scalar() or 0

        # Активные с username
        with_username_result = await session.execute(
            select(func.count(ChannelSubscriber.id)).where(
                ChannelSubscriber.channel_id == channel_id,
                ChannelSubscriber.left_at.is_(None),
                ChannelSubscriber.username.isnot(None)
            )
        )
        with_username = with_username_result.scalar() or 0

        # Активные без username
        without_username = active - with_username

        return {
            "total": total,
            "active": active,
            "with_username": with_username,
            "without_username": without_username
        }


async def clear_channel_subscribers(channel_id: int) -> int:
    """
    Полная очистка всех данных о подписчиках канала.

    Args:
        channel_id: ID канала

    Returns:
        Количество удаленных записей
    """
    async with async_session() as session:
        # Получаем количество записей для возврата
        result = await session.execute(
            select(func.count(ChannelSubscriber.id)).where(
                ChannelSubscriber.channel_id == channel_id
            )
        )
        count = result.scalar() or 0

        # Удаляем все записи
        await session.execute(
            delete(ChannelSubscriber).where(
                ChannelSubscriber.channel_id == channel_id
            )
        )
        await session.commit()

        logging.info(f"Cleared {count} subscribers for channel {channel_id}")
        return count


async def update_existing_subscribers(channel_id: int, subscribers: List[Dict]) -> int:
    """
    Обновление данных существующих активных подписчиков канала.
    В отличие от bulk_add, не добавляет новых подписчиков.

    Args:
        channel_id: ID канала
        subscribers: Список словарей с данными подписчиков

    Returns:
        Количество обновленных записей
    """
    if not subscribers:
        return 0

    updated_count = 0
    batch_size = 100

    async with async_session() as session:
        try:
            for i in range(0, len(subscribers), batch_size):
                batch = subscribers[i:i + batch_size]

                for sub_data in batch:
                    user_id = sub_data.get("user_id")
                    if not user_id:
                        continue

                    result = await session.execute(
                        select(ChannelSubscriber).where(
                            ChannelSubscriber.channel_id == channel_id,
                            ChannelSubscriber.user_id == user_id,
                            ChannelSubscriber.left_at.is_(None)  # Только активные
                        )
                    )
                    existing = result.scalar_one_or_none()

                    if existing:
                        # Обновляем данные
                        existing.username = sub_data.get("username")
                        existing.first_name = sub_data.get("first_name")
                        existing.full_name = sub_data.get("full_name")
                        updated_count += 1

            await session.commit()
            logging.info(f"Updated {updated_count} existing subscribers for channel {channel_id}")

        except Exception as e:
            await session.rollback()
            logging.error(f"Error in update_existing_subscribers for channel {channel_id}: {e}")
            raise

    return updated_count

