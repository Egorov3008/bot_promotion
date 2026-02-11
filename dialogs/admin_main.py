"""
Диалог главного админ-меню.

Сценарий:
- команда /admin в basic_handlers.py стартует этот диалог;
- в окне показывается текст MESSAGES["admin_main_menu"] и 4 кнопки:
  создание розыгрыша, просмотр розыгрышей, управление админами и каналами;
- реальные переходы в другие диалоги будут добавлены на следующих шагах,
  пока кнопки показывают плейсхолдеры.
"""

from aiogram.types import CallbackQuery

from aiogram_dialog import Dialog, DialogManager, Window, StartMode
from aiogram_dialog.widgets.kbd import Button, Row
from aiogram_dialog.widgets.text import Const

from states.admin_states import (
    AdminStates,
    CreateGiveawayStates,
    AdminDialogStates,
    ChannelDialogStates, ViewGiveawaysStates,
)
from texts.messages import MESSAGES, BUTTONS


async def _not_implemented(callback: CallbackQuery, button: Button, manager: DialogManager) -> None:
    """
    Временный обработчик для кнопок, пока соответствующие диалоги не реализованы.
    """
    await callback.answer("Функция будет доступна позже.", show_alert=True)


async def on_create_giveaway_click(callback: CallbackQuery, button: Button, manager: DialogManager) -> None:
    """Переход в мастер создания розыгрыша."""
    await callback.answer()
    await manager.start(state=CreateGiveawayStates.WAITING_TITLE, mode=StartMode.RESET_STACK)


async def on_admin_management_click(callback: CallbackQuery, button: Button, manager: DialogManager) -> None:
    """Переход в диалог управления администраторами."""
    await callback.answer()
    await manager.start(state=AdminDialogStates.MAIN_MENU, mode=StartMode.RESET_STACK)


async def on_channel_management_click(callback: CallbackQuery, button: Button, manager: DialogManager) -> None:
    """Переход в диалог управления каналами."""
    await callback.answer()
    await manager.start(state=ChannelDialogStates.MAIN_MENU, mode=StartMode.RESET_STACK)


async def on_view_giveaways_click(callback: CallbackQuery, button: Button, manager: DialogManager) -> None:
    """Переход к просмотру розыгрышей."""
    await callback.answer()
    await manager.start(state=ViewGiveawaysStates.CHOOSING_TYPE, mode=StartMode.RESET_STACK)


admin_main_dialog = Dialog(
    Window(
        Const(MESSAGES["admin_main_menu"]),
        Row(
            Button(Const(BUTTONS["create_giveaway"]), id="create_giveaway_btn", on_click=on_create_giveaway_click),
        ),
        Row(
            Button(Const(BUTTONS["view_giveaways"]), id="view_giveaways_btn", on_click=on_view_giveaways_click),
        ),
        Row(
            Button(Const(BUTTONS["admin_management"]), id="admin_management_btn", on_click=on_admin_management_click),
            Button(Const(BUTTONS["channel_management"]), id="channel_management_btn", on_click=on_channel_management_click),
        ),
        state=AdminStates.MAIN_MENU,
    )
)


