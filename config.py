"""
Конфигурация бота - загрузка переменных окружения
"""
import os
from dotenv import load_dotenv

# Загружаем переменные из .env файла
load_dotenv()



class Config:
    def __init__(self):
        # === Aiogram Bot ===
        self.BOT_TOKEN = os.getenv("BOT_TOKEN")
        self.MAIN_ADMIN_ID = int(os.getenv("MAIN_ADMIN_ID", 0))
        self.DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///giveaway_bot.db")
        self.TIMEZONE = os.getenv("TIMEZONE", "Europe/Moscow")

        # === Pyrogram Client ===
        self.API_ID = os.getenv("API_ID")
        self.API_HASH = os.getenv("API_HASH")
        self.PHONE_NUMBER = os.getenv("PHONE_NUMBER")
        self.SESSION_NAME = os.getenv("SESSION_NAME", "pyrogram_session")

        # Проверки
        if not self.BOT_TOKEN:
            raise ValueError("BOT_TOKEN не найден!")
        if not self.MAIN_ADMIN_ID:
            raise ValueError("MAIN_ADMIN_ID не найден!")
        if not self.API_ID or not self.API_HASH or not self.PHONE_NUMBER:
            raise ValueError("Для Pyrogram нужны: API_ID, API_HASH, PHONE_NUMBER")

config = Config()