"""
Диалоги управления каналами на базе aiogram-dialog.

Поддерживаемые сценарии:
- просмотр списка каналов;
- добавление канала по ссылке/username;
- добавление канала пересылкой сообщения;
- удаление канала;
- парсинг подписчиков после добавления канала (с прогресс-баром и отменой).

Используются состояния ChannelDialogStates из states.admin_states.
"""

import asyncio
import logging
from typing import Any, Dict

from aiogram.types import Message, CallbackQuery

from aiogram_dialog import Dialog, DialogManager, Window, StartMode, ShowMode
from aiogram_dialog.widgets.input import MessageInput
from aiogram_dialog.widgets.kbd import Button, Row, Select
from aiogram_dialog.widgets.text import Const, Format

from states.admin_states import ChannelDialogStates, AdminStates
from texts.messages import MESSAGES, BUTTONS, ADMIN_CHANNEL_ITEM, CHANNEL_DETAIL_TEXT
from database.database import (
    get_all_channels, add_channel, remove_channel,
    add_channel_by_username, bulk_add_channel_subscribers,
    get_channel, get_channel_subscribers_stats,
)

# ---------------------------------------------------------------------------
#  Getters
# ---------------------------------------------------------------------------

async def channels_getter(dialog_manager: DialogManager, **kwargs) -> Dict[str, Any]:
    """Геттер для списка каналов."""
    channels = await get_all_channels()

    channel_list = []
    for channel in channels:
        admin_name = "Неизвестно"
        if channel.admin:
            admin_name = channel.admin.first_name or f"ID: {channel.added_by}"
            if channel.admin.username:
                admin_name += f" (@{channel.admin.username})"

        channel_info = ADMIN_CHANNEL_ITEM.format(
            name=channel.channel_name,
            username=f"@{channel.channel_username}" if channel.channel_username else "Без username",
            admin=admin_name,
        )
        channel_list.append(channel_info)

    channel_text = (
        MESSAGES["current_channels"].format(channels="\n\n".join(channel_list))
        if channel_list
        else "📺 Каналов не найдено"
    )

    return {
        "channels": channels,
        "channels_text": channel_text,
    }


async def ask_parse_getter(dialog_manager: DialogManager, **kwargs) -> Dict[str, Any]:
    """Геттер для окна предложения парсинга."""
    channel_name = dialog_manager.dialog_data.get("parse_channel_name", "")
    return {
        "ask_parse_text": MESSAGES["channel_added_parsing_prompt"].format(channel=channel_name),
    }


async def parsing_progress_getter(dialog_manager: DialogManager, **kwargs) -> Dict[str, Any]:
    """Геттер для окна прогресса парсинга."""
    dd = dialog_manager.dialog_data
    parsed = dd.get("parsed", 0)
    total = dd.get("total", 1) or 1
    channel_name = dd.get("parse_channel_name", "")

    percent = min(parsed / total * 100, 100)
    filled = int(percent / 10)
    bar = "\u2588" * filled + "\u2591" * (10 - filled)

    progress_text = (
        f"\u23f3 <b>Парсинг в процессе...</b>\n\n"
        f"\U0001f4fa Канал: {channel_name}\n"
        f"\U0001f465 Обработано: {parsed}/{total}\n"
        f"\U0001f4c8 [{bar}] {percent:.0f}%\n\n"
        f"<i>Пожалуйста, подождите...</i>"
    )
    return {"progress_text": progress_text}


async def parsing_complete_getter(dialog_manager: DialogManager, **kwargs) -> Dict[str, Any]:
    """Геттер для окна результатов парсинга."""
    dd = dialog_manager.dialog_data
    channel_name = dd.get("parse_channel_name", "")
    total = dd.get("parsed", 0)
    with_username = dd.get("with_username", 0)
    without_username = dd.get("without_username", 0)
    bots = dd.get("bots_count", 0)
    added = dd.get("added", 0)
    updated = dd.get("updated", 0)
    cancelled = dd.get("parsing_cancelled", False)

    if cancelled:
        result_text = BUTTONS["parsing_cancelled"].format(
            channel=channel_name,
            processed=total,
        )
    else:
        result_text = BUTTONS["parsing_complete"].format(
            channel=channel_name,
            total=total,
            with_username=with_username,
            without_username=without_username,
            added=added,
            updated=updated,
        )

    return {"result_text": result_text}


async def channel_list_getter(dialog_manager: DialogManager, **kwargs) -> Dict[str, Any]:
    """Геттер для списка каналов (Select)."""
    channels = await get_all_channels()
    return {"channels": channels}


