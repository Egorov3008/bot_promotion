import pytest
from datetime import datetime, timezone
from sqlalchemy import select
from unittest.mock import AsyncMock, MagicMock

from database.database import (
    bulk_add_channel_subscribers,
    get_channel_subscribers_stats,
    clear_channel_subscribers
)
from database.models import ChannelSubscriber, Channel


@pytest.fixture
async def setup_channel(test_session):
    """Фикстура для создания тестового канала"""
    channel = Channel(
        channel_id=-1001234567890,
        channel_name="Test Channel",
        channel_username="testchannel",
        added_by=123456789
    )
    test_session.add(channel)
    await test_session.commit()
    await test_session.refresh(channel)
    return channel


@pytest.fixture
def sample_subscribers():
    """Фикстура с примерами данных подписчиков"""
    return [
        {
            "user_id": 111111111,
            "username": "user1",
            "first_name": "User",
            "last_name": "One"
        },
        {
            "user_id": 222222222,
            "username": "user2",
            "first_name": "User",
            "last_name": "Two"
        },
        {
            "user_id": 333333333,
            "username": "user3",
            "first_name": "User",
            "last_name": "Three"
        }
    ]


@pytest.mark.asyncio
async def test_bulk_add_channel_subscribers_new_subscribers(
    test_session,
    setup_channel,
    sample_subscribers
):
    """Тест массового добавления новых подписчиков"""
    channel_id = setup_channel.channel_id
    
    added, updated = await bulk_add_channel_subscribers(
        channel_id,
        sample_subscribers
    )
    
    await test_session.commit()
    
    # Проверяем результаты
    assert added == 3
    assert updated == 0
    
    # Проверяем, что подписчики добавлены в БД
    result = await test_session.execute(
        select(ChannelSubscriber).where(
            ChannelSubscriber.channel_id == channel_id
        )
    )
    subscribers = result.scalars().all()
    
    assert len(subscribers) == 3
    assert all(s.username for s in subscribers)  # Все должны иметь username
    assert all(s.left_at is None for s in subscribers)  # Все активные


@pytest.mark.asyncio
async def test_bulk_add_channel_subscribers_update_existing(
    test_session,
    setup_channel,
    sample_subscribers
):
    """Тест обновления существующих подписчиков (вернувшихся)"""
    channel_id = setup_channel.channel_id
    
    # Сначала добавляем одного подписчика с left_at (отписавшегося)
    subscriber = ChannelSubscriber(
        channel_id=channel_id,
        user_id=111111111,
        username="old_username",
        first_name="Old",
        full_name="Old Name",
        added_at=datetime.now(timezone.utc),
        left_at=datetime.now(timezone.utc)
    )
    test_session.add(subscriber)
    await test_session.commit()
    
    # Теперь массово добавляем, включая того же пользователя
    added, updated = await bulk_add_channel_subscribers(
        channel_id,
        sample_subscribers
    )
    
    await test_session.commit()
    
    # Проверяем результаты
    assert added == 2  # 2 новых пользователя
    assert updated == 1  # 1 обновленный (вернувшийся)
    
    # Проверяем, что вернувшийся пользователь теперь активен
    result = await test_session.execute(
        select(ChannelSubscriber).where(
            ChannelSubscriber.channel_id == channel_id,
            ChannelSubscriber.user_id == 111111111
        )
    )
    returned_subscriber = result.scalar_one()
    
    assert returned_subscriber.left_at is None  # Теперь активен
    assert returned_subscriber.username == "user1"  # Данные обновлены


@pytest.mark.asyncio
async def test_bulk_add_channel_subscribers_duplicates(
    test_session,
    setup_channel,
    sample_subscribers
):
    """Тест обработки дубликатов (уже активные подписчики)"""
    channel_id = setup_channel.channel_id
    
    # Сначала добавляем подписчиков
    await bulk_add_channel_subscribers(channel_id, sample_subscribers)
    await test_session.commit()
    
    # Пытаемся добавить тех же подписчиков снова
    added, updated = await bulk_add_channel_subscribers(
        channel_id,
        sample_subscribers
    )
    
    await test_session.commit()
    
    # Проверяем, что дубликаты не добавлены
    assert added == 0
    assert updated == 0
    
    # Проверяем, что количество подписчиков не изменилось
    result = await test_session.execute(
        select(func.count(ChannelSubscriber.id)).where(
            ChannelSubscriber.channel_id == channel_id
        )
    )
    count = result.scalar()
    
    assert count == 3


@pytest.mark.asyncio
async def test_bulk_add_channel_subscribers_empty_list(
    test_session,
    setup_channel
):
    """Тест обработки пустого списка подписчиков"""
    channel_id = setup_channel.channel_id
    
    added, updated = await bulk_add_channel_subscribers(channel_id, [])
    
    assert added == 0
    assert updated == 0


