from pyrogram import Client
from pyrogram.handlers import RawUpdateHandler
from pyrogram.raw.types import UpdateMessageReactions, PeerChannel
from pyrogram.raw.functions.messages import GetMessageReactionsList
import logging

from database.database import update_last_activity


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
        self.app.add_handler(RawUpdateHandler(self.on_raw_update), group=0)

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
        При получении UpdateMessageReactions запрашиваем список
        реагировавших через GetMessageReactionsList (доступно админам канала).
        """
        update_type = type(update).__name__

        if not isinstance(update, UpdateMessageReactions):
            return

        try:
            peer = update.peer
            message_id = update.msg_id

            if not hasattr(peer, 'channel_id'):
                logging.debug(f"Реакция не в канале, пропускаю: {peer}")
                return

            channel_id = peer.channel_id
            chat_id = int(f"-100{channel_id}")
            logging.info(f"🎯 UpdateMessageReactions: chat_id={chat_id}, msg_id={message_id}")

            # Запрашиваем полный список пользователей через MTProto API
            result = await client.invoke(
                GetMessageReactionsList(
                    peer=PeerChannel(channel_id=channel_id),
                    id=message_id,
                    limit=100,
                )
            )

            logging.info(f"   GetMessageReactionsList: получено {len(result.reactions)} реакций")

            for reaction in result.reactions:
                user_id = reaction.peer_id.user_id if hasattr(reaction.peer_id, 'user_id') else None
                if not user_id:
                    continue

                # Ищем данные пользователя в ответе
                user_data = next((u for u in result.users if u.id == user_id), None)
                username = getattr(user_data, 'username', None) if user_data else None
                first_name = getattr(user_data, 'first_name', None) if user_data else None
                last_name = getattr(user_data, 'last_name', None) if user_data else None
                full_name = f"{first_name or ''} {last_name or ''}".strip() or None

                await update_last_activity(
                    channel_id=chat_id,
                    user_id=user_id,
                    username=username,
                    first_name=first_name,
                    full_name=full_name,
                )
                logging.info(f"✅ Реакция сохранена: user_id={user_id}, username={username}, канал={chat_id}")

            if not result.reactions:
                logging.info(f"   Список реакций пуст для сообщения {message_id}")

        except Exception as e:
            logging.error(f"❌ Ошибка обработки реакций: {e}", exc_info=True)

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