async def channel_info_getter(dialog_manager: DialogManager, **kwargs) -> Dict[str, Any]:
    """Геттер для детальной информации о канале."""
    channel_id = dialog_manager.dialog_data.get("selected_channel_id")
    if not channel_id:
        return {"detail_text": "❌ Канал не найден"}

    channel = await get_channel(channel_id)
    if not channel:
        return {"detail_text": "❌ Канал не найден в базе"}

    # Статистика подписчиков
    stats = await get_channel_subscribers_stats(channel_id)

    # Кто добавил
    added_by = "Неизвестно"
    if channel.admin:
        added_by = channel.admin.first_name or f"ID: {channel.added_by}"
        if channel.admin.username:
            added_by += f" (@{channel.admin.username})"

    # Группа обсуждений
    discussion = str(channel.discussion_group_id) if channel.discussion_group_id else "Нет"

    # Дата добавления
    created_at = channel.created_at.strftime("%d.%m.%Y %H:%M") if channel.created_at else "—"

    # Администраторы канала из Telegram API
    bot = dialog_manager.middleware_data["bot"]
    admins_list = ""
    try:
        admins = await bot.get_chat_administrators(channel_id)
        admin_lines = []
        for admin in admins:
            user = admin.user
            if user.is_bot:
                name = f"🤖 {user.first_name or ''}"
            else:
                name = f"👤 {user.first_name or ''}"
            if user.username:
                name += f" (@{user.username})"
            role = "владелец" if admin.status == "creator" else "админ"
            admin_lines.append(f"  {name} — <i>{role}</i>")
        admins_list = "\n".join(admin_lines) if admin_lines else "Нет данных"
    except Exception as e:
        admins_list = f"⚠️ Не удалось получить: {e}"

    detail_text = CHANNEL_DETAIL_TEXT.format(
        name=channel.channel_name,
        username=f"@{channel.channel_username}" if channel.channel_username else "Нет",
        channel_id=channel.channel_id,
        discussion_group=discussion,
        added_by=added_by,
        created_at=created_at,
        subs_total=stats.get("active", 0),
        subs_with_un=stats.get("with_username", 0),
        subs_without_un=stats.get("without_username", 0),
        admins_list=admins_list,
    )

    return {"detail_text": detail_text}


# ---------------------------------------------------------------------------
#  Handlers — navigation
# ---------------------------------------------------------------------------

async def on_show_channels(callback: CallbackQuery, button: Button, manager: DialogManager) -> None:
    """Переход к списку каналов."""
    await callback.answer()
    await manager.switch_to(ChannelDialogStates.VIEW_CHANNELS_LIST)


async def on_channel_selected(
    callback: CallbackQuery,
    widget: Select,
    manager: DialogManager,
    item_id: str,
) -> None:
    """Выбор канала для просмотра деталей."""
    await callback.answer()
    try:
        manager.dialog_data["selected_channel_id"] = int(item_id)
    except ValueError:
        return
    await manager.switch_to(ChannelDialogStates.VIEW_CHANNEL_INFO)


async def go_to_add_by_link(callback: CallbackQuery, button: Button, manager: DialogManager) -> None:
    """Переход к добавлению канала по ссылке."""
    await callback.answer()
    await manager.switch_to(ChannelDialogStates.ADD_BY_LINK)


async def go_to_add_by_forward(callback: CallbackQuery, button: Button, manager: DialogManager) -> None:
    """Переход к добавлению канала пересылкой."""
    await callback.answer()
    await manager.switch_to(ChannelDialogStates.ADD_BY_FORWARD)


async def go_to_choose_channel_remove(callback: CallbackQuery, button: Button, manager: DialogManager) -> None:
    """Переход к выбору канала для удаления."""
    await callback.answer()
    data = await channels_getter(manager)
    if not data["channels"]:
        await callback.answer("Нет каналов для удаления", show_alert=True)
        return
    await manager.switch_to(ChannelDialogStates.CHOOSE_CHANNEL_TO_REMOVE)


async def go_back_to_admin_main(callback: CallbackQuery, button: Button, manager: DialogManager) -> None:
    """Назад в главное админ-меню."""
    await callback.answer()
    await manager.start(AdminStates.MAIN_MENU, mode=StartMode.RESET_STACK)


# ---------------------------------------------------------------------------
#  Handlers — add channel
# ---------------------------------------------------------------------------

