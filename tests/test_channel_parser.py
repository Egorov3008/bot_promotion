import pytest
from unittest.mock import AsyncMock, MagicMock
from pyrogram.errors import FloodWait, RPCError, UserNotParticipant, ChatAdminRequired
from pyrogram.enums import ChatMemberStatus

from utils.channel_parser import parse_channel_subscribers, get_pyrogram_client, check_pyrogram_client_admin_rights
from database.models import ChannelSubscriber
from database.database import bulk_add_channel_subscribers, clear_channel_subscribers, get_channel_subscribers_stats


@pytest.fixture
def mock_pyrogram_client():
    """Фикстура для мока Pyrogram клиента"""
    mock_app = MagicMock()
    mock_app.invoke = AsyncMock()
    mock_app.start = AsyncMock()
    mock_app.stop = AsyncMock()

    # get_chat_members должен возвращать async итератор (не AsyncMock)
    async def mock_get_chat_members(*args, **kwargs):
        return AsyncIteratorFromList([])
    mock_app.get_chat_members = mock_get_chat_members

    mock_app.get_chat_member = AsyncMock()
    return mock_app


@pytest.fixture
def sample_pyrogram_user():
    """Фикстура для мока Pyrogram User объекта"""
    mock_user = MagicMock()
    mock_user.id = 12345
    mock_user.username = "testuser"
    mock_user.first_name = "Test"
    mock_user.last_name = "User"
    mock_user.is_bot = False
    mock_user.is_verified = False
    mock_user.is_self = False
    mock_user.is_contact = False
    mock_user.is_mutual_contact = False
    mock_user.is_deleted = False
    mock_user.is_bot = False
    mock_user.is_fake = False
    mock_user.is_scam = False
    mock_user.is_support = False
    mock_user.is_restricted = False
    mock_user.is_creator = False # Добавлено
    mock_user.is_anonymous = False # Добавлено
    mock_user.status = "online" # Добавлено
    return mock_user


@pytest.fixture
def sample_pyrogram_bot_user():
    """Фикстура для мока Pyrogram User объекта (бот)"""
    mock_user = MagicMock()
    mock_user.id = 54321
    mock_user.username = "testbot"
    mock_user.first_name = "Test"
    mock_user.last_name = "Bot"
    mock_user.is_bot = True
    return mock_user


@pytest.fixture
def mock_chat_member_creator(sample_pyrogram_user):
    """Фикстура для мока Pyrogram ChatMember объекта (создатель)"""
    mock_member = MagicMock()
    mock_member.user = sample_pyrogram_user
    mock_member.status = ChatMemberStatus.OWNER
    mock_member.can_post_messages = True
    mock_member.can_edit_messages = True
    mock_member.can_delete_messages = True
    mock_member.can_invite_users = True
    mock_member.can_restrict_members = True
    mock_member.can_pin_messages = True
    mock_member.can_promote_members = True
    mock_member.can_manage_chat = True
    return mock_member


@pytest.fixture
def mock_chat_member_admin(sample_pyrogram_user):
    """Фикстура для мока Pyrogram ChatMember объекта (админ)"""
    mock_member = MagicMock()
    mock_member.user = sample_pyrogram_user
    mock_member.status = ChatMemberStatus.ADMINISTRATOR
    mock_member.can_post_messages = True
    mock_member.can_edit_messages = True
    mock_member.can_delete_messages = True
    mock_member.can_invite_users = True
    mock_member.can_restrict_members = True
    mock_member.can_pin_messages = True
    mock_member.can_promote_members = False  # Не создатель\n    mock_member.can_manage_chat = True
    return mock_member


@pytest.fixture
def mock_chat_member_member(sample_pyrogram_user):
    """Фикстура для мока Pyrogram ChatMember объекта (обычный пользователь)"""
    mock_member = MagicMock()
    mock_member.user = sample_pyrogram_user
    mock_member.status = ChatMemberStatus.MEMBER
    mock_member.can_post_messages = False
    mock_member.can_edit_messages = False
    mock_member.can_delete_messages = False
    return mock_member


@pytest.mark.asyncio
async def test_check_pyrogram_client_admin_rights_creator(mock_pyrogram_client, mock_chat_member_creator):
    """Тест проверки прав администратора для создателя канала."""
    mock_pyrogram_client.get_chat_member = AsyncMock(return_value=mock_chat_member_creator)
    channel_id = -1001234567890
    client_user_id = 123456789
    result = await check_pyrogram_client_admin_rights(mock_pyrogram_client, channel_id, client_user_id)
    assert result is True


@pytest.mark.asyncio
async def test_check_pyrogram_client_admin_rights_admin(mock_pyrogram_client, mock_chat_member_admin):
    """Тест проверки прав администратора для админа канала."""
    mock_pyrogram_client.get_chat_member = AsyncMock(return_value=mock_chat_member_admin)
    channel_id = -1001234567890
    client_user_id = 123456789
    result = await check_pyrogram_client_admin_rights(mock_pyrogram_client, channel_id, client_user_id)
    assert result is True


@pytest.mark.asyncio
async def test_check_pyrogram_client_admin_rights_member(mock_pyrogram_client, mock_chat_member_member):
    """Тест проверки прав администратора для обычного пользователя канала."""
    mock_pyrogram_client.get_chat_member = AsyncMock(return_value=mock_chat_member_member)
    channel_id = -1001234567890
    client_user_id = 123456789
    result = await check_pyrogram_client_admin_rights(mock_pyrogram_client, channel_id, client_user_id)
    assert result is False


@pytest.mark.asyncio
async def test_check_pyrogram_client_admin_rights_not_participant(mock_pyrogram_client):
    """Тест проверки прав администратора, когда клиент не является участником канала."""
    mock_pyrogram_client.get_chat_member = AsyncMock(side_effect=UserNotParticipant("Not a participant"))
    channel_id = -1001234567890
    client_user_id = 123456789
    result = await check_pyrogram_client_admin_rights(mock_pyrogram_client, channel_id, client_user_id)
    assert result is False


@pytest.mark.asyncio
async def test_check_pyrogram_client_admin_rights_rpc_error(mock_pyrogram_client):
    """Тест проверки прав администратора при RPC ошибке."""
    mock_pyrogram_client.get_chat_member = AsyncMock(side_effect=RPCError("RPC Error"))
    channel_id = -1001234567890
    client_user_id = 123456789
    result = await check_pyrogram_client_admin_rights(mock_pyrogram_client, channel_id, client_user_id)
    assert result is False


# Helper для создания async генератора из списка
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
        item = self.items[self.index]
        self.index += 1
        return item


class MockPyrogramClient:
    """Простой mock-класс для Pyrogram клиента."""
    def __init__(self):
        self.invoke = AsyncMock()
        self.start = AsyncMock()
        self.stop = AsyncMock()
        self._get_chat_members_data = {}

    async def get_chat_members(self, chat_id, *args, **kwargs):
        """Возвращает async итератор на основе сохраненных данных."""
        key = str(chat_id)
        items = self._get_chat_members_data.get(key, [])
        return AsyncIteratorFromList(items)

    def set_chat_members_data(self, channel_id, members):
        """Устанавливает данные для мока get_chat_members."""
        self._get_chat_members_data[str(channel_id)] = members

    def set_get_chat_members_side_effect(self, func):
        """Переопределяет поведение get_chat_members."""
        self.get_chat_members = func

    async def get_chat_member(self, chat_id, user_id):
        """Mock для get_chat_member."""
        return AsyncMock()()


@pytest.fixture
def mock_pyrogram_client():
    """Фикстура для мока Pyrogram клиента"""
    return MockPyrogramClient()


# --- Тесты для parse_channel_subscribers ---

@pytest.mark.asyncio
async def test_parse_channel_subscribers_success(mock_pyrogram_client, sample_pyrogram_user):
    """Тест успешного парсинга подписчиков канала."""
    user_with_username = sample_pyrogram_user
    user_without_username = MagicMock(id=12346, username=None, first_name="No", last_name="User")
    bot_user = MagicMock(id=12347, username="botty", first_name="Bot", is_bot=True)

    mock_chat_member_1 = MagicMock(user=user_with_username)
    mock_chat_member_2 = MagicMock(user=user_without_username)
    mock_chat_member_3 = MagicMock(user=bot_user)

    # Устанавливаем данные для мока
    mock_pyrogram_client.set_chat_members_data(-1001234567890, [
        mock_chat_member_1,
        mock_chat_member_2,
        mock_chat_member_3,
    ])

    channel_id = -1001234567890
    subscribers, total_members, has_username_count = await parse_channel_subscribers(mock_pyrogram_client, channel_id)

    assert total_members == 3  # Все найденные пользователи
    assert has_username_count == 1  # Только testuser
    assert len(subscribers) == 1
    assert subscribers[0]["user_id"] == user_with_username.id
    assert subscribers[0]["username"] == user_with_username.username
    assert subscribers[0]["first_name"] == user_with_username.first_name
    assert subscribers[0]["full_name"] == f"{user_with_username.first_name} {user_with_username.last_name}"


