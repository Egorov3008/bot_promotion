"""
Пакет с диалогами на базе aiogram-dialog.

Структура:
- admin_main.py      — главное админ-меню.
- admins.py          — управление администраторами.
- channels.py        — управление каналами.
- giveaway_create.py — мастер создания розыгрыша.
- giveaway_view.py   — просмотр списков и деталей розыгрышей.
- giveaway_edit.py   — редактирование/удаление розыгрышей.

Функция register_dialogs(dp) подключает все Dialog-объекты к Dispatcher.
По мере добавления новых диалогов их нужно регистрировать здесь.
"""

from aiogram import Dispatcher

from .admin_main import admin_main_dialog
from .giveaway_create import create_giveaway_dialog
from .admins import admin_management_dialog
from .channels import channels_dialog
from .giveaway_view import giveaway_view_dialog
from .giveaway_edit import giveaway_edit_dialog


def register_dialogs(dp: Dispatcher) -> None:
    """
    Регистрация всех диалогов в Dispatcher.
    """
    dp.include_router(admin_main_dialog)
    dp.include_router(create_giveaway_dialog)
    dp.include_router(admin_management_dialog)
    dp.include_router(channels_dialog)
    dp.include_router(giveaway_view_dialog)
    dp.include_router(giveaway_edit_dialog)

