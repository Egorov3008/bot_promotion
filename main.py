import asyncio
import logging
import sys
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import BotCommand

from aiogram_dialog import setup_dialogs

from config import config
from database.database import init_db
from handlers import setup_handlers
from middlewares.auth import AdminMiddleware
from middlewares.pyro import PyrogramMiddleware
from pyrogram_app.pyro_client import setup_pyrogram
from utils.scheduler import setup_scheduler
from dialogs import register_dialogs


async def main():
    """Основная функция запуска бота"""
    # Настройка логирования
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler('bot.log', encoding='utf-8'),
            logging.StreamHandler(sys.stdout)
        ]
    )
    pyro = setup_pyrogram(config)
    await pyro.start()  # 🔥 Запускаем сразу
    # Инициализация бота и диспетчера
    bot = Bot(
        token=config.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )
    logging.getLogger("aiogram.event").setLevel(logging.WARNING)
    logging.getLogger("pyrogram.session").setLevel(logging.ERROR)

    # Устанавливаем команды бота
    try:
        await bot.set_my_commands([
            BotCommand(command="start", description="Запуск и перезапуск бота"),
            BotCommand(command="clear", description="Очистить диалог"),
        ])
    except Exception:
        pass
    
    dp = Dispatcher()
    
    # Инициализация базы данных
    await init_db()
    
    # Настройка middleware для проверки админов
    dp.message.middleware(AdminMiddleware())
    dp.callback_query.middleware(AdminMiddleware())
    dp.message.middleware(PyrogramMiddleware(pyro))
    
    # Регистрация handlers
    setup_handlers(dp)

    # Регистрация диалогов и инициализация aiogram-dialog
    register_dialogs(dp)
    setup_dialogs(dp)
    
    # Настройка планировщика для автоматического завершения розыгрышей
    await setup_scheduler(bot)

    try:
        logging.info("🚀 Бот запущен! Aiogram + Pyrogram работают.")
        await dp.start_polling(
            bot,
            allowed_updates=["message", "callback_query", "chat_member", "message_reaction"]
        )
    finally:
        await bot.session.close()
        if pyro.is_running:
            await pyro.stop()
        logging.info("🛑 Все клиенты остановлены.")


if __name__ == "__main__":
    asyncio.run(main())