@pytest.mark.asyncio
async def test_parse_channel_subscribers_large_channel(mock_pyrogram_client, sample_pyrogram_user, monkeypatch):
    """Тест парсинга большого канала с лимитами и задержками."""
    # Создаем много пользователей
    users_data = []
    for i in range(105):
        user = MagicMock(id=10000 + i, username=f"user{i}", first_name=f"User{i}", last_name=f"Last{i}", is_bot=False)
        users_data.append(MagicMock(user=user))

    mock_pyrogram_client.set_chat_members_data(-1001234567890, users_data)

    # Мокаем sleep для ускорения тестов
    mock_sleep = AsyncMock()
    monkeypatch.setattr("asyncio.sleep", mock_sleep)

    channel_id = -1001234567890
    subscribers, total_members, has_username_count = await parse_channel_subscribers(mock_pyrogram_client, channel_id)

    assert total_members == 105
    assert has_username_count == 105
    assert len(subscribers) == 105
    # Проверяем, что sleep вызывался хотя бы раз (для обработки лимита)
    assert mock_sleep.call_count >= 1


@pytest.mark.asyncio
async def test_parse_channel_subscribers_flood_wait(mock_pyrogram_client, sample_pyrogram_user, monkeypatch):
    """Тест обработки FloodWait при парсинге."""
    user1 = MagicMock(user=sample_pyrogram_user)
    user2 = MagicMock(user=MagicMock(id=12346, username="user2", first_name="User", last_name="Two", is_bot=False))

    # Создаем итератор, который вызывает FloodWait после первого элемента
    class FloodWaitIterator:
        def __init__(self, items, exception_after=1):
            self.items = items
            self.exception_after = exception_after
            self.index = 0

        def __aiter__(self):
            return self

        async def __anext__(self):
            if self.index >= len(self.items):
                raise StopAsyncIteration
            if self.index >= self.exception_after:
                raise FloodWait(value=1)
            item = self.items[self.index]
            self.index += 1
            return item

    # Переопределяем get_chat_members для этого теста
    async def mock_get_chat_fw(chat_id, *args, **kwargs):
        return FloodWaitIterator([user1, user2], exception_after=1)

    mock_pyrogram_client.set_get_chat_members_side_effect(mock_get_chat_fw)

    mock_sleep = AsyncMock()
    monkeypatch.setattr("asyncio.sleep", mock_sleep)

    channel_id = -1001234567890
    subscribers, total_members, has_username_count = await parse_channel_subscribers(mock_pyrogram_client, channel_id)

    assert total_members == 2
    assert has_username_count == 2
    assert len(subscribers) == 2
    # Проверяем, что sleep вызывался для FloodWait
    mock_sleep.assert_any_call(1 + 0.5) # 1 из FloodWait + 0.5 на всякий случай


@pytest.mark.asyncio
async def test_parse_channel_subscribers_rpc_error(mock_pyrogram_client):
    """Тест обработки RPCError при парсинге."""
    async def raise_rpc_error(*args, **kwargs):
        raise RPCError("Test RPC Error")
    mock_pyrogram_client.set_get_chat_members_side_effect(raise_rpc_error)

    channel_id = -1001234567890
    subscribers, total_members, has_username_count = await parse_channel_subscribers(mock_pyrogram_client, channel_id)

    assert total_members == 0
    assert has_username_count == 0
    assert len(subscribers) == 0


@pytest.mark.asyncio
async def test_parse_channel_subscribers_no_permissions(mock_pyrogram_client):
    """Тест обработки отсутствия прав при парсинге."""
    async def raise_no_permissions(*args, **kwargs):
        raise ChatAdminRequired("Admin rights needed")
    mock_pyrogram_client.set_get_chat_members_side_effect(raise_no_permissions)

    channel_id = -1001234567890
    subscribers, total_members, has_username_count = await parse_channel_subscribers(mock_pyrogram_client, channel_id)

    assert total_members == 0
    assert has_username_count == 0
    assert len(subscribers) == 0
