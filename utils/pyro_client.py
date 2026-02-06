from pyrogram import Client
import logging
import asyncio

logger = logging.getLogger(__name__)

class PyrogramClient:
    def __init__(self, config):
        self.config = config
        self.app = Client(
            name=config.SESSION_NAME,
            api_id=config.API_ID,
            api_hash=config.API_HASH,
            phone_number=config.PHONE_NUMBER,
            no_updates=False  # Получаем обновления (реакции, сообщения)
        )
        self.is_running = False

    async def start(self):
        """Запуск Pyrogram клиента"""
        try:
            await self.app.start()
            self.is_running = True
            logger.info("✅ Pyrogram клиент запущен и авторизован")
        except Exception as e:
            logger.error(f"❌ Ошибка при запуске Pyrogram: {e}")
            raise

    async def stop(self):
        """Остановка клиента"""
        if self.is_running:
            await self.app.stop()
            self.is_running = False
            logger.info("🛑 Pyrogram клиент остановлен")

    async def send_message(self, chat_id, text: str, parse_mode=None):
        """Отправка сообщения через Pyrogram"""
        if not self.is_running:
            return False
        try:
            await self.app.send_message(chat_id, text, parse_mode=parse_mode)
            logger.info(f"📩 Сообщение отправлено: {chat_id}")
            return True
        except Exception as e:
            logger.error(f"❌ Не удалось отправить сообщение {chat_id}: {e}")
            return False

    async def get_message_reactions(self, chat_id, message_id):
        """Получение реакций на пост (только если доступны)"""
        if not self.is_running:
            return None
        try:
            message = await self.app.get_messages(chat_id, message_id)
            return message.reactions
        except Exception as e:
            logger.error(f"❌ Ошибка получения реакций: {e}")
            return None

    async def export(self):
        """Возвращает экземпляр клиента (для кастомных операций)"""
        return self.app

# Глобальный экземпляр
pyro_client = None

def setup_pyrogram(config) -> PyrogramClient:
    global pyro_client
    pyro_client = PyrogramClient(config)
    return pyro_client