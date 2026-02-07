import logging

from aiogram import Router, types, F
from aiogram.types import MessageReactionUpdated

from database.database import add_channel_subscriber, remove_channel_subscriber, update_last_activity, \
    get_channel_for_discussion_group

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


@router.message(F.chat.type.in_({"supergroup", "group"}))  # Группа обсуждения — supergroup
async def handle_comment(message: types.Message):
    """
    Обрабатывает комментарии в группе обсуждения канала.
    Если группа привязана к каналу, считаем пользователя активным.
    """
    # Проверяем, что это группа обсуждений (есть linked chat)
    if not message.is_topic_message and not message.reply_to_message:
        return  # Не реакция на пост — возможно, просто сообщение в чате

    user = message.from_user
    discussion_group_id = message.chat.id
    channel = await get_channel_for_discussion_group(discussion_group_id)
    if not discussion_group_id:
        logging.info(f"Группа {discussion_group_id} не привязана к каналу")
        return  # Не привязана к каналу
    # Добавляем пользователя как подписчика (если ещё не был)
    # Это нужно, потому что он может не быть в ChannelSubscriber
    await update_last_activity(channel_id=channel.channel_id,
                               user_id=user.id,
                               username=user.username,
                               first_name=user.first_name,
                               full_name=user.full_name)
    logging.debug(f"Активность пользователя {user.id} в группе обсуждений {channel.channel_id}")


@router.message
async def handle_reaction(update: MessageReactionUpdated):
    """
    Обработка изменений реакций (Bot API 7.0+).
    Требуется aiogram 3.x и включённые реакции в allowed_updates.
    """
    # Проверка: реакция в канале
    logging.info(f"Обновление реакции: {update}")
    if update.chat.type != "channel":
        return

    channel_id = update.chat.id
    user = update.user or update.actor_chat  # actor_chat для анонимных админов
    if not user:
        return

    # Если были старые реакции — удаляем их из статистики?
    # Или логируем каждое изменение?
    for reaction in update.new_reaction:
        logging.info(f"Реакция: {user.id} → {reaction.emoji} на пост {update.message_id}")


def chat_member_handlers(dp):
    """Регистрация базовых хендлеров"""
    dp.include_router(router)
