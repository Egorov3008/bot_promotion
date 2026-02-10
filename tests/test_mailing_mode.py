"""
Тесты для модуля pyrogram_app/mailing_mode.py

Покрывают:
- Инициализацию MailingMode
- Отправку сообщения одному пользователю
- Массовую отправку сообщений
- Персонализированную отправку сообщений
- Оценку времени доставки
- Остановку рассылки
"""

import pytest
from unittest.mock import AsyncMock, MagicMock

from pyrogram_app.mailing_mode import MailingMode
from pyrogram.errors import UserBlocked


class TestMailingMode:
    """Тесты для класса MailingMode"""

    @pytest.fixture
    def mailing_mode(self, mock_pyrogram_client):
        """Фикстура для экземпляра MailingMode"""
        return MailingMode(mock_pyrogram_client)

    def test_init(self, mock_pyrogram_client, mailing_mode):
        """Тест инициализации MailingMode"""
        assert mailing_mode.client == mock_pyrogram_client
        assert mailing_mode.delay_min == 1.0
        assert mailing_mode.delay_max == 3.0
        assert mailing_mode._stop_event is not None

    @pytest.mark.asyncio
    async def test_send_message_to_user_success(self, mailing_mode):
        """Тест успешной отправки сообщения одному пользователю"""
        mailing_mode.client.send_message = AsyncMock(return_value=True)
        
        success, message = await mailing_mode.send_message_to_user(123, "Test message")
        
        assert success is True
        assert message == "Успешно отправлено"
        mailing_mode.client.send_message.assert_awaited_once_with(
            chat_id=123,
            text="Test message",
            parse_mode=None,
            disable_web_page_preview=False
        )

    @pytest.mark.asyncio
    async def test_send_message_to_user_blocked(self, mailing_mode):
        """Тест отправки сообщения одному пользователю, если бот заблокирован"""
        mailing_mode.client.send_message = AsyncMock(side_effect=Exception("bot was blocked"))
        
        success, message = await mailing_mode.send_message_to_user(123, "Test message")
        
        assert success is False
        assert message == "Пользователь заблокировал бота"

    @pytest.mark.asyncio
    async def test_send_message_to_user_flood_wait(self, mailing_mode):
        """Тест отправки сообщения одному пользователю при Flood Wait"""
        mailing_mode.client.send_message = AsyncMock(side_effect=Exception("FloodWait: A wait of 123 seconds is required"))
        
        success, message = await mailing_mode.send_message_to_user(123, "Test message")
        
        assert success is False
        assert message == "Превышен лимит запросов (Flood Wait)"

    @pytest.mark.asyncio
    async def test_send_message_to_user_other_error(self, mailing_mode):
        """Тест отправки сообщения одному пользователю при другой ошибке"""
        mailing_mode.client.send_message = AsyncMock(side_effect=Exception("Some other error"))
        
        success, message = await mailing_mode.send_message_to_user(123, "Test message")
        
        assert success is False
        assert message == "Неизвестная ошибка: Some other error"

    @pytest.mark.asyncio
    async def test_send_bulk_messages_success(self, mailing_mode, monkeypatch):
        """Тест успешной массовой рассылки"""
        user_ids = [1, 2, 3]
        mailing_mode.client.send_message = AsyncMock(return_value=True)
        mock_sleep = AsyncMock()
        monkeypatch.setattr("asyncio.sleep", mock_sleep)
        monkeypatch.setattr("random.uniform", MagicMock(return_value=1.5))
        monkeypatch.setattr("random.shuffle", MagicMock())
        
        stats = await mailing_mode.send_bulk_messages(user_ids, "Bulk message")
        
        assert stats.total_sent == 3
        assert stats.successful == 3
        assert stats.failed == 0
        assert mailing_mode.client.send_message.call_count == 3
        assert mock_sleep.call_count >= 3 # 3 на задержки между сообщениями

    @pytest.mark.asyncio
    async def test_send_bulk_messages_with_failures(self, mailing_mode, monkeypatch):
        """Тест массовой рассылки с ошибками"""
        user_ids = [1, 2, 3]
        mailing_mode.client.send_message.side_effect = [
            AsyncMock(return_value=True)(),
            UserBlocked(),
            Exception("Some other error"),
        ]

        mock_sleep = AsyncMock()
        monkeypatch.setattr("asyncio.sleep", mock_sleep)
        monkeypatch.setattr("random.uniform", MagicMock(return_value=1.5))
        monkeypatch.setattr("random.shuffle", MagicMock())

        stats = await mailing_mode.send_bulk_messages(user_ids, "Bulk message")

        assert stats.total_sent == 3
        assert stats.successful == 1
        assert stats.failed == 2
        assert stats.blocked == 1
        assert stats.other_errors == 1
        assert mailing_mode.client.send_message.call_count == 3

    @pytest.mark.asyncio
    async def test_send_bulk_messages_stop_event(self, mailing_mode, monkeypatch):
        """Тест остановки массовой рассылки по событию"""
        user_ids = [1, 2, 3, 4, 5]
        mailing_mode.client.send_message.side_effect = [AsyncMock(return_value=True)() for _ in user_ids]

        mock_sleep = AsyncMock()
        monkeypatch.setattr("asyncio.sleep", mock_sleep)
        monkeypatch.setattr("random.uniform", MagicMock(return_value=1.5))
        monkeypatch.setattr("random.shuffle", MagicMock())


        # Устанавливаем _stop_event после первой отправки
        initial_call_count = [0] # Используем список для изменения вложенной переменной
        def set_stop_event_side_effect(*args, **kwargs):
            initial_call_count[0] += 1
            if initial_call_count[0] == 1:
                mailing_mode._stop_event.set()
            return AsyncMock(return_value=True)()

        mailing_mode.client.send_message.side_effect = set_stop_event_side_effect

        stats = await mailing_mode.send_bulk_messages(user_ids, "Test")

        assert stats.total_sent == 1 # Отправлено только одно сообщение
        assert stats.successful == 1
        assert stats.failed == 0
        assert initial_call_count[0] == 1 # Проверяем количество фактических вызовов

    @pytest.mark.asyncio
    async def test_send_personalized_messages_success(self, mailing_mode, monkeypatch):
        """Тест успешной персонализированной рассылки"""
        user_messages = [
            {"user_id": 1, "text": "Msg 1"},
            {"user_id": 2, "text": "Msg 2"}
        ]
        mailing_mode.client.send_message = AsyncMock(return_value=True)
        mock_sleep = AsyncMock()
        monkeypatch.setattr("asyncio.sleep", mock_sleep)
        monkeypatch.setattr("random.uniform", MagicMock(return_value=1.5))
        monkeypatch.setattr("random.shuffle", MagicMock())

        stats = await mailing_mode.send_personalized_messages(user_messages)
        
        assert stats.total_sent == 2
        assert stats.successful == 2
        assert mailing_mode.client.send_message.call_count == 2

    @pytest.mark.asyncio
    async def test_estimate_delivery_time(self, mailing_mode):
        """Тест оценки времени доставки"""
        # Без дополнительных задержек
        estimate = await mailing_mode.estimate_delivery_time(user_count=10, delay_range=(1, 1))
        assert estimate == 10 * 1.0

        # С дополнительными задержками (каждые 50 сообщений)
        estimate = await mailing_mode.estimate_delivery_time(user_count=100, delay_range=(1, 1))
        expected_base_time = 100 * 1.0
        expected_extra_time = (100 // 50) * 15 # Две доп. задержки по 15 секунд
        assert estimate == expected_base_time + expected_extra_time

    def test_stop(self, mailing_mode):
        """Тест остановки рассылки"""
        mailing_mode.stop()
        assert mailing_mode._stop_event.is_set() is True
