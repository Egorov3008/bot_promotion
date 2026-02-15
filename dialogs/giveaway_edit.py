"""
Диалоги редактирования и удаления розыгрышей.

Логика EditGiveawayStates:
- выбор поля (заголовок, описание, медиа, время, message_winner);
- обновление полей через update_giveaway_fields и переопубликование поста;
- удаление розыгрыша (delete_giveaway, cancel_giveaway_schedule + удаление сообщения из канала).
"""

import logging
from typing import Any, Dict

from aiogram.types import Message, CallbackQuery

from aiogram_dialog import Dialog, DialogManager, Window
from aiogram_dialog.widgets.input import MessageInput
from aiogram_dialog.widgets.kbd import Button, Row
from aiogram_dialog.widgets.text import Const

from states.admin_states import EditGiveawayStates, ViewGiveawaysStates
from texts.messages import MESSAGES, BUTTONS
from utils.datetime_utils import parse_datetime, is_future_datetime
from utils.scheduler import schedule_giveaway_finish, cancel_giveaway_schedule
from utils.keyboards import get_participate_keyboard
from utils.datetime_utils import format_datetime
from database.database import (
    get_giveaway,
    update_giveaway_fields,
    delete_giveaway,
    update_giveaway_message_id,
)
from database.database import get_participants_count


async def update_channel_giveaway_post(bot, giveaway) -> None:
    """Переопубликовывает пост розыгрыша в канале."""
    try:
        participants_count = await get_participants_count(giveaway.id)
        from texts.messages import GIVEAWAY_POST_TEMPLATE

        post_text = GIVEAWAY_POST_TEMPLATE.format(
            title=giveaway.title,
            description=giveaway.description,
            winner_places=getattr(giveaway, "winner_places", 1),
            end_time=format_datetime(giveaway.end_time),
            participants=participants_count,
        )
        keyboard = get_participate_keyboard(giveaway.id, participants_count)

        sent_message = None
        if giveaway.media_type == "photo" and giveaway.media_file_id:
            sent_message = await bot.send_photo(
                chat_id=giveaway.channel_id,
                photo=giveaway.media_file_id,
                caption=post_text,
                reply_markup=keyboard,
            )
        elif giveaway.media_type == "video" and giveaway.media_file_id:
            sent_message = await bot.send_video(
                chat_id=giveaway.channel_id,
                video=giveaway.media_file_id,
                caption=post_text,
                reply_markup=keyboard,
            )
        elif giveaway.media_type == "animation" and giveaway.media_file_id:
            sent_message = await bot.send_animation(
                chat_id=giveaway.channel_id,
                animation=giveaway.media_file_id,
                caption=post_text,
                reply_markup=keyboard,
            )
        elif giveaway.media_type == "document" and giveaway.media_file_id:
            sent_message = await bot.send_document(
                chat_id=giveaway.channel_id,
                document=giveaway.media_file_id,
                caption=post_text,
                reply_markup=keyboard,
            )
        else:
            sent_message = await bot.send_message(
                chat_id=giveaway.channel_id,
                text=post_text,
                reply_markup=keyboard,
            )

        if sent_message:
            if giveaway.message_id:
                try:
                    await bot.delete_message(chat_id=giveaway.channel_id, message_id=giveaway.message_id)
                except Exception:
                    pass
            await update_giveaway_message_id(giveaway.id, sent_message.message_id)
    except Exception as e:
        logging.error(f"Ошибка обновления поста розыгрыша: {e}")


async def start_edit_title(callback: CallbackQuery, button: Button, manager: DialogManager) -> None:
    await callback.answer()
    await manager.switch_to(EditGiveawayStates.WAITING_NEW_TITLE)


async def start_edit_description(callback: CallbackQuery, button: Button, manager: DialogManager) -> None:
    await callback.answer()
    await manager.switch_to(EditGiveawayStates.WAITING_NEW_DESCRIPTION)


async def start_edit_message_winner(callback: CallbackQuery, button: Button, manager: DialogManager) -> None:
    await callback.answer()
    await manager.switch_to(EditGiveawayStates.WAITING_NEW_MESSAGE_WINNER)


