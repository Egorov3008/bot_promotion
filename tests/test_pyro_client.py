"""
Тесты для модуля pyrogram_app/pyro_client.py

Покрывают:
- Инициализацию PyrogramClient
- Запуск и остановку клиента
- Отправку сообщений
- Получение реакций
- Обработку raw update
- Singleton паттерн (setup_pyrogram, get_pyrogram_client)
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from pyrogram.raw.types import UpdateMessageReactions
from pyrogram import Client

from pyrogram_app.pyro_client import (
    PyrogramClient,
    setup_pyrogram,
    get_pyrogram_client,
    _instance
)


class TestPyrogramClient:
    """Тесты класса PyrogramClient"""
    
    def test_pyrogram_client_initialization(self, mock_config):
        """Тест инициализации PyrogramClient"""
        with patch('pyrogram_app.pyro_client.Client') as mock_client_class:
            mock_client_instance = MagicMock()
            mock_client_class.return_value = mock_client_instance
            
            client = PyrogramClient(mock_config)
            
            assert client.config == mock_config
            assert client.app == mock_client_instance
            assert client.is_running is False
            mock_client_class.assert_called_once_with(
                name=mock_config.SESSION_NAME,
                api_id=mock_config.API_ID,
                api_hash=mock_config.API_HASH,
                phone_number=mock_config.PHONE_NUMBER,
                no_updates=False
            )
            mock_client_instance.add_handler.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_start_success(self, mock_config):
        """Тест успешного запуска клиента"""
        with patch('pyrogram_app.pyro_client.Client') as mock_client_class:
            mock_client_instance = MagicMock()
            mock_client_instance.start = AsyncMock()
            mock_client_class.return_value = mock_client_instance
            
            client = PyrogramClient(mock_config)
            await client.start()
            
            assert client.is_running is True
            mock_client_instance.start.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_start_already_running(self, mock_config):
        """Тест запуска уже запущенного клиента"""
        with patch('pyrogram_app.pyro_client.Client') as mock_client_class:
            mock_client_instance = MagicMock()
            mock_client_instance.start = AsyncMock()
            mock_client_class.return_value = mock_client_instance
            
            client = PyrogramClient(mock_config)
            client.is_running = True
            
            await client.start()
            
            # start не должен вызываться второй раз
            mock_client_instance.start.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_start_exception(self, mock_config):
        """Тест обработки исключения при запуске"""
        with patch('pyrogram_app.pyro_client.Client') as mock_client_class:
            mock_client_instance = MagicMock()
            mock_client_instance.start = AsyncMock(side_effect=Exception("Connection error"))
            mock_client_class.return_value = mock_client_instance
            
            client = PyrogramClient(mock_config)
            
            with pytest.raises(Exception, match="Connection error"):
                await client.start()
            
            assert client.is_running is False
    
    @pytest.mark.asyncio
    async def test_stop_success(self, mock_config):
        """Тест успешной остановки клиента"""
        with patch('pyrogram_app.pyro_client.Client') as mock_client_class:
            mock_client_instance = MagicMock()
            mock_client_instance.stop = AsyncMock()
            mock_client_class.return_value = mock_client_instance
            
            client = PyrogramClient(mock_config)
            client.is_running = True
            
            await client.stop()
            
            assert client.is_running is False
            mock_client_instance.stop.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_stop_when_not_running(self, mock_config):
        """Тест остановки незапущенного клиента"""
        with patch('pyrogram_app.pyro_client.Client') as mock_client_class:
            mock_client_instance = MagicMock()
            mock_client_instance.stop = AsyncMock()
            mock_client_class.return_value = mock_client_instance
            
            client = PyrogramClient(mock_config)
            client.is_running = False
            
            await client.stop()
            
            # stop не должен вызываться
            mock_client_instance.stop.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_send_message_success(self, mock_config):
        """Тест успешной отправки сообщения"""
        with patch('pyrogram_app.pyro_client.Client') as mock_client_class:
            mock_client_instance = MagicMock()
            mock_client_instance.send_message = AsyncMock()
            mock_client_class.return_value = mock_client_instance
            
            client = PyrogramClient(mock_config)
            client.is_running = True
            
            result = await client.send_message(
                chat_id=123456789,
                text="Test message",
                parse_mode="HTML"
            )
            
            assert result is True
            mock_client_instance.send_message.assert_called_once_with(
                123456789,
                "Test message",
                parse_mode="HTML"
            )
    
    @pytest.mark.asyncio
    async def test_send_message_not_running(self, mock_config):
        """Тест отправки сообщения при незапущенном клиенте"""
        with patch('pyrogram_app.pyro_client.Client') as mock_client_class:
            mock_client_instance = MagicMock()
            mock_client_class.return_value = mock_client_instance
            
            client = PyrogramClient(mock_config)
            client.is_running = False
            
            result = await client.send_message(123456789, "Test message")
            
            assert result is False
            mock_client_instance.send_message.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_send_message_exception(self, mock_config):
        """Тест обработки исключения при отправке сообщения"""
        with patch('pyrogram_app.pyro_client.Client') as mock_client_class:
            mock_client_instance = MagicMock()
            mock_client_instance.send_message = AsyncMock(
                side_effect=Exception("Send failed")
            )
            mock_client_class.return_value = mock_client_instance
            
            client = PyrogramClient(mock_config)
            client.is_running = True
            
            result = await client.send_message(123456789, "Test message")
            
            assert result is False
    
    @pytest.mark.asyncio
    async def test_get_message_reactions_success(self, mock_config, mock_message_with_reactions):
        """Тест успешного получения реакций"""
        with patch('pyrogram_app.pyro_client.Client') as mock_client_class:
            mock_client_instance = MagicMock()
            mock_client_instance.get_messages = AsyncMock(return_value=mock_message_with_reactions)
            mock_client_class.return_value = mock_client_instance
            
            client = PyrogramClient(mock_config)
            client.is_running = True
            
            reactions = await client.get_message_reactions(chat_id=-1001234567890, message_id=1)
            
            assert reactions is not None
            assert reactions == mock_message_with_reactions.reactions
            mock_client_instance.get_messages.assert_called_once_with(-1001234567890, 1)
    
    @pytest.mark.asyncio
    async def test_get_message_reactions_not_running(self, mock_config):
        """Тест получения реакций при незапущенном клиенте"""
        with patch('pyrogram_app.pyro_client.Client') as mock_client_class:
            mock_client_instance = MagicMock()
            mock_client_class.return_value = mock_client_instance
            
            client = PyrogramClient(mock_config)
            client.is_running = False
            
            reactions = await client.get_message_reactions(-1001234567890, 1)
            
            assert reactions is None
            mock_client_instance.get_messages.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_get_message_reactions_exception(self, mock_config):
        """Тест обработки исключения при получении реакций"""
        with patch('pyrogram_app.pyro_client.Client') as mock_client_class:
            mock_client_instance = MagicMock()
            mock_client_instance.get_messages = AsyncMock(side_effect=Exception("Get failed"))
            mock_client_class.return_value = mock_client_instance
            
            client = PyrogramClient(mock_config)
            client.is_running = True
            
            reactions = await client.get_message_reactions(-1001234567890, 1)
            
            assert reactions is None
    
    @pytest.mark.asyncio
    async def test_on_raw_update_message_reactions(self, mock_config, mock_update_message_reactions):
        """Тест обработки raw update с реакциями"""
        with patch('pyrogram_app.pyro_client.Client') as mock_client_class:
            mock_client_instance = MagicMock()
            mock_client_class.return_value = mock_client_instance
            
            client = PyrogramClient(mock_config)
            
            await client.on_raw_update(
                client=mock_client_instance,
                update=mock_update_message_reactions,
                users={},
                chats={}
            )
            
            # Проверяем, что обработчик не вызывает исключений
            # Реальная проверка логов не требуется для модульных тестов
    
    @pytest.mark.asyncio
    async def test_on_raw_update_not_message_reactions(self, mock_config):
        """Тест обработки raw update другого типа"""
        with patch('pyrogram_app.pyro_client.Client') as mock_client_class:
            mock_client_instance = MagicMock()
            mock_client_class.return_value = mock_client_instance
            
            client = PyrogramClient(mock_config)
            
            # Создаем mock обновление другого типа
            mock_update = MagicMock()
            mock_update.__class__.__name__ = "UpdateNewMessage"
            
            # Не должно вызывать исключений
            await client.on_raw_update(
                client=mock_client_instance,
                update=mock_update,
                users={},
                chats={}
            )
    
    @pytest.mark.asyncio
    async def test_on_raw_update_exception(self, mock_config):
        """Тест обработки исключения в on_raw_update"""
        with patch('pyrogram_app.pyro_client.Client') as mock_client_class:
            mock_client_instance = MagicMock()
            mock_client_class.return_value = mock_client_instance
            
            client = PyrogramClient(mock_config)
            
            # Создаем update, который вызовет исключение
            mock_update = MagicMock(spec=UpdateMessageReactions)
            mock_update.peer = None  # Это вызовет AttributeError
            
            # Не должно вызывать исключений
            await client.on_raw_update(
                client=mock_client_instance,
                update=mock_update,
                users={},
                chats={}
            )
    
    @pytest.mark.asyncio
    async def test_export(self, mock_config):
        """Тест метода export"""
        with patch('pyrogram_app.pyro_client.Client') as mock_client_class:
            mock_client_instance = MagicMock()
            mock_client_class.return_value = mock_client_instance
            
            client = PyrogramClient(mock_config)
            exported = await client.export()
            
            assert exported == mock_client_instance


class TestPyrogramClientSingleton:
    """Тесты singleton паттерна для PyrogramClient"""
    
    def test_setup_pyrogram_creates_instance(self, mock_config):
        """Тест создания экземпляра через setup_pyrogram"""
        with patch('pyrogram_app.pyro_client._instance', None):
            with patch('pyrogram_app.pyro_client.PyrogramClient') as mock_pyro_client_class:
                mock_instance = MagicMock()
                mock_pyro_client_class.return_value = mock_instance
                
                result = setup_pyrogram(mock_config)
                
                assert result == mock_instance
                mock_pyro_client_class.assert_called_once_with(mock_config)
    
    def test_setup_pyrogram_returns_existing_instance(self, mock_config):
        """Тест возврата существующего экземпляра"""
        with patch('pyrogram_app.pyro_client._instance', MagicMock()):
            with patch('pyrogram_app.pyro_client.PyrogramClient') as mock_pyro_client_class:
                result = setup_pyrogram(mock_config)
                
                # Не должен создавать новый экземпляр
                mock_pyro_client_class.assert_not_called()
    
    def test_get_pyrogram_client_success(self):
        """Тест получения существующего клиента"""
        mock_instance = MagicMock()
        with patch('pyrogram_app.pyro_client._instance', mock_instance):
            result = get_pyrogram_client()
            
            assert result == mock_instance
    
    def test_get_pyrogram_client_not_initialized(self):
        """Тест получения клиента до инициализации"""
        with patch('pyrogram_app.pyro_client._instance', None):
            with pytest.raises(RuntimeError, match="PyrogramClient ещё не инициализирован"):
                get_pyrogram_client()
