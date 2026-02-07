from pyrogram import Client
from pyrogram.raw.types import UpdateMessageReactions
import logging


class PyrogramClient:
    def __init__(self, config):
        self.config = config
        self.app: Client = Client(
            name=config.SESSION_NAME,
            api_id=config.API_ID,
            api_hash=config.API_HASH,
            phone_number=config.PHONE_NUMBER,
            no_updates=False
        )
        self.is_running = False

        # Подписываемся на raw-обновления
        self.app.add_handler(self.on_raw_update, group=0)

    async def start(self):
        """Запуск Pyrogram клиента"""
        if self.is_running:
            logging.warning("Pyrogram клиент уже запущен.")
            return
        try:
            await self.app.start()
            self.is_running = True
            logging.info("✅ Pyrogram клиент запущен и авторизован")
        except Exception as e:
            logging.error(f"❌ Ошибка при запуске Pyrogram: {e}")
            raise

    async def stop(self):
        """Остановка клиента"""
        if self.is_running:
            await self.app.stop()
            self.is_running = False
            logging.info("🛑 Pyrogram клиент остановлен")

    async def send_message(self, chat_id, text: str, parse_mode=None):
        """Отправка сообщения через Pyrogram"""
        if not self.is_running:
            logging.error("❌ Pyrogram клиент не запущен. Невозможно отправить сообщение.")
            return False
        try:
            await self.app.send_message(chat_id, text, parse_mode=parse_mode)
            logging.info(f"📩 Сообщение отправлено: {chat_id}")
            return True
        except Exception as e:
            logging.error(f"❌ Не удалось отправить сообщение {chat_id}: {e}")
            return False

    async def get_message_reactions(self, chat_id, message_id):
        """Получение реакций на пост (только если доступны)"""
        if not self.is_running:
            return None
        try:
            message = await self.app.get_messages(chat_id, message_id)
            return message.reactions
        except Exception as e:
            logging.error(f"❌ Ошибка получения реакций: {e}")
            return None

    async def on_raw_update(self, client: Client, update, users, chats):
        """
        Обработчик 'сырых' обновлений — ловим изменения реакций.
        """
        logging.debug(f"🔍 Обработка raw_update: {type(update)}")
        try:
            if isinstance(update, UpdateMessageReactions):
                chat_id = int(f"-100{update.peer.channel_id}") if hasattr(update.peer, 'channel_id') else update.peer.user_id
                message_id = update.msg_id
                reactions = update.reactions

                reacted_users = []
                for r in reactions.results:
                    if hasattr(r, 'peer_ids') and r.peer_ids:
                        reacted_users.extend([peer_id.user_id for peer_id in r.peer_ids])

                logging.info(
                    f"🔄 Обновление реакций: чат={chat_id}, сообщение={message_id}, "
                    f"реакции={len(reacted_users)} пользователей"
                )
                for user_id in reacted_users:
                    logging.info(f"✅ Пользователь {user_id} проявил активность в сообщении {message_id}")

        except Exception as e:
            logging.error(f"❌ Ошибка в обработчике raw_update (реакции): {e}")

    async def export(self):
        """Возвращает внутренний экземпляр Client (если нужно)"""
        return self.app


# Глобальный экземпляр
_instance: PyrogramClient | None = None


def setup_pyrogram(config) -> PyrogramClient:
    """
    Возвращает единственный экземпляр PyrogramClient.
    Создаёт новый только если ещё не создан.
    """
    global _instance
    if _instance is None:
        _instance = PyrogramClient(config)
    return _instance


def get_pyrogram_client() -> PyrogramClient:
    """
    Получить готовый запущенный клиент (удобно для использования в других модулях).
    """
    if _instance is None:
        raise RuntimeError("PyrogramClient ещё не инициализирован. Вызовите setup_pyrogram(config) сначала.")
    return _instance