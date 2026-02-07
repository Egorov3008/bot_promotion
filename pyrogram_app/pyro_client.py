from pyrogram import Client
from pyrogram.raw.types import UpdateMessageReactions
import logging


class PyrogramClient:
    def __init__(self, config):
        self.config = config
        self.app = Client(
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
        try:
            # Фильтруем только обновления реакций
            if isinstance(update, UpdateMessageReactions):
                chat_id = int(f"-100{update.peer.channel_id}") if hasattr(update.peer, 'channel_id') else update.peer.user_id
                message_id = update.msg_id
                reactions = update.reactions

                # Парсим список пользователей, поставивших реакции
                reacted_users = []

                for r in reactions.results:
                    # r.peer_ids — список ID пользователей, поставивших эту реакцию
                    if hasattr(r, 'peer_ids') and r.peer_ids:
                        reacted_users.extend([peer_id.user_id for peer_id in r.peer_ids])
                    elif hasattr(r, 'peer_emoticon'):
                        # Это может быть анонимная реакция или кастомная
                        pass

                # Логируем событие
                logging.info(
                    f"🔄 Обновление реакций: "
                    f"чат={chat_id}, сообщение={message_id}, "
                    f"реакции={len(reacted_users)} пользователей"
                )

                # Здесь можно вызвать вашу логику: сохранить активность
                for user_id in reacted_users:
                    logging.info(f"✅ Пользователь {user_id} проявил активность в сообщении {message_id}")

        except Exception as e:
            logging.error(f"❌ Ошибка в обработчике raw_update (реакции): {e}")

    async def export(self):
        """Возвращает экземпляр клиента (для кастомных операций)"""
        return self.app


# Глобальный экземпляр
pyro_client = None


def setup_pyrogram(config) -> PyrogramClient:
    global pyro_client
    pyro_client = PyrogramClient(config)
    return pyro_client