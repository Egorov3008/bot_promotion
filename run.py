import asyncio
import logging
import sys
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import BotCommand

from config import config
from database.database import init_db
from handlers import setup_handlers
from middlewares.auth import AdminMiddleware
from utils.scheduler import setup_scheduler
from utils.pyro_client import setup_pyrogram, pyro_client


async def main():
    # Настройка логирования
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler('bot.log', encoding='utf-8'),
            logging.StreamHandler(sys.stdout)
        ]
    )

    # Инициализация aiogram бота
    bot = Bot(
        token=config.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )

    # Установка команд
    try:
        await bot.set_my_commands([
            BotCommand(command="start", description="Запуск и перезапуск бота"),
            BotCommand(command="clear", description="Очистить диалог"),
        ])
    except Exception as e:
        logging.error(f"Ошибка установки команд: {e}")

    dp = Dispatcher()

    # Инициализация базы данных
    await init_db()

    # Подключение middleware
    dp.message.middleware(AdminMiddleware())
    dp.callback_query.middleware(AdminMiddleware())

    # Регистрация хендлеров
    setup_handlers(dp)

    # === Запуск Pyrogram клиента ===
    pyro = setup_pyrogram(config)
    pyro_task = asyncio.create_task(pyro.start())  # Запускаем параллельно

    # Ждём, пока Pyrogram запустится
    await asyncio.sleep(2)

    # === Запуск планировщика (использует aiogram bot) ===
    await setup_scheduler(bot)

    try:
        logging.info("🚀 Бот запущен! Aiogram + Pyrogram работают параллельно.")
        # Запуск aiogram polling
        await dp.start_polling(
            bot,
            allowed_updates=["message", "callback_query", "chat_member", "message_reaction"]
        )
    finally:
        # Корректная остановка
        await bot.session.close()
        if pyro_client and pyro_client.is_running:
            await pyro_client.stop()
        logging.info("🛑 Все клиенты остановлены.")


if __name__ == "__main__":
    asyncio.run(main())