async def on_add_channel_by_link(message: Message, widget: MessageInput, manager: DialogManager) -> None:
    """Добавление канала по ссылке/username."""
    channel_input = (message.text or "").strip()
    success, result_message = await add_channel_by_username(
        channel_username=channel_input,
        bot=message.bot,
        added_by=message.from_user.id,
    )
    if not result_message:
        result_message = "✅ Канал добавлен!" if success else "❌ Ошибка при добавлении канала."

    await message.answer(result_message)
    if success:
        # Получаем инфо о канале для парсинга
        clean = channel_input.replace("@", "").replace("https://t.me/", "").replace("http://t.me/", "")
        try:
            chat = await message.bot.get_chat(f"@{clean}")
            manager.dialog_data["parse_channel_id"] = chat.id
            manager.dialog_data["parse_channel_name"] = chat.title or clean
            await manager.switch_to(ChannelDialogStates.ASK_PARSE)
        except Exception:
            await manager.switch_to(ChannelDialogStates.MAIN_MENU)


async def on_add_channel_by_forward(message: Message, widget: MessageInput, manager: DialogManager) -> None:
    """Добавление канала пересылкой сообщения из канала."""
    if not message.forward_from_chat:
        await message.answer("❌ Пожалуйста, перешлите сообщение из канала")
        return

    channel = message.forward_from_chat
    if channel.type != "channel":
        await message.answer("❌ Это не канал!")
        return

    # Проверяем, является ли бот администратором канала
    try:
        bot_member = await message.bot.get_chat_member(channel.id, message.bot.id)
        if bot_member.status not in ["administrator", "creator"]:
            await message.answer(MESSAGES["bot_not_admin"])
            return
    except Exception:
        await message.answer(MESSAGES["bot_not_admin"])
        return

    success = await add_channel(
        channel_id=channel.id,
        channel_name=channel.title,
        channel_username=channel.username,
        added_by=message.from_user.id,
    )

    if success:
        await message.answer(MESSAGES["channel_added"])
        manager.dialog_data["parse_channel_id"] = channel.id
        manager.dialog_data["parse_channel_name"] = channel.title or str(channel.id)
        await manager.switch_to(ChannelDialogStates.ASK_PARSE)
    else:
        await message.answer(MESSAGES["channel_already_exists"])


# ---------------------------------------------------------------------------
#  Handlers — remove channel
# ---------------------------------------------------------------------------

async def on_remove_channel_selected(
    callback: CallbackQuery,
    widget: Select,
    manager: DialogManager,
    item_id: str,
) -> None:
    """Удаление выбранного канала."""
    try:
        channel_id = int(item_id)
    except ValueError:
        await callback.answer("Некорректный канал", show_alert=True)
        return

    success = await remove_channel(channel_id)
    if success:
        await callback.message.answer(MESSAGES["channel_removed"])
    else:
        await callback.message.answer(MESSAGES["error_occurred"])

    await callback.answer()
    await manager.switch_to(ChannelDialogStates.MAIN_MENU)


# ---------------------------------------------------------------------------
#  Handlers — parsing
# ---------------------------------------------------------------------------

async def _run_parsing_task(
    bg_manager,
    channel_id: int,
    channel_name: str,
    pyro_client,
) -> None:
    """Фоновая задача парсинга подписчиков."""
    from pyrogram_app.parsing_mode import ParsingMode

    app = pyro_client.app
    parser = ParsingMode(app)

    # Сохраняем parser для возможности отмены
    await bg_manager.update({"_parser": parser}, show_mode=ShowMode.NO_UPDATE)

    async def progress_callback(stats, total):
        try:
            await bg_manager.update(
                {
                    "parsed": stats.total_processed,
                    "total": total,
                    "with_username": stats.with_username,
                    "without_username": stats.without_username,
                    "bots_count": stats.bots_count,
                },
                show_mode=ShowMode.EDIT,
            )
        except Exception as e:
            logging.warning(f"Не удалось обновить прогресс: {e}")

    try:
        subscribers, stats = await parser.parse_full_batched(
            channel_id=channel_id,
            batch_size=200,
            progress_callback=progress_callback,
        )

        # Сохраняем подписчиков в БД
        added, updated = 0, 0
        if subscribers:
            added, updated = await bulk_add_channel_subscribers(channel_id, subscribers)

        cancelled = parser._stop_event.is_set()
        await bg_manager.update(
            {
                "parsed": stats.total_processed,
                "total": stats.total_processed,
                "with_username": stats.with_username,
                "without_username": stats.without_username,
                "bots_count": stats.bots_count,
                "added": added,
                "updated": updated,
                "parsing_cancelled": cancelled,
                "_parsing_done": True,
            },
            show_mode=ShowMode.NO_UPDATE,
        )

        # Переключаем на экран результатов
        try:
            await bg_manager.switch_to(ChannelDialogStates.PARSING_COMPLETE)
        except Exception as e:
            logging.warning(f"Не удалось переключить на результаты: {e}")

    except Exception as e:
        logging.error(f"Ошибка парсинга канала {channel_name}: {e}")
        await bg_manager.update(
            {
                "parsing_cancelled": True,
                "parsing_error": str(e),
                "_parsing_done": True,
            },
            show_mode=ShowMode.NO_UPDATE,
        )
        try:
            await bg_manager.switch_to(ChannelDialogStates.PARSING_COMPLETE)
        except Exception:
            pass


