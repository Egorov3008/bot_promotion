import pytest
import asyncio
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import sessionmaker

from database.models import Base, Channel, Admin, Giveaway, Participant, ChannelSubscriber


# Тестовая база данных в памяти
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest.fixture(scope="function")
async def test_engine():
    """Фикстура для создания тестового движка базы данных"""
    engine = create_async_engine(
        TEST_DATABASE_URL,
        echo=False,
        connect_args={"check_same_thread": False}
    )
    
    # Создаем все таблицы
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    yield engine
    
    # Очистка после теста
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    
    await engine.dispose()


@pytest.fixture(scope="function")
async def test_session_maker(test_engine):
    """Фикстура для создания фабрики сессий"""
    async_session_maker = async_sessionmaker(
        test_engine,
        class_=AsyncSession,
        expire_on_commit=False
    )
    yield async_session_maker


@pytest.fixture(scope="function")
async def test_session(test_session_maker):
    """Фикстура для создания тестовой сессии"""
    async with test_session_maker() as session:
        yield session
        # Откат транзакции после теста
        await session.rollback()


@pytest.fixture
def sample_admin():
    """Фикстура с примером админа"""
    return Admin(
        user_id=123456789,
        username="testadmin",
        first_name="Test",
        last_name="Admin"
    )


@pytest.fixture
def sample_channel():
    """Фикстура с примером канала"""
    return Channel(
        channel_id=-1001234567890,
        channel_name="Test Channel",
        channel_username="testchannel",
        added_by=123456789
    )


@pytest.fixture
def sample_giveaway(sample_channel):
    """Фикстура с примером розыгрыша"""
    return Giveaway(
        channel_id=sample_channel.channel_id,
        message_id=1,
        title="Test Giveaway",
        description="Test description",
        winners_count=3,
        end_time=datetime.now(timezone.utc),
        created_by=123456789,
        status="active"
    )


@pytest.fixture
def sample_participant(sample_giveaway):
    """Фикстура с примером участника розыгрыша"""
    return GiveawayParticipant(
        giveaway_id=sample_giveaway.id,
        user_id=111111111,
        username="participant1",
        first_name="Participant",
        last_name="One",
        joined_at=datetime.now(timezone.utc)
    )


@pytest.fixture
def sample_channel_subscriber(sample_channel):
    """Фикстура с примером подписчика канала"""
    return ChannelSubscriber(
        channel_id=sample_channel.channel_id,
        user_id=111111111,
        username="subscriber1",
        first_name="Subscriber",
        last_name="One",
        full_name="Subscriber One",
        added_at=datetime.now(timezone.utc)
    )
