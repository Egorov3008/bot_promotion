"""
Диалоги управления администраторами бота на базе aiogram-dialog.

Поддерживаемые сценарии:
- просмотр списка администраторов;
- добавление администратора по ID или username/ссылке;
- удаление администратора (кроме главного).

Используются состояния AdminDialogStates из states.admin_states.
"""

import logging
from typing import Any, Dict, List

from aiogram.types import Message, CallbackQuery

from aiogram_dialog import Dialog, DialogManager, Window, StartMode
from aiogram_dialog.widgets.input import MessageInput
from aiogram_dialog.widgets.kbd import Button, Row, Select
from aiogram_dialog.widgets.text import Const, Format

from states.admin_states import AdminDialogStates, AdminStates
from texts.messages import MESSAGES, BUTTONS, ADMIN_USER_ITEM
from database.database import get_all_admins, add_admin, remove_admin, is_admin
from database.models import Admin


async def admins_getter(dialog_manager: DialogManager, **kwargs) -> Dict[str, Any]:
    """Геттер для списка администраторов."""
    admins = await get_all_admins()
    removable_admins: List[Admin] = [a for a in admins if not a.is_main_admin]

    admin_list_lines = []
    for admin in admins:
        admin_info = ADMIN_USER_ITEM.format(
            name=admin.first_name or "Без имени",
            username=admin.username or "без username",
            user_id=admin.user_id,
        )
        if admin.is_main_admin:
            admin_info += "\n👑 <b>Главный администратор</b>"
        admin_list_lines.append(admin_info)

    admins_text = (
        MESSAGES["current_admins"].format(admins="\n\n".join(admin_list_lines))
        if admin_list_lines
        else "👥 Администраторов не найдено"
    )

    return {
        "admins_text": admins_text,
        "removable_admins": removable_admins,
    }


async def on_show_admins(callback: CallbackQuery, button: Button, manager: DialogManager) -> None:
    """Кнопка 'Список админов' — просто обновляет текст с данными из геттера."""
    await callback.answer()
    data = await admins_getter(manager)
    await callback.message.edit_text(
        data["admins_text"],
        parse_mode="HTML",
    )


async def go_to_add_admin(callback: CallbackQuery, button: Button, manager: DialogManager) -> None:
    """Переход к вводу ID/username нового администратора."""
    await callback.answer()
    await manager.switch_to(AdminDialogStates.ADD_ADMIN_ID)


async def go_to_choose_remove(callback: CallbackQuery, button: Button, manager: DialogManager) -> None:
    """Переход к выбору администратора для удаления."""
    await callback.answer()
    data = await admins_getter(manager)
    if not data["removable_admins"]:
        await callback.answer("Нет администраторов для удаления", show_alert=True)
        return
    await manager.switch_to(AdminDialogStates.CHOOSE_ADMIN_TO_REMOVE)


async def go_back_to_main_menu(callback: CallbackQuery, button: Button, manager: DialogManager) -> None:
    """Возврат в главное админ-меню."""
    await callback.answer()
    await manager.start(AdminStates.MAIN_MENU, mode=StartMode.RESET_STACK)