async def on_start_parsing(callback: CallbackQuery, button: Button, manager: DialogManager) -> None:
    """Запуск парсинга подписчиков."""
    await callback.answer()

    channel_id = manager.dialog_data.get("parse_channel_id")
    channel_name = manager.dialog_data.get("parse_channel_name", "")

    if not channel_id:
        await callback.message.answer("❌ Канал не найден")
        await manager.switch_to(ChannelDialogStates.MAIN_MENU)
        return

    # Получаем pyrogram клиент
    from pyrogram_app.pyro_client import get_pyrogram_client
    try:
        pyro_client = get_pyrogram_client()
    except RuntimeError:
        await callback.message.answer("❌ Pyrogram клиент не запущен")
        await manager.switch_to(ChannelDialogStates.MAIN_MENU)
        return

    # Инициализируем прогресс
    manager.dialog_data["parsed"] = 0
    manager.dialog_data["total"] = 0
    manager.dialog_data["_parsing_done"] = False

    await manager.switch_to(ChannelDialogStates.PARSING_IN_PROGRESS)

    # Создаём background manager и запускаем задачу
    bg_manager = manager.bg(
        user_id=callback.from_user.id,
        chat_id=callback.message.chat.id,
    )

    task = asyncio.create_task(
        _run_parsing_task(bg_manager, channel_id, channel_name, pyro_client)
    )
    manager.dialog_data["_parsing_task"] = task


async def on_skip_parsing(callback: CallbackQuery, button: Button, manager: DialogManager) -> None:
    """Пропуск парсинга."""
    await callback.answer()
    await manager.switch_to(ChannelDialogStates.MAIN_MENU)


async def on_cancel_parsing(callback: CallbackQuery, button: Button, manager: DialogManager) -> None:
    """Отмена парсинга."""
    await callback.answer("Отмена парсинга...")

    # Останавливаем парсер
    parser = manager.dialog_data.get("_parser")
    if parser:
        parser.stop()

    # Отменяем задачу если ещё выполняется
    task = manager.dialog_data.get("_parsing_task")
    if task and not task.done():
        # Даём парсеру время остановиться
        try:
            await asyncio.wait_for(task, timeout=5.0)
        except asyncio.TimeoutError:
            task.cancel()

    manager.dialog_data["parsing_cancelled"] = True
    await manager.switch_to(ChannelDialogStates.PARSING_COMPLETE)


async def on_parsing_back_to_menu(callback: CallbackQuery, button: Button, manager: DialogManager) -> None:
    """Возврат в меню после парсинга."""
    await callback.answer()
    # Чистим данные парсинга
    for key in list(manager.dialog_data.keys()):
        if key.startswith("parse_") or key.startswith("_pars") or key in (
            "parsed", "total", "with_username", "without_username",
            "bots_count", "added", "updated", "parsing_cancelled",
            "parsing_error", "_parser", "_parsing_task", "_parsing_done",
        ):
            manager.dialog_data.pop(key, None)
    await manager.switch_to(ChannelDialogStates.MAIN_MENU)


async def on_check_parsing_done(callback: CallbackQuery, button: Button, manager: DialogManager) -> None:
    """Проверка завершения парсинга (скрытая кнопка для автоматического обновления)."""
    await callback.answer()
    if manager.dialog_data.get("_parsing_done"):
        await manager.switch_to(ChannelDialogStates.PARSING_COMPLETE)


# ---------------------------------------------------------------------------
#  Dialog
# ---------------------------------------------------------------------------

