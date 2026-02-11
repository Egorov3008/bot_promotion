"""
Диалоги управления каналами на базе aiogram-dialog.

Поддерживаемые сценарии:
- просмотр списка каналов;
- добавление канала по ссылке/username;
- добавление канала пересылкой сообщения;
- удаление канала.

Используются состояния ChannelDialogStates из states.admin_states.
"""

from typing import Any, Dict

from aiogram.types import Message, CallbackQuery

from aiogram_dialog import Dialog, DialogManager, Window, StartMode
from aiogram_dialog.widgets.input import MessageInput
from aiogram_dialog.widgets.kbd import Button, Row, Select
from aiogram_dialog.widgets.text import Const, Format

from states.admin_states import ChannelDialogStates, AdminStates
from texts.messages import MESSAGES, BUTTONS, ADMIN_CHANNEL_ITEM
from database.database import get_all_channels, add_channel, remove_channel, add_channel_by_username


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


async def on_show_channels(callback: CallbackQuery, button: Button, manager: DialogManager) -> None:
    """Показ списка каналов."""
    await callback.answer()
    data = await channels_getter(manager)
    await callback.message.edit_text(
        data["channels_text"],
        parse_mode="HTML",
    )


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
        await manager.switch_to(ChannelDialogStates.MAIN_MENU)
    else:
        await message.answer(MESSAGES["channel_already_exists"])


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
)