@pytest.mark.asyncio
async def test_get_channel_subscribers_stats(test_session, setup_channel):
    """Тест получения статистики по подписчикам"""
    channel_id = setup_channel.channel_id
    
    # Добавляем разных подписчиков
    subscribers_data = [
        {
            "user_id": 111111111,
            "username": "user1",
            "first_name": "User"
        },
        {
            "user_id": 222222222,
            "username": "user2",
            "first_name": "User"
        },
        {
            "user_id": 333333333,
            "username": None,  # Без username
            "first_name": "NoUsername"
        }
    ]
    
    await bulk_add_channel_subscribers(channel_id, subscribers_data[:2])
    
    # Добавляем подписчика без username вручную
    subscriber_no_username = ChannelSubscriber(
        channel_id=channel_id,
        user_id=333333333,
        username=None,
        first_name="NoUsername",
        full_name="NoUsername"
    )
    test_session.add(subscriber_no_username)
    await test_session.commit()
    
    # Получаем статистику
    stats = await get_channel_subscribers_stats(channel_id)
    
    # Проверяем результаты
    assert stats["total"] == 3
    assert stats["active"] == 3
    assert stats["with_username"] == 2
    assert stats["without_username"] == 1


@pytest.mark.asyncio
async def test_get_channel_subscribers_stats_with_left_subscribers(
    test_session,
    setup_channel,
    sample_subscribers
):
    """Тест статистики с отписавшимися подписчиками"""
    channel_id = setup_channel.channel_id
    
    # Добавляем подписчиков
    await bulk_add_channel_subscribers(channel_id, sample_subscribers)
    
    # Отписываем одного
    result = await test_session.execute(
        select(ChannelSubscriber).where(
            ChannelSubscriber.channel_id == channel_id,
            ChannelSubscriber.user_id == 111111111
        )
    )
    subscriber = result.scalar_one()
    subscriber.left_at = datetime.now(timezone.utc)
    await test_session.commit()
    
    # Получаем статистику
    stats = await get_channel_subscribers_stats(channel_id)
    
    # Проверяем результаты
    assert stats["total"] == 3  # Всего записей
    assert stats["active"] == 2  # Активных
    assert stats["with_username"] == 2  # С username (только активные)


@pytest.mark.asyncio
async def test_get_channel_subscribers_stats_empty_channel(
    test_session,
    setup_channel
):
    """Тест статистики для канала без подписчиков"""
    channel_id = setup_channel.channel_id
    
    stats = await get_channel_subscribers_stats(channel_id)
    
    assert stats["total"] == 0
    assert stats["active"] == 0
    assert stats["with_username"] == 0
    assert stats["without_username"] == 0


@pytest.mark.asyncio
async def test_clear_channel_subscribers(test_session, setup_channel, sample_subscribers):
    """Тест очистки подписчиков канала"""
    channel_id = setup_channel.channel_id
    
    # Добавляем подписчиков
    await bulk_add_channel_subscribers(channel_id, sample_subscribers)
    await test_session.commit()
    
    # Проверяем, что подписчики добавлены
    result = await test_session.execute(
        select(func.count(ChannelSubscriber.id)).where(
            ChannelSubscriber.channel_id == channel_id
        )
    )
    count_before = result.scalar()
    assert count_before == 3
    
    # Очищаем подписчиков
    deleted_count = await clear_channel_subscribers(channel_id)
    
    assert deleted_count == 3
    
    # Проверяем, что подписчики удалены
    result = await test_session.execute(
        select(func.count(ChannelSubscriber.id)).where(
            ChannelSubscriber.channel_id == channel_id
        )
    )
    count_after = result.scalar()
    assert count_after == 0


@pytest.mark.asyncio
async def test_clear_channel_subscribers_empty_channel(test_session, setup_channel):
    """Тест очистки подписчиков для пустого канала"""
    channel_id = setup_channel.channel_id
    
    deleted_count = await clear_channel_subscribers(channel_id)
    
    assert deleted_count == 0


@pytest.mark.asyncio
async def test_bulk_add_channel_subscribers_large_batch(
    test_session,
    setup_channel
):
    """Тест массового добавления большого количества подписчиков"""
    channel_id = setup_channel.channel_id
    
    # Генерируем 500 подписчиков
    large_subscribers = [
        {
            "user_id": i,
            "username": f"user{i}",
            "first_name": f"User{i}",
            "last_name": "Test"
        }
        for i in range(1, 501)
    ]
    
    added, updated = await bulk_add_channel_subscribers(
        channel_id,
        large_subscribers
    )
    
    await test_session.commit()
    
    assert added == 500
    assert updated == 0
    
    # Проверяем, что все подписчики добавлены
    result = await test_session.execute(
        select(func.count(ChannelSubscriber.id)).where(
            ChannelSubscriber.channel_id == channel_id
        )
    )
    count = result.scalar()
    
    assert count == 500


# Импортируем func для использования в тестах
from sqlalchemy import func