channels_dialog = Dialog(
    # Главное меню управления каналами
    Window(
        Const(MESSAGES["channel_management_menu"]),
        Row(
            Button(Const(BUTTONS["view_channels"]), id="view_channels_btn", on_click=on_show_channels),
        ),
        Row(
            Button(Const(BUTTONS["add_channel_by_link"]), id="add_channel_link_btn", on_click=go_to_add_by_link),
            Button(Const(BUTTONS["add_channel_by_forward"]), id="add_channel_forward_btn", on_click=go_to_add_by_forward),
        ),
        Row(
            Button(Const(BUTTONS["remove_channel"]), id="remove_channel_btn", on_click=go_to_choose_channel_remove),
        ),
        Row(
            Button(Const(BUTTONS["back_to_menu"]), id="back_to_admin_menu_btn", on_click=go_back_to_admin_main),
        ),
        state=ChannelDialogStates.MAIN_MENU,
    ),
    # Добавление по ссылке
    Window(
        Const(MESSAGES["enter_channel_link"]),
        MessageInput(on_add_channel_by_link),
        Row(
            Button(Const(BUTTONS["back"]), id="back_from_add_link", on_click=lambda c, b, m: m.switch_to(ChannelDialogStates.MAIN_MENU)),
        ),
        state=ChannelDialogStates.ADD_BY_LINK,
    ),
    # Добавление пересылкой
    Window(
        Const(MESSAGES["enter_channel_forward"]),
        MessageInput(on_add_channel_by_forward),
        Row(
            Button(Const(BUTTONS["back"]), id="back_from_add_forward", on_click=lambda c, b, m: m.switch_to(ChannelDialogStates.MAIN_MENU)),
        ),
        state=ChannelDialogStates.ADD_BY_FORWARD,
    ),
    # Выбор канала для удаления
    Window(
        Const(MESSAGES["choose_channel_to_remove"]),
        Select(
            Format("{item.channel_name} (@{item.channel_username})" if "{item.channel_username}" else "{item.channel_name}"),
            id="channel_to_remove_select",
            item_id_getter=lambda ch: str(ch.channel_id),
            items="channels",
            on_click=on_remove_channel_selected,
        ),
        Row(
            Button(Const(BUTTONS["back"]), id="back_from_remove_channel", on_click=lambda c, b, m: m.switch_to(ChannelDialogStates.MAIN_MENU)),
        ),
        getter=channels_getter,
        state=ChannelDialogStates.CHOOSE_CHANNEL_TO_REMOVE,
    ),
    # Список каналов (выбор)
    Window(
        Const("📺 <b>Выберите канал для просмотра:</b>"),
        Select(
            Format("📺 {item.channel_name}"),
            id="channel_view_select",
            item_id_getter=lambda ch: str(ch.channel_id),
            items="channels",
            on_click=on_channel_selected,
        ),
        Row(
            Button(Const(BUTTONS["back"]), id="back_from_channels_list",
                   on_click=lambda c, b, m: m.switch_to(ChannelDialogStates.MAIN_MENU)),
        ),
        getter=channel_list_getter,
        state=ChannelDialogStates.VIEW_CHANNELS_LIST,
    ),
    # Детальная информация о канале
    Window(
        Format("{detail_text}"),
        Row(
            Button(Const(BUTTONS["back"]), id="back_from_channel_info",
                   on_click=lambda c, b, m: m.switch_to(ChannelDialogStates.VIEW_CHANNELS_LIST)),
        ),
        Row(
            Button(Const(BUTTONS["back_to_menu"]), id="channel_info_to_menu",
                   on_click=lambda c, b, m: m.switch_to(ChannelDialogStates.MAIN_MENU)),
        ),
        getter=channel_info_getter,
        state=ChannelDialogStates.VIEW_CHANNEL_INFO,
    ),
    # Предложение парсинга
    Window(
        Format("{ask_parse_text}"),
        Row(
            Button(Const(BUTTONS["start_parsing"]), id="start_parsing_btn", on_click=on_start_parsing),
            Button(Const(BUTTONS["skip_parsing"]), id="skip_parsing_btn", on_click=on_skip_parsing),
        ),
        getter=ask_parse_getter,
        state=ChannelDialogStates.ASK_PARSE,
    ),
    # Прогресс парсинга
    Window(
        Format("{progress_text}"),
        Row(
            Button(Const(BUTTONS["cancel_parsing"]), id="cancel_parsing_btn", on_click=on_cancel_parsing),
        ),
        getter=parsing_progress_getter,
        state=ChannelDialogStates.PARSING_IN_PROGRESS,
    ),
    # Результаты парсинга
    Window(
        Format("{result_text}"),
        Row(
            Button(Const(BUTTONS["back_to_menu"]), id="parsing_back_menu_btn", on_click=on_parsing_back_to_menu),
        ),
        getter=parsing_complete_getter,
        state=ChannelDialogStates.PARSING_COMPLETE,
    ),
)
