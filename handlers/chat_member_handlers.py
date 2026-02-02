import logging
from aiogram import Router, types
from database.database import add_channel_subscriber, remove_channel_subscriber

router = Router()

@router.chat_member()
async def handle_new_subscriber(update: types.ChatMemberUpdated):
    """
    Обрабатывает изменения статуса участника канала.
    Отслеживает как подписки, так и отписки пользователей.
    """
    # Только для каналов
    if update.chat.type != "channel":
        return

    old_status = update.old_chat_member.status
    new_status = update.new_chat_member.status
    user = update.new_chat_member.user
    channel_id = update.chat.id

    # Пользователь присоединился, если статус изменился с 'left'/'kicked' на 'member' или 'restricted'
    is_joining = old_status in ("left", "kicked") and new_status in ("member", "restricted")
    
    # Пользователь отписался, если статус изменился с 'member'/'restricted' на 'left'/'kicked'
    is_leaving = old_status in ("member", "restricted") and new_status in ("left", "kicked")

    if is_joining:
        # Сохраняем как подписчика
        success = await add_channel_subscriber(
            channel_id=channel_id,
            user_id=user.id,
            username=user.username,
            first_name=user.first_name,
            full_name=user.full_name,
        )
        if success:
            logging.info(f"Подписчик добавлен: {user.id} в канале {channel_id}")
        else:
            logging.info(f"Подписчик уже существует: {user.id} в канале {channel_id}")
    
    elif is_leaving:
        # Отмечаем как отписавшегося
        success = await remove_channel_subscriber(
            channel_id=channel_id,
            user_id=user.id
        )
        if success:
            logging.info(f"Подписчик отписан: {user.id} в канале {channel_id}")
        else:
            logging.info(f"Не удалось отписать пользователя: {user.id} в канале {channel_id} (возможно, уже отписан)")


def chat_member_handlers(dp):
    """Регистрация базовых хендлеров"""
    dp.include_router(router)