async def on_add_admin_input(message: Message, widget: MessageInput, manager: DialogManager) -> None:
    """
    Обработка добавления администратора.
    Поддерживаются форматы:
    - @username
    - t.me/username или https://t.me/username
    - числовой user_id
    """
    text = (message.text or "").strip()
    username = None

    if text.startswith("@"):
        username = text[1:]
    elif "t.me/" in text:
        start = text.rfind("/") + 1
        username = text[start:]
    elif text.isdigit():
        # Добавление по ID без разрешения username
        try:
            user_id = int(text)
        except ValueError:
            await message.answer(MESSAGES["invalid_username_or_id"])
            return

        if await is_admin(user_id):
            await message.answer(MESSAGES["admin_already_exists"])
        else:
            success = await add_admin(
                user_id=user_id,
                username=None,
                first_name=f"ID: {user_id}",
                full_name=f"ID: {user_id}",
            )
            if success:
                await message.answer(MESSAGES["admin_added"])
            else:
                await message.answer(MESSAGES["admin_already_exists"])

        await manager.switch_to(AdminDialogStates.MAIN_MENU)
        return

    if not username:
        await message.answer(MESSAGES["invalid_username_or_id"])
        return

    # Пытаемся получить информацию о пользователе через get_chat
    try:
        chat = await message.bot.get_chat(f"@{username}" if not username.startswith("@") else username)
        if chat.type != "private":
            await message.answer("❌ Указанная ссылка ведёт не на пользователя.")
            return

        user_id = chat.id
        full_name = f"{chat.first_name} {chat.last_name}" if chat.last_name else chat.first_name

        if await is_admin(user_id):
            await message.answer(MESSAGES["admin_already_exists"])
        else:
            success = await add_admin(
                user_id=user_id,
                username=chat.username,
                first_name=chat.first_name,
                full_name=full_name,
            )
            if success:
                await message.answer(MESSAGES["admin_added"])
            else:
                await message.answer(MESSAGES["admin_already_exists"])

    except Exception as e:
        logging.warning(f"Не удалось найти пользователя по username '{username}': {e}")
        await message.answer(MESSAGES["admin_not_found"])

    await manager.switch_to(AdminDialogStates.MAIN_MENU)


async def on_remove_admin_selected(
    callback: CallbackQuery,
    widget: Select,
    manager: DialogManager,
    item_id: str,
) -> None:
    """Удаление выбранного администратора."""
    try:
        user_id = int(item_id)
    except ValueError:
        await callback.answer("Некорректный администратор", show_alert=True)
        return

    success = await remove_admin(user_id)
    if success:
        await callback.message.answer(MESSAGES["admin_removed"])
    else:
        await callback.message.answer(MESSAGES["error_occurred"])

    await callback.answer()
    await manager.switch_to(AdminDialogStates.MAIN_MENU)


admin_management_dialog = Dialog(
    # Главное меню управления администраторами
    Window(
        Const(MESSAGES["admin_management_menu"]),
        Row(
            Button(Const(BUTTONS["view_admins"]), id="view_admins_btn", on_click=on_show_admins),
        ),
        Row(
            Button(Const(BUTTONS["add_admin"]), id="add_admin_btn", on_click=go_to_add_admin),
            Button(Const(BUTTONS["remove_admin"]), id="remove_admin_btn", on_click=go_to_choose_remove),
        ),
        Row(
            Button(Const(BUTTONS["back_to_menu"]), id="back_to_main_admin_menu", on_click=go_back_to_main_menu),
        ),
        state=AdminDialogStates.MAIN_MENU,
    ),
    # Ввод ID/username нового администратора
    Window(
        Const(MESSAGES["enter_new_admin_id"]),
        MessageInput(on_add_admin_input),
        Row(
            Button(Const(BUTTONS["back"]), id="back_from_add_admin", on_click=lambda c, b, m: m.switch_to(AdminDialogStates.MAIN_MENU)),
        ),
        state=AdminDialogStates.ADD_ADMIN_ID,
    ),
    # Выбор администратора для удаления
    Window(
        Const(MESSAGES["choose_admin_to_remove"]),
        Select(
            Format("{item.first_name} (@{item.username})" if "{item.username}" else "{item.first_name}"),
            id="admin_to_remove_select",
            item_id_getter=lambda a: str(a.user_id),
            items="removable_admins",
            on_click=on_remove_admin_selected,
        ),
        Row(
            Button(Const(BUTTONS["back"]), id="back_from_remove_admin", on_click=lambda c, b, m: m.switch_to(AdminDialogStates.MAIN_MENU)),
        ),
        getter=admins_getter,
        state=AdminDialogStates.CHOOSE_ADMIN_TO_REMOVE,
    ),
)

