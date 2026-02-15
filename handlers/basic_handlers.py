from aiogram import Dispatcher, Router
from aiogram.types import Message
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext

from aiogram_dialog import DialogManager, StartMode

from database.database import is_admin
from states.admin_states import AdminStates

router = Router()


@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    """Обработчик команды /start"""
    # Проверяем, является ли пользователь админом
    is_user_admin = await is_admin(message.from_user.id)
    
    if is_user_admin:
        await message.answer(
            "👋 Добро пожаловать, администратор!\n\n"
            "🎉 Это бот для проведения розыгрышей в Telegram-каналах.\n\n"
            "🛠 Используйте команду /admin для входа в панель управления."
        )
    else:
        await message.answer(
            "👋 Добро пожаловать!\n\n"
            "🎉 Этот бот проводит розыгрыши в Telegram-каналах.\n\n"
            "🎯 Чтобы участвовать в розыгрышах, нажимайте кнопку 'Участвовать' под постами розыгрышей в каналах.\n\n"
            "🏆 Удачи в розыгрышах!"
        )


@router.message(Command("clear"))
async def cmd_clear(message: Message):
    """Очистка последних сообщений в диалоге с ботом"""
    chat_id = message.chat.id
    start_id = max(1, message.message_id - 100)
    for msg_id in range(start_id, message.message_id + 1):
        try:
            await message.bot.delete_message(chat_id=chat_id, message_id=msg_id)
        except Exception:
            pass


@router.message(Command("admin"))
async def cmd_admin(message: Message, state: FSMContext, dialog_manager: DialogManager):
    """Обработчик команды /admin - вход в админ-панель"""
    await state.clear()
    await dialog_manager.start(state=AdminStates.MAIN_MENU, mode=StartMode.RESET_STACK)


def setup_basic_handlers(dp: Dispatcher):
    """Регистрация базовых хендлеров"""
    dp.include_router(router)
