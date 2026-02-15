"""
Тесты для модуля pyrogram_app/parsing_mode.py

Покрывают:
- Инициализацию ParsingMode
- Проверку прав администратора
- Полный парсинг подписчиков
- Инкрементальный парсинг подписчиков
- Получение количества участников
- Получение информации о конкретном участнике
- Проверку активности пользователей
- Получение реакций на сообщение
- Получение информации о канале
- Остановку парсинга
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone
from pyrogram.errors import FloodWait, BadRequest, UserNotParticipant, RPCError
from pyrogram.enums import ChatMemberStatus
from pyrogram.raw.types import stats

from pyrogram_app.parsing_mode import ParsingMode, ParsingStats, SubscriberInfo
from tests.conftest import AsyncIteratorFromList


@pytest.fixture
def parsing_mode(mock_pyrogram_client):
    return ParsingMode(mock_pyrogram_client)

class TestParsingMode:
    """Тесты для класса ParsingMode"""

    # @pytest.fixture # Removed, now a module-level fixture
    # def parsing_mode(self, mock_pyrogram_client):
    #     return ParsingMode(mock_pyrogram_client)


    def test_init(self, mock_pyrogram_client, parsing_mode):
        """Тест инициализации ParsingMode"""
        assert parsing_mode.client == mock_pyrogram_client
        assert parsing_mode._stop_event is not None

    @pytest.mark.asyncio
    async def test_check_admin_rights_true(self, parsing_mode, mock_external_parsing_funcs):
        """Тест успешной проверки прав администратора"""
        mock_external_parsing_funcs["pyrogram_app.parsing_mode.check_pyrogram_client_admin_rights"].return_value = True
        has_rights, message = await parsing_mode.check_admin_rights(123)
        assert has_rights is True
        assert message == "✅ Бот имеет права администратора"
        mock_external_parsing_funcs["pyrogram_app.parsing_mode.check_pyrogram_client_admin_rights"].assert_awaited_once_with(parsing_mode.client, 123)

    @pytest.mark.asyncio
    async def test_check_admin_rights_false(self, parsing_mode, mock_external_parsing_funcs):
        """Тест неудачной проверки прав администратора"""
        mock_external_parsing_funcs["pyrogram_app.parsing_mode.check_pyrogram_client_admin_rights"].return_value = False
        has_rights, message = await parsing_mode.check_admin_rights(123)
        assert has_rights is False
        assert message == "❌ У бота нет прав администратора в канале"

    @pytest.mark.asyncio
    async def test_parse_full_success(self, parsing_mode, mock_external_parsing_funcs):
        """Тест успешного полного парсинга"""
        mock_external_parsing_funcs["pyrogram_app.parsing_mode.parse_channel_subscribers"].return_value = (
            [
                {"user_id": 1, "first_name": "User1", "username": "user1"},
                {"user_id": 2, "first_name": "User2", "username": None}
            ],
            1,  # with_username_count
            1   # bots_count
        )
        
        subscribers, stats = await parsing_mode.parse_full(123)
        
        assert len(subscribers) == 2
        assert stats.total_processed == 3  # 2 пользователя + 1 бот
        assert stats.with_username == 1
        assert stats.bots_count == 1
        mock_external_parsing_funcs["pyrogram_app.parsing_mode.parse_channel_subscribers"].assert_awaited_once_with(parsing_mode.client, 123, progress_callback=None)
        mock_external_parsing_funcs["pyrogram_app.parsing_mode.parse_channel_subscribers"].assert_awaited_once()

    @pytest.mark.asyncio
    async def test_parse_full_with_callback(self, parsing_mode, mock_external_parsing_funcs):
        """Тест полного парсинга с callback'ом"""
        # Ensure the mock for parse_channel_subscribers is set correctly for this test
        mock_external_parsing_funcs["pyrogram_app.parsing_mode.parse_channel_subscribers"].return_value = (
            [
                {"user_id": 1, "first_name": "User1", "username": "user1"},
            ],
            1, 0
        )
        mock_callback = AsyncMock()
        mock_external_parsing_funcs["pyrogram_app.parsing_mode.parse_channel_subscribers"].assert_awaited_once_with(parsing_mode.client, 123, progress_callback=mock_callback)
        # assert mock_callback.called # Not asserting the callback directly, as it's passed to external func
        mock_callback.assert_awaited_once_with(stats)

    @pytest.mark.asyncio
    async def test_parse_full_value_error(self, parsing_mode, mock_external_parsing_funcs):
        """Тест обработки ValueError при полном парсинге"""
        mock_external_parsing_funcs["pyrogram_app.parsing_mode.parse_channel_subscribers"].side_effect = ValueError("Test Error")
        with pytest.raises(ValueError, match="Test Error"):
            await parsing_mode.parse_full(123)

    @pytest.mark.asyncio
    async def test_parse_incremental_success(self, parsing_mode, mock_pyrogram_client, mock_pyrogram_user, mock_pyrogram_bot, mock_pyrogram_user_no_username):
        """Тест успешного инкрементального парсинга"""
        known_users = [mock_pyrogram_user.id]
        
        # Мокаем get_chat_members для инкрементального парсинга
        mock_member_new_user = MagicMock(user=mock_pyrogram_user_no_username)
        mock_member_bot = MagicMock(user=mock_pyrogram_bot)
        mock_member_known = MagicMock(user=mock_pyrogram_user)

        mock_pyrogram_client.get_chat_members.return_value = AsyncIteratorFromList([
            mock_member_known, # Уже известный пользователь
            mock_member_new_user, # Новый пользователь без username
            mock_member_bot, # Бот
        ])
        
        new_subscribers, stats = await parsing_mode.parse_incremental(123, known_users)
        
        assert len(new_subscribers) == 1
        assert stats.added_count == 1 # Renamed from total_processed
        assert stats.total_processed == 1
        assert stats.with_username == 1
        assert stats.bots_count == 1
        mock_pyrogram_client.get_chat_members.assert_awaited_once_with(chat_id=123)

    @pytest.mark.asyncio
    async def test_parse_incremental_flood_wait(self, parsing_mode, mock_pyrogram_client, mock_pyrogram_user, mock_external_parsing_funcs):
        """Тест обработки FloodWait при инкрементальном парсинге"""
        mock_pyrogram_client.get_chat_members.side_effect = FloodWait(value=1)
        
        new_subscribers, stats = await parsing_mode.parse_incremental(123, [])
        
        mock_external_parsing_funcs["pyrogram_app.parsing_mode.asyncio.sleep"].assert_awaited_once_with(1 + 1) # Use the patched sleep
        mock_external_parsing_funcs["asyncio.sleep"].assert_awaited_once_with(1 + 1)

    @pytest.mark.asyncio
    async def test_get_channel_members_count_success(self, parsing_mode, mock_pyrogram_client, mock_chat_info):
        # Ensure the mock for get_chat returns an AsyncMock object
        mock_chat_info_async = AsyncMock()
        mock_chat_info_async.members_count = 500
        mock_pyrogram_client.get_chat.return_value = mock_chat_info_async
        mock_pyrogram_client.get_chat.return_value = mock_chat_info
        
        count = await parsing_mode.get_channel_members_count(-1001234567890)
        
        assert count == 500
        mock_pyrogram_client.get_chat.assert_awaited_once_with(chat_id=-1001234567890)

    @pytest.mark.asyncio
    async def test_get_channel_members_count_error(self, parsing_mode, mock_pyrogram_client):
        """Тест получения количества участников при ошибке"""
        mock_pyrogram_client.get_chat.side_effect = Exception("Failed to get chat")
        
        count = await parsing_mode.get_channel_members_count(-1001234567890)
        
        assert count == 0

    @pytest.mark.asyncio
    async def test_get_member_info_success(self, parsing_mode, mock_pyrogram_client, mock_chat_member):
        """Тест успешного получения информации об участнике"""
        mock_pyrogram_client.get_chat_member.return_value = mock_chat_member
        
        info = await parsing_mode.get_member_info(-1001234567890, 12345)
        
        assert info["user_id"] == mock_chat_member.user.id
        assert info["status"] == mock_chat_member.status
        mock_pyrogram_client.get_chat_member.assert_awaited_once_with(chat_id=-1001234567890, user_id=12345)

    @pytest.mark.asyncio
    async def test_get_member_info_not_participant(self, parsing_mode, mock_pyrogram_client):
        """Тест получения информации об участнике, которого нет в канале"""
        mock_pyrogram_client.get_chat_member.side_effect = BadRequest("USER_NOT_PARTICIPANT")
        
        info = await parsing_mode.get_member_info(-1001234567890, 12345)
        
        assert info is None

    @pytest.mark.asyncio
    async def test_check_user_activity_in_channel(self, parsing_mode, mock_pyrogram_client, mock_chat_member):
        """Тест проверки активности пользователя, который в канале"""
        mock_chat_member.status = ChatMemberStatus.MEMBER # Set the enum directly
        mock_chat_member.status = ChatMemberStatus.MEMBER.value
        
        activity_report = await parsing_mode.check_user_activity(-1001234567890, [12345])
        
        assert 12345 in activity_report
        assert activity_report[12345]["in_channel"] is True
        assert activity_report[12345]["is_active"] is True

    @pytest.mark.asyncio
    async def test_check_user_activity_not_in_channel(self, parsing_mode, mock_pyrogram_client):
        """Тест проверки активности пользователя, которого нет в канале"""
        mock_pyrogram_client.get_chat_member.side_effect = BadRequest("USER_NOT_PARTICIPANT")
        
        activity_report = await parsing_mode.check_user_activity(-1001234567890, [12345])
        
        assert 12345 in activity_report
        assert activity_report[12345]["in_channel"] is False
        assert activity_report[12345]["is_active"] is False
        assert activity_report[12345]["status"] == "left"

    @pytest.mark.asyncio
    async def test_get_recent_message_reactions_success(self, parsing_mode, mock_pyrogram_client, mock_message_with_reactions):
        """Тест остановки парсинга"""
        parsing_mode.stop()
