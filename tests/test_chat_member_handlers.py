from datetime import datetime, timedelta
from unittest.mock import patch, AsyncMock

import pytest
from aiogram.types import (
    Chat,
    User,
    ChatMemberUpdated,
    ChatMemberLeft,
    ChatMemberMember,
    ChatMemberRestricted,
    ChatMemberBanned,
)

from handlers.chat_member_handlers import handle_new_subscriber


def create_chat_member_update(
    old_status: str, new_status: str, chat_type: str = "channel"
) -> ChatMemberUpdated:
    """
    Вспомогательная функция для создания объекта ChatMemberUpdated
    """
    user = User(id=111222333, is_bot=False, first_name="Test User", username="testuser")

    def make_member(status: str):
        if status == "left":
            return ChatMemberLeft(user=user)
        elif status == "member":
            return ChatMemberMember(user=user)
        elif status == "restricted":
            # Все обязательные поля для ChatMemberRestricted
            return ChatMemberRestricted(
                user=user,
                is_member=True,
                can_send_messages=False,
                can_send_audios=False,
                can_send_documents=False,
                can_send_photos=False,
                can_send_videos=False,
                can_send_video_notes=False,
                can_send_voice_notes=False,
                can_send_polls=False,
                can_send_other_messages=False,
                can_add_web_page_previews=False,
                can_change_info=False,
                can_invite_users=False,
                can_pin_messages=False,
                can_manage_topics=False,
                until_date=datetime.now() + timedelta(minutes=5),  # Должно быть в будущем
            )
        elif status == "kicked":
            return ChatMemberBanned(
                user=user,
                until_date=datetime.now() + timedelta(days=30),
            )
        else:
            raise ValueError(f"Unsupported chat member status: {status}")

    old_chat_member = make_member(old_status)
    new_chat_member = make_member(new_status)

    return ChatMemberUpdated(
        chat=Chat(id=123456789, type=chat_type, title="Test Channel"),
        from_user=User(id=987654321, is_bot=False, first_name="Admin"),
        date=datetime.now(),
        old_chat_member=old_chat_member,
        new_chat_member=new_chat_member,
    )


class TestChatMemberHandlers:
    """
    Тесты для обработчика событий участников каналов
    """

    @pytest.mark.asyncio
    async def test_handle_new_subscriber_channel_join(self):
        """Тест обработки присоединения пользователя к каналу"""
        with patch(
            "handlers.chat_member_handlers.add_channel_subscriber", return_value=True
        ) as mock_add, patch(
            "handlers.chat_member_handlers.remove_channel_subscriber"
        ) as mock_remove:
            update = create_chat_member_update(old_status="left", new_status="member")
            await handle_new_subscriber(update)

            mock_add.assert_called_once_with(
                channel_id=123456789,
                user_id=111222333,
                username="testuser",
                first_name="Test User",
            )
            mock_remove.assert_not_called()

    @pytest.mark.asyncio
    async def test_handle_new_subscriber_channel_leave(self):
        """Тест обработки отписки пользователя от канала"""
        with patch(
            "handlers.chat_member_handlers.remove_channel_subscriber", return_value=True
        ) as mock_remove, patch(
            "handlers.chat_member_handlers.add_channel_subscriber"
        ) as mock_add:
            update = create_chat_member_update(old_status="member", new_status="left")
            await handle_new_subscriber(update)

            mock_remove.assert_called_once_with(channel_id=123456789, user_id=111222333)
            mock_add.assert_not_called()

    @pytest.mark.asyncio
    async def test_handle_new_subscriber_channel_restrict(self):
        """Тест обработки ограничения пользователя (считается подпиской)"""
        with patch(
            "handlers.chat_member_handlers.add_channel_subscriber", return_value=True
        ) as mock_add, patch(
            "handlers.chat_member_handlers.remove_channel_subscriber"
        ) as mock_remove:
            update = create_chat_member_update(
                old_status="left", new_status="restricted"
            )
            await handle_new_subscriber(update)

            mock_add.assert_called_once()
            mock_remove.assert_not_called()

    @pytest.mark.asyncio
    async def test_handle_new_subscriber_channel_unrestrict(self):
        """Тест снятия ограничений (считается отпиской)"""
        with patch(
            "handlers.chat_member_handlers.remove_channel_subscriber", return_value=True
        ) as mock_remove, patch(
            "handlers.chat_member_handlers.add_channel_subscriber"
        ) as mock_add:
            update = create_chat_member_update(
                old_status="restricted", new_status="left"
            )
            await handle_new_subscriber(update)

            mock_remove.assert_called_once()
            mock_add.assert_not_called()

    @pytest.mark.asyncio
    async def test_handle_new_subscriber_not_channel(self):
        """Тест обработки обновления не в канале (должно быть проигнорировано)"""
        with patch(
            "handlers.chat_member_handlers.add_channel_subscriber"
        ) as mock_add, patch(
            "handlers.chat_member_handlers.remove_channel_subscriber"
        ) as mock_remove:
            update = create_chat_member_update(
                old_status="left", new_status="member", chat_type="group"
            )
            await handle_new_subscriber(update)

            mock_add.assert_not_called()
            mock_remove.assert_not_called()

    @pytest.mark.asyncio
    async def test_handle_new_subscriber_kicked(self):
        """Тест исключения пользователя из канала (отписка)"""
        with patch(
            "handlers.chat_member_handlers.remove_channel_subscriber", return_value=True
        ) as mock_remove, patch(
            "handlers.chat_member_handlers.add_channel_subscriber"
        ) as mock_add:
            update = create_chat_member_update(old_status="member", new_status="kicked")
            await handle_new_subscriber(update)

            mock_remove.assert_called_once()
            mock_add.assert_not_called()

    @pytest.mark.asyncio
    async def test_handle_new_subscriber_add_existing_subscriber(self):
        """Тест повторного присоединения (уже существует)"""
        with patch(
            "handlers.chat_member_handlers.add_channel_subscriber", return_value=False
        ) as mock_add, patch(
            "handlers.chat_member_handlers.remove_channel_subscriber"
        ) as mock_remove:
            update = create_chat_member_update(old_status="left", new_status="member")
            await handle_new_subscriber(update)

            mock_add.assert_called_once()
            mock_remove.assert_not_called()

    @pytest.mark.asyncio
    async def test_handle_new_subscriber_remove_nonexistent_subscriber(self):
        """Тест отписки несуществующего пользователя"""
        with patch(
            "handlers.chat_member_handlers.remove_channel_subscriber", return_value=False
        ) as mock_remove, patch(
            "handlers.chat_member_handlers.add_channel_subscriber"
        ) as mock_add:
            update = create_chat_member_update(old_status="member", new_status="left")
            await handle_new_subscriber(update)

            mock_remove.assert_called_once()
            mock_add.assert_not_called()