"""
pyrogram_app - Модуль для работы с Telegram User Bot через Pyrogram

Компоненты:
- PyrogramClient: Основной класс-обёртка для инициализации и управления Client
- ParsingMode: Парсинг каналов и мониторинг активности пользователей
- MailingMode: Массовая рассылка сообщений

Пример использования:
    from pyrogram_app.pyro_client import setup_pyrogram, get_pyrogram_client
    from pyrogram_app.parsing_mode import ParsingMode
    from pyrogram_app.mailing_mode import MailingMode
    
    # Инициализация
    pyro = setup_pyrogram(config)
    await pyro.start()
    
    # Получение клиента
    client = pyro.export()
    
    # Использование режимов
    parser = ParsingMode(client)
    mailer = MailingMode(client)
"""

from .pyro_client import (
    PyrogramClient,
    setup_pyrogram,
    get_pyrogram_client
)

from .parsing_mode import (
    ParsingMode,
    ParsingStats,
    SubscriberInfo,
    UserParser  # Алиас для обратной совместимости
)

from .mailing_mode import (
    MailingMode,
    MailingStats
)

__all__ = [
    # PyrogramClient
    "PyrogramClient",
    "setup_pyrogram",
    "get_pyrogram_client",
    
    # ParsingMode
    "ParsingMode",
    "ParsingStats",
    "SubscriberInfo",
    "UserParser",
    
    # MailingMode
    "MailingMode",
    "MailingStats",
]
