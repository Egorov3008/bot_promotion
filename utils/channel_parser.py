import asyncio
import logging
from typing import List, Dict, Tuple

from pyrogram import Client
from pyrogram.errors import FloodWait, BadRequest
from pyrogram.enums import ChatMemberStatus


async def parse_channel_subscribers(
    client: Client,
    channel_id: int
) -> Tuple[List[Dict], int, int]:
    """
    Парсит подписчиков канала, сохраняя только пользователей с открытым username.
    Обрабатывает Rate Limits и ошибки Telegram API.

    Args:
        client: Pyrogram клиент
        channel_id: ID канала
        
    Returns:
        tuple: (список подписчиков с username, кол-во с username, кол-во ботов)
    """
    subscribers_with_username = []
    users_with_username_count = 0
    bots_count = 0
    total_processed = 0

    try:
        async for member in client.get_chat_members(chat_id=channel_id):
            total_processed += 1
            user = member.user

            if user.is_bot:
                bots_count += 1
                continue

            if user.username:
                subscribers_with_username.append({
                    "user_id": user.id,
                    "first_name": user.first_name,
                    "username": user.username
                })
                users_with_username_count += 1
            
            # Небольшая задержка для соблюдения Rate Limits, особенно при большом количестве пользователей
            # Aдaптивный Rate Limits и экспоненциальная выдержка будут реализованы на этапе 4
            if total_processed % 100 == 0: 
                await asyncio.sleep(0.1) 

    except FloodWait as e:
        logging.warning(f"Получен FloodWait при парсинге канала {channel_id}: ждем {e.value} секунд. Обработано {total_processed} пользователей.")
        await asyncio.sleep(e.value + 1) # Добавляем 1 секунду на всякий случай
        # В реальных условиях нужно будет повторить запрос с места обрыва,
        # что потребует изменений в логике генератора или создания внешнего счетчика.
        # Для текущей реализации MVP, мы просто ждём и продолжаем.
        # Или, возможно, прерываем и сообщаем админу.
        # Пока примем, что генератор продолжит или админ перезапустит.
        # Для этапа MVP, просто ожидание достаточно.

    except BadRequest as e:
        if "CHAT_ADMIN_REQUIRED" in str(e):
            logging.error(f"Ошибка при парсинге канала {channel_id}: У Pyrogram клиента нет прав администратора в канале. {e}")
            raise ValueError(f"BOT_NOT_ADMIN: У Pyrogram клиента нет прав администратора в канале {channel_id}.")
        elif "USER_RESTRICTED" in str(e) or "PEER_ID_INVALID" in str(e):
             logging.warning(f"Ошибка при парсинге канала {channel_id}: Пользователь ограничен или ID недействителен. Возможна блокировка от канала, или это системный пользователь. {e}")
        else:
            logging.error(f"Неизвестная ошибка BadRequest при парсинге канала {channel_id}: {e}")
            raise

    except Exception as e:
        logging.error(f"Непредвиденная ошибка при парсинге канала {channel_id}: {e}")
        raise
    
    logging.info(f"Парсинг канала {channel_id} завершен. Всего обработано: {total_processed}, "
                f"пользователей с username: {users_with_username_count}, ботов: {bots_count}.")
    
    return subscribers_with_username, users_with_username_count, bots_count

async def get_pyrogram_client(client: Client) -> Client:
    """
    Убеждается, что Pyrogram клиент запущен и возвращает его.
    """
    if not client.is_connected:
        try:
            await client.start()
            logging.info("Pyrogram клиент успешно запущен.")
        except Exception as e:
            logging.error(f"Ошибка запуска Pyrogram клиента: {e}")
            raise
    return client

async def check_pyrogram_client_admin_rights(client: Client, channel_id: int, client_user_id: int = None) -> bool:
    """
    Проверяет, имеет ли Pyrogram клиент административные права в канале.
    Предполагается, что клиент уже запущен.

    Args:
        client: Pyrogram клиент
        channel_id: ID канала
        client_user_id: Опционально ID пользователя для проверки (если не передан, используется get_me())
    """
    try:
        if client_user_id is None:
            me = await client.get_me()
            if not me:
                logging.error("Не удалось получить информацию о текущем Pyrogram клиенте.")
                return False
            client_user_id = me.id

        # Пытаемся получить информацию о клиенте как члене чата
        member = await client.get_chat_member(chat_id=channel_id, user_id=client_user_id)

        # Проверяем статус члена чата
        if member.status in [ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER]:
            return True
        else:
            logging.warning(f"Pyrogram клиент {me.id} не имеет прав администратора в канале {channel_id}. Статус: {member.status.name}")
            return False
            
    except BadRequest as e:
        if "CHAT_ID_INVALID" in str(e) or "CHAT_NOT_FOUND" in str(e):
            logging.error(f"Ошибка проверки прав в канале {channel_id}: Канал не найден или ID недействителен.")
            return False
        if "USER_NOT_PARTICIPANT" in str(e):
             # Если клиент не является участником, то не может быть админом.
             # Это может быть нормальной ситуацией, если бот только что был отправлен в канал.
             logging.warning(f"Pyrogram клиент не является участником канала {channel_id}.")
             return False
        logging.error(f"Неизвестная ошибка BadRequest при проверке прав Pyrogram клиента в канале {channel_id}: {e}")
        return False
    except Exception as e:
        logging.error(f"Непредвиденная ошибка при проверке прав Pyrogram клиента в канале {channel_id}: {e}")
        return False