async def start_edit_media(callback: CallbackQuery, button: Button, manager: DialogManager) -> None:
    await callback.answer()
    await manager.switch_to(EditGiveawayStates.WAITING_NEW_MEDIA)


async def start_edit_end_time(callback: CallbackQuery, button: Button, manager: DialogManager) -> None:
    await callback.answer()
    await manager.switch_to(EditGiveawayStates.WAITING_NEW_END_TIME)


async def on_new_title(message: Message, widget: MessageInput, manager: DialogManager) -> None:
    title = (message.html_text or message.text or "").strip()
    if len(title) > 255:
        await message.answer(MESSAGES["title_too_long"])
        return
    giveaway_id = manager.dialog_data.get("current_giveaway_id")
    await update_giveaway_fields(giveaway_id, title=title)
    updated = await get_giveaway(giveaway_id)
    await update_channel_giveaway_post(message.bot, updated)
    await message.answer(MESSAGES["giveaway_updated"])
    await manager.switch_to(EditGiveawayStates.CHOOSING_FIELD)


async def on_new_description(message: Message, widget: MessageInput, manager: DialogManager) -> None:
    description = (message.html_text or message.text or "").strip()
    if len(description) > 4000:
        await message.answer(MESSAGES["description_too_long"])
        return
    giveaway_id = manager.dialog_data.get("current_giveaway_id")
    await update_giveaway_fields(giveaway_id, description=description)
    updated = await get_giveaway(giveaway_id)
    await update_channel_giveaway_post(message.bot, updated)
    await message.answer(MESSAGES["giveaway_updated"])
    await manager.switch_to(EditGiveawayStates.CHOOSING_FIELD)


async def on_new_message_winner(message: Message, widget: MessageInput, manager: DialogManager) -> None:
    message_winner = (message.html_text or message.text or "").strip()
    if len(message_winner) > 4000:
        await message.answer(MESSAGES["message_winners_too_long"])
        return
    giveaway_id = manager.dialog_data.get("current_giveaway_id")
    await update_giveaway_fields(giveaway_id, message_winner=message_winner)
    await message.answer(MESSAGES["giveaway_updated"])
    await manager.switch_to(EditGiveawayStates.CHOOSING_FIELD)


async def on_new_media(message: Message, widget: MessageInput, manager: DialogManager) -> None:
    media_type = None
    file_id = None
    if message.photo:
        media_type = "photo"
        file_id = message.photo[-1].file_id
    elif message.video:
        media_type = "video"
        file_id = message.video.file_id
    elif message.animation:
        media_type = "animation"
        file_id = message.animation.file_id
    elif message.document:
        media_type = "document"
        file_id = message.document.file_id
    else:
        await message.answer("❌ Поддерживаются только фото, видео, GIF и документы")
        return

    giveaway_id = manager.dialog_data.get("current_giveaway_id")
    await update_giveaway_fields(giveaway_id, media_type=media_type, media_file_id=file_id)
    updated = await get_giveaway(giveaway_id)
    await update_channel_giveaway_post(message.bot, updated)
    await message.answer(MESSAGES["giveaway_updated"])
    await manager.switch_to(EditGiveawayStates.CHOOSING_FIELD)


async def on_new_end_time(message: Message, widget: MessageInput, manager: DialogManager) -> None:
    try:
        new_end = parse_datetime(message.text)
    except ValueError:
        await message.answer(MESSAGES["invalid_datetime"])
        return

    if not is_future_datetime(new_end):
        await message.answer(MESSAGES["datetime_in_past"])
        return

    giveaway_id = manager.dialog_data.get("current_giveaway_id")
    await update_giveaway_fields(giveaway_id, end_time=new_end)
    updated = await get_giveaway(giveaway_id)
    schedule_giveaway_finish(message.bot, giveaway_id, new_end)
    await update_channel_giveaway_post(message.bot, updated)
    await message.answer(MESSAGES["giveaway_updated"])
    await manager.switch_to(EditGiveawayStates.CHOOSING_FIELD)


async def back_to_details(callback: CallbackQuery, button: Button, manager: DialogManager) -> None:
    await callback.answer()
    await manager.switch_to(ViewGiveawaysStates.VIEWING_DETAILS)


