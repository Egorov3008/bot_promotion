from aiogram import Dispatcher

from .chat_member_handlers import chat_member_handlers
from .basic_handlers import setup_basic_handlers


def setup_handlers(dp: Dispatcher):
    """Регистрация всех хендлеров"""
    chat_member_handlers(dp)
    setup_basic_handlers(dp)

