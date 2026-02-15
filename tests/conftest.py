import pytest
import asyncio
from datetime import datetime, timezone
from unittest.mock import MagicMock, AsyncMock, patch

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import sessionmaker
from pyrogram import Client, types
from pyrogram.enums import ChatMemberStatus

from database.models import Base, Channel, Admin, Giveaway, Participant, ChannelSubscriber
from pyrogram_app.parsing_mode import ParsingMode


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
    return Participant(
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


# ============ Фикстуры для модуля pyrogram_app ============

@pytest.fixture
def mock_config():
    """Фикстура для мока конфигурации Pyrogram"""
    config = MagicMock()
    config.SESSION_NAME = "test_session"
    config.API_ID = 12345
    config.API_HASH = "test_hash"
    config.PHONE_NUMBER = "+79001234567"
    return config


@pytest.fixture(scope="function")
async def mock_pyrogram_client():
    client = AsyncMock(spec=Client)
    client.get_chat.return_value = AsyncMock(spec=types.Chat)
    client.get_chat_member.return_value = AsyncMock(spec=types.ChatMember)
    client.get_chat_history.return_value = AsyncMock()
    client.get_chat_members.return_value = AsyncIteratorFromList([]) # Default empty
    yield client


@pytest.fixture(scope="function")
def mock_external_parsing_funcs():
    with patch("pyrogram_app.parsing_mode.check_pyrogram_client_admin_rights", new_callable=MagicMock) as mock_check_admin, \
         patch("pyrogram_app.parsing_mode.parse_channel_subscribers", new_callable=MagicMock) as mock_parse_subscribers, \
         patch("pyrogram_app.parsing_mode.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        yield {
            "pyrogram_app.parsing_mode.check_pyrogram_client_admin_rights": mock_check_admin,
            "pyrogram_app.parsing_mode.parse_channel_subscribers": mock_parse_subscribers,
            "pyrogram_app.parsing_mode.asyncio.sleep": mock_sleep,
        }


@pytest.fixture(scope="function")
async def parsing_mode(mock_pyrogram_client):
    mode = ParsingMode(pyro_client=mock_pyrogram_client)
    yield mode


@pytest.fixture
def mock_pyrogram_user():
    user = MagicMock(spec=types.User)
    user.id = 1
    user.first_name = "Test User"
    user.username = "testuser"
    user.is_bot = False
    return user


@pytest.fixture
def mock_pyrogram_bot():
    bot = MagicMock(spec=types.User)
    bot.id = 999
    bot.first_name = "Test Bot"
    bot.username = "testbot"
    bot.is_bot = True
    return bot


@pytest.fixture
def mock_pyrogram_user_no_username():
    user = MagicMock(spec=types.User)
    user.id = 2
    user.first_name = "No Username User"
    user.username = None
    user.is_bot = False
    return user


@pytest.fixture
def mock_chat_info():
    chat = MagicMock(spec=types.Chat)
    chat.id = -1001234567890
    chat.title = "Test Channel"
    chat.members_count = 100
    chat.username = None # Added missing username attribute
    return chat


@pytest.fixture
def mock_chat_member():
    member = MagicMock(spec=types.ChatMember)
    member.user = MagicMock(spec=types.User)
    member.user.id = 12345
    member.user.first_name = "Member Name"
    member.user.username = "memberusername"
    member.status = ChatMemberStatus.MEMBER
    member.joined_date = "Неизвестно"
    return member


@pytest.fixture
def mock_message():
    message = MagicMock(spec=types.Message)
    message.reactions = None # Message with no reactions
    return message


@pytest.fixture
def mock_message_with_reactions():
    message = MagicMock(spec=types.Message)
    # Mock the reactions data structure including a list of members
    message.reactions = [      MagicMock(emoji="👍", total_count=5,
              custom_reactions=[],
              recent_senders=[MagicMock(is_bot=False, is_self=False, is_contact=False, is_mutual_contact=False, is_deleted=False, id=111111111, first_name='ReactUser1'),
                              MagicMock(is_bot=False, is_self=False, is_contact=False, is_mutual_contact=False, is_deleted=False, id=222222222, first_name='ReactUser2')]),
      MagicMock(emoji="❤️", total_count=3,
              custom_reactions=[],
              recent_senders=[MagicMock(is_bot=False, is_self=False, is_contact=False, is_mutual_contact=False, is_deleted=False, id=333333333, first_name='ReactUser3'),
                              MagicMock(is_bot=False, is_self=False, is_contact=False, is_mutual_contact=False, is_deleted=False, id=444444444, first_name='ReactUser4')])
    ]
    return message


@pytest.fixture
def mock_update_message_reactions():
    """Фикстура для мока UpdateMessageReactions (raw update)"""
    from pyrogram.raw.types import UpdateMessageReactions
    mock_update = MagicMock(spec=UpdateMessageReactions)
    mock_update.peer = MagicMock()
    mock_update.peer.channel_id = 1234567890
    mock_update.msg_id = 1
    
    mock_update.reactions = MagicMock()
    
    # Мок для реакции
    mock_reaction = MagicMock()
    mock_peer1 = MagicMock()
    mock_peer1.user_id = 111111111
    mock_peer2 = MagicMock()
    mock_peer2.user_id = 222222222
    
    mock_reaction.peer_ids = [mock_peer1, mock_peer2]
    
    mock_update.reactions.results = [mock_reaction]
    
    return mock_update


# Вспомогательный класс для создания async итератора из списка
class AsyncIteratorFromList:
    """Класс для создания async итератора из списка (совместим с async for)."""
    def __init__(self, items):
        self.items = items
        self.index = 0

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self.index >= len(self.items):
            raise StopAsyncIteration
        value = self.items[self.index]
        self.index += 1
        return value


# Фиксим ошибки из-за sqlite async
@pytest.fixture(autouse=True)
def use_mock_sqlite(monkeypatch):
    monkeypatch.setattr("aiosqlite.connect", MagicMock(return_value=AsyncMock(aenter=AsyncMock(), aexit=AsyncMock())))