async def start_delete(callback: CallbackQuery, button: Button, manager: DialogManager) -> None:
    """Подтверждение удаления розыгрыша."""
    await callback.answer()
    giveaway_id = manager.dialog_data.get("current_giveaway_id")
    giveaway = await get_giveaway(giveaway_id)
    if not giveaway:
        await callback.message.answer("❌ Розыгрыш не найден")
        return
    text = MESSAGES["confirm_delete"].format(title=giveaway.title)
    await callback.message.answer(text)
    await manager.switch_to(EditGiveawayStates.CONFIRM_EDIT)


async def confirm_delete(callback: CallbackQuery, button: Button, manager: DialogManager) -> None:
    """Окончательное удаление розыгрыша."""
    await callback.answer()
    giveaway_id = manager.dialog_data.get("current_giveaway_id")
    giveaway = await get_giveaway(giveaway_id)

    if giveaway:
        if giveaway.status == "active":
            cancel_giveaway_schedule(giveaway_id)
        if giveaway.message_id:
            try:
                await callback.bot.delete_message(
                    chat_id=giveaway.channel_id,
                    message_id=giveaway.message_id,
                )
            except Exception as e:
                logging.warning(f"Не удалось удалить сообщение из канала: {e}")

    success = await delete_giveaway(giveaway_id)
    if success:
        await callback.message.answer(MESSAGES["giveaway_deleted"])
    else:
        await callback.message.answer(MESSAGES["error_occurred"])

    await manager.done()


async def cancel_delete(callback: CallbackQuery, button: Button, manager: DialogManager) -> None:
    await callback.answer()
    await callback.message.answer(MESSAGES["deletion_cancelled"])
    await manager.switch_to(ViewGiveawaysStates.VIEWING_DETAILS)


giveaway_edit_dialog = Dialog(
    # Выбор поля для редактирования
    Window(
        Const(MESSAGES["choose_field_to_edit"]),
        Row(
            Button(Const(BUTTONS["edit_title"]), id="edit_title_btn", on_click=start_edit_title),
        ),
        Row(
            Button(Const(BUTTONS["edit_description"]), id="edit_description_btn", on_click=start_edit_description),
        ),
        Row(
            Button(Const(BUTTONS["message_winner"]), id="edit_message_winner_btn", on_click=start_edit_message_winner),
        ),
        Row(
            Button(Const(BUTTONS["edit_media"]), id="edit_media_btn", on_click=start_edit_media),
        ),
        Row(
            Button(Const(BUTTONS["edit_end_time"]), id="edit_end_time_btn", on_click=start_edit_end_time),
        ),
        Row(
            Button(Const(BUTTONS["back"]), id="back_to_details_btn", on_click=back_to_details),
        ),
        state=EditGiveawayStates.CHOOSING_FIELD,
    ),
    # Новые значения
    Window(
        Const(MESSAGES["enter_new_title"]),
        MessageInput(on_new_title),
        state=EditGiveawayStates.WAITING_NEW_TITLE,
    ),
    Window(
        Const(MESSAGES["enter_new_description"]),
        MessageInput(on_new_description),
        state=EditGiveawayStates.WAITING_NEW_DESCRIPTION,
    ),
    Window(
        Const(MESSAGES["enter_new_message_winner"]),
        MessageInput(on_new_message_winner),
        state=EditGiveawayStates.WAITING_NEW_MESSAGE_WINNER,
    ),
    Window(
        Const(MESSAGES["enter_new_media"]),
        MessageInput(on_new_media),
        state=EditGiveawayStates.WAITING_NEW_MEDIA,
    ),
    Window(
        Const(MESSAGES["enter_new_end_time"]),
        MessageInput(on_new_end_time),
        state=EditGiveawayStates.WAITING_NEW_END_TIME,
    ),
    # Удаление
    Window(
        Const("Подтверждение удаления розыгрыша"),
        Row(
            Button(Const(BUTTONS["yes"]), id="confirm_delete_btn", on_click=confirm_delete),
            Button(Const(BUTTONS["no"]), id="cancel_delete_btn", on_click=cancel_delete),
        ),
        state=EditGiveawayStates.CONFIRM_EDIT,
    ),
)

