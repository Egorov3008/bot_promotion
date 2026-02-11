"""
Диалоги мастера создания розыгрыша на базе aiogram-dialog.

Логика по шагам соответствует FSM CreateGiveawayStates из handlers/giveaway_handlers.py:
- ввод заголовка и описания;
- ввод сообщения для победителей (message_winner);
- загрузка/пропуск медиа;
- выбор количества призовых мест;
- выбор канала;
- ввод даты и времени окончания;
- подтверждение и создание записи в БД + поста в канале.

Для хранения промежуточных данных используется dialog_data DialogManager.
"""

import logging
from typing import Any, Dict, List

from aiogram.types import Message, CallbackQuery

from aiogram_dialog import Dialog, DialogManager, Window
from aiogram_dialog.widgets.input import MessageInput
from aiogram_dialog.widgets.kbd import Button, Row, Select
from aiogram_dialog.widgets.text import Const, Format

from states.admin_states import CreateGiveawayStates
from texts.messages import MESSAGES, GIVEAWAY_POST_TEMPLATE, BUTTONS
from utils.datetime_utils import parse_datetime, format_datetime, is_future_datetime
from utils.scheduler import schedule_giveaway_finish
from utils.keyboards import get_participate_keyboard
from database.database import get_all_channels, create_giveaway, update_giveaway_message_id, delete_giveaway


async def on_title(message: Message, widget: MessageInput, manager: DialogManager) -> None:
    """Шаг: заголовок розыгрыша."""
    title = (message.html_text or message.text or "").strip()
    if len(title) > 255:
        await message.answer(MESSAGES["title_too_long"])
        return
    manager.dialog_data["title"] = title
    await manager.next()


async def on_description(message: Message, widget: MessageInput, manager: DialogManager) -> None:
    """Шаг: описание розыгрыша."""
    description = (message.html_text or message.text or "").strip()
    if len(description) > 4000:
        await message.answer(MESSAGES["description_too_long"])
        return
    manager.dialog_data["description"] = description
    await manager.next()


async def on_message_winner(message: Message, widget: MessageInput, manager: DialogManager) -> None:
    """Шаг: текст сообщения для победителей."""
    text = (message.html_text or message.text or "").strip()
    if len(text) > 4000:
        await message.answer(MESSAGES["message_winners_too_long"])
        return
    manager.dialog_data["message_winner"] = text
    await manager.next()


async def on_media(message: Message, widget: MessageInput, manager: DialogManager) -> None:
    """Шаг: медиа (опционально)."""
    media_data = None

    if message.photo:
        media_data = {"type": "photo", "file_id": message.photo[-1].file_id}
    elif message.video:
        media_data = {"type": "video", "file_id": message.video.file_id}
    elif message.animation:
        media_data = {"type": "animation", "file_id": message.animation.file_id}
    elif message.document:
        media_data = {"type": "document", "file_id": message.document.file_id}
    else:
        await message.answer("❌ Поддерживаются только фото, видео, GIF и документы")
        return

    manager.dialog_data["media"] = media_data
    await manager.next()


async def on_skip_media(callback: CallbackQuery, button: Button, manager: DialogManager) -> None:
    """Пропуск шага с медиа."""
    # media просто не будет в dialog_data
    await callback.answer()
    await manager.next()


async def on_winner_places(message: Message, widget: MessageInput, manager: DialogManager) -> None:
    """Шаг: количество призовых мест."""
    try:
        winner_places = int((message.text or "").strip())
    except ValueError:
        await message.answer(MESSAGES["invalid_winner_places"])
        return

    if winner_places < 1 or winner_places > 10:
        await message.answer(MESSAGES["invalid_winner_places"])
        return

    manager.dialog_data["winner_places"] = winner_places

    # Проверяем наличие каналов до перехода к выбору
    channels = await get_all_channels()
    if not channels:
        await message.answer(
            "❌ Нет доступных каналов! Сначала добавьте каналы в разделе управления каналами.",
        )
        await manager.done()
        return

    await manager.next()


async def channels_getter(dialog_manager: DialogManager, **kwargs) -> Dict[str, Any]:
    """Геттер для списка каналов."""
    channels = await get_all_channels()
    return {"channels": channels}


async def on_channel_selected(
    callback: CallbackQuery,
    widget: Select,
    manager: DialogManager,
    item_id: str,
) -> None:
    """Выбор канала для розыгрыша."""
    try:
        channel_id = int(item_id)
    except ValueError:
        await callback.answer("Некорректный канал", show_alert=True)
        return

    manager.dialog_data["channel_id"] = channel_id
    await callback.answer()
    await manager.next()


async def on_end_time(message: Message, widget: MessageInput, manager: DialogManager) -> None:
    """Шаг: дата и время окончания розыгрыша + подготовка текста подтверждения."""
    try:
        end_time = parse_datetime(message.text)
    except ValueError:
        await message.answer(MESSAGES["invalid_datetime"])
        return

    if not is_future_datetime(end_time):
        await message.answer(MESSAGES["datetime_in_past"])
        return

    manager.dialog_data["end_time"] = end_time

    # Подготовка текста подтверждения (аналог process_end_time)
    data = manager.dialog_data
    channels = await get_all_channels()
    selected_channel = next(
        (ch for ch in channels if ch.channel_id == data.get("channel_id")),
        None,
    )

    channel_name = selected_channel.channel_name if selected_channel else "Неизвестен"
    media_info = "Есть" if data.get("media") else "Нет"

    description = data.get("description", "")
    message_winner = data.get("message_winner", "")

    confirmation_text = MESSAGES["confirm_giveaway"].format(
        title=data.get("title", ""),
        description=description[:50] + "..." if len(description) > 50 else description,
        message_winner=message_winner[:50] + "..." if len(message_winner) > 50 else message_winner,
        winner_places=data.get("winner_places", 1),
        channel=channel_name,
        end_time=format_datetime(end_time),
        media=media_info,
    )

    manager.dialog_data["confirmation_text"] = confirmation_text
    await manager.next()


async def on_confirm_create(callback: CallbackQuery, button: Button, manager: DialogManager) -> None:
    """Подтверждение создания розыгрыша и публикация поста."""
    data = manager.dialog_data

    try:
        media_data = data.get("media")
        giveaway = await create_giveaway(
            title=data.get("title", ""),
            description=data.get("description", ""),
            message_winner=data.get("message_winner", ""),
            end_time=data["end_time"],
            channel_id=data["channel_id"],
            created_by=callback.from_user.id,
            winner_places=data.get("winner_places", 1),
            media_type=media_data["type"] if media_data else None,
            media_file_id=media_data["file_id"] if media_data else None,
        )

        if not giveaway:
            await callback.message.answer(MESSAGES["error_occurred"])
            await callback.answer()
            await manager.done()
            return

        post_text = GIVEAWAY_POST_TEMPLATE.format(
            title=data.get("title", ""),
            description=data.get("description", ""),
            winner_places=data.get("winner_places", 1),
            end_time=format_datetime(data["end_time"]),
            participants=0,
        )

        keyboard = get_participate_keyboard(giveaway.id, 0)

        try:
            if media_data:
                if media_data["type"] == "photo":
                    sent_message = await callback.bot.send_photo(
                        chat_id=data["channel_id"],
                        photo=media_data["file_id"],
                        caption=post_text,
                        reply_markup=keyboard,
                    )
                elif media_data["type"] == "video":
                    sent_message = await callback.bot.send_video(
                        chat_id=data["channel_id"],
                        video=media_data["file_id"],
                        caption=post_text,
                        reply_markup=keyboard,
                    )
                elif media_data["type"] == "animation":
                    sent_message = await callback.bot.send_animation(
                        chat_id=data["channel_id"],
                        animation=media_data["file_id"],
                        caption=post_text,
                        reply_markup=keyboard,
                    )
                else:
                    sent_message = await callback.bot.send_document(
                        chat_id=data["channel_id"],
                        document=media_data["file_id"],
                        caption=post_text,
                        reply_markup=keyboard,
                    )
            else:
                sent_message = await callback.bot.send_message(
                    chat_id=data["channel_id"],
                    text=post_text,
                    reply_markup=keyboard,
                )

            await update_giveaway_message_id(giveaway.id, sent_message.message_id)
            schedule_giveaway_finish(callback.bot, giveaway.id, data["end_time"])

            await callback.message.answer(MESSAGES["giveaway_created"])

        except Exception as e:
            logging.error(f"Ошибка публикации розыгрыша: {e}")
            await delete_giveaway(giveaway.id)
            await callback.message.answer(
                "❌ Ошибка при публикации розыгрыша в канале. Проверьте права бота.",
            )

    except Exception as e:
        logging.error(f"Ошибка создания розыгрыша: {e}")
        await callback.message.answer(MESSAGES["error_occurred"])

    await callback.answer()
    await manager.done()


async def on_cancel_create(callback: CallbackQuery, button: Button, manager: DialogManager) -> None:
    """Отмена создания розыгрыша."""
    await callback.answer()
    await callback.message.answer(MESSAGES["giveaway_creation_cancelled"])
    await manager.done()


create_giveaway_dialog = Dialog(
    # 1. Заголовок
    Window(
        Const(MESSAGES["create_giveaway_start"]),
        MessageInput(on_title),
        state=CreateGiveawayStates.WAITING_TITLE,
    ),
    # 2. Описание
    Window(
        Const(MESSAGES["enter_description"]),
        MessageInput(on_description),
        state=CreateGiveawayStates.WAITING_DESCRIPTION,
    ),
    # 3. Сообщение победителям
    Window(
        Const(MESSAGES["enter_message_winner"]),
        MessageInput(on_message_winner),
        state=CreateGiveawayStates.WAITING_MESSAGE_WINNERS,
    ),
    # 4. Медиа (с возможностью пропуска)
    Window(
        Const(MESSAGES["enter_media"]),
        MessageInput(on_media),
        Row(
            Button(Const(BUTTONS["skip_media"]), id="skip_media_btn", on_click=on_skip_media),
        ),
        state=CreateGiveawayStates.WAITING_MEDIA,
    ),
    # 5. Количество призовых мест
    Window(
        Const(MESSAGES["enter_winner_places"]),
        MessageInput(on_winner_places),
        state=CreateGiveawayStates.WAITING_WINNER_PLACES,
    ),
    # 6. Выбор канала
    Window(
        Const(MESSAGES["choose_channel"]),
        Select(
            Format("{item.channel_name}"),
            id="channel_select",
            item_id_getter=lambda ch: str(ch.channel_id),
            items="channels",
            on_click=on_channel_selected,
        ),
        getter=channels_getter,
        state=CreateGiveawayStates.WAITING_CHANNEL,
    ),
    # 7. Время окончания
    Window(
        Const(MESSAGES["enter_end_time"]),
        MessageInput(on_end_time),
        state=CreateGiveawayStates.WAITING_END_TIME,
    ),
    # 8. Подтверждение
    Window(
        Format("{confirmation_text}"),
        Row(
            Button(Const(BUTTONS["confirm"]), id="confirm_create_btn", on_click=on_confirm_create),
            Button(Const(BUTTONS["cancel"]), id="cancel_create_btn", on_click=on_cancel_create),
        ),
        state=CreateGiveawayStates.CONFIRM_CREATION,
    ),
)

