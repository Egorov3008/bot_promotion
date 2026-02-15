from datetime import datetime
from enum import Enum
from typing import Optional, List

from sqlalchemy import (
    Column, Integer, String, Text, DateTime, Boolean,
    ForeignKey, BigInteger, create_engine, UniqueConstraint
)
from sqlalchemy.orm import declarative_base
from sqlalchemy.orm import relationship, sessionmaker
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

Base = declarative_base()


class GiveawayStatus(Enum):
    """Статусы розыгрыша"""
    ACTIVE = "active"       # Активный розыгрыш
    FINISHED = "finished"   # Завершенный розыгрыш
    CANCELLED = "cancelled" # Отмененный розыгрыш


class Admin(Base):
    """Модель администраторов"""
    __tablename__ = "admins"
    
    id = Column(Integer, primary_key=True)
    user_id = Column(BigInteger, unique=True, nullable=False)  # Telegram User ID
    username = Column(String(255), nullable=True)
    first_name = Column(String(255), nullable=True)
    full_name = Column(String(255), nullable=True)
    is_main_admin = Column(Boolean, default=False)  # Главный админ
    created_at = Column(DateTime, default=datetime.utcnow)


class Channel(Base):
    """Модель каналов для розыгрышей"""
    __tablename__ = "channels"
    
    id = Column(Integer, primary_key=True)
    channel_id = Column(BigInteger, unique=True, nullable=False)  # Telegram Channel ID
    channel_name = Column(String(255), nullable=False)
    channel_username = Column(String(255), nullable=True)  # @channel_username
    added_by = Column(BigInteger, ForeignKey('admins.user_id'))
    created_at = Column(DateTime, default=datetime.utcnow)
    discussion_group_id = Column(Integer, nullable=True)
    
    # Связь с админом, который добавил канал
    admin = relationship("Admin", backref="channels")


class ChannelSubscriber(Base):
    """Модель подписчиков канала (все, кого добавили, пока бот был админом)"""
    __tablename__ = "channel_subscribers"

    id = Column(Integer, primary_key=True)
    channel_id = Column(BigInteger, nullable=False)  # ID канала
    user_id = Column(BigInteger, nullable=False)     # Telegram ID пользователя
    username = Column(String(255), nullable=True)
    full_name = Column(String(255), nullable=True)
    first_name = Column(String(255), nullable=True)
    added_at = Column(DateTime, default=datetime.utcnow)  # Время добавления
    left_at = Column(DateTime)
    last_activity_at = Column(DateTime, nullable=True)

    # Уникальность: один пользователь — одна запись на канал
    __table_args__ = (
        UniqueConstraint('channel_id', 'user_id', name='unique_channel_user'),
    )

class Giveaway(Base):
    """Модель розыгрыша"""
    __tablename__ = "giveaways"
    
    id = Column(Integer, primary_key=True)
    title = Column(String(255), nullable=False)  # Заголовок розыгрыша
    description = Column(Text, nullable=False)    # Описание розыгрыша
    message_winner = Column(Text, nullable=True)  # Сообщение победителю
    
    # Медиа файлы
    media_type = Column(String(50), nullable=True)  # photo, video, animation, document
    media_file_id = Column(String(255), nullable=True)  # Telegram file_id
    
    # Канал и сообщение
    channel_id = Column(BigInteger, ForeignKey('channels.channel_id'))
    message_id = Column(BigInteger, nullable=True)  # ID сообщения в канале
    
    # Временные метки
    start_time = Column(DateTime, default=datetime.utcnow)
    end_time = Column(DateTime, nullable=False)
    # period = Column(Integer, nullable=False)  # Период напоминания в часах
    
    # Статус и количество призовых мест
    status = Column(String(20), default=GiveawayStatus.ACTIVE.value)
    winner_places = Column(Integer, default=1)  # Количество призовых мест
    
    # Кто создал
    created_by = Column(BigInteger, ForeignKey('admins.user_id'))
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Связи
    channel = relationship("Channel", backref="giveaways")
    creator = relationship("Admin", backref="created_giveaways")

    @property
    def participants_count(self) -> int:
        return len(self.participants) if hasattr(self, 'participants') else 0


class Participant(Base):
    """Модель участников розыгрыша"""
    __tablename__ = "participants"
    
    id = Column(Integer, primary_key=True)
    giveaway_id = Column(Integer, ForeignKey('giveaways.id'), nullable=False)
    user_id = Column(BigInteger, nullable=False)
    username = Column(String(255), nullable=True)
    first_name = Column(String(255), nullable=True)
    full_name = Column(String(255), nullable=True)
    joined_at = Column(DateTime, default=datetime.utcnow)
    
    # Связь с розыгрышем
    giveaway = relationship("Giveaway", backref="participants")
    
    # Уникальный индекс: один пользователь - один розыгрыш
    __table_args__ = (
        {'sqlite_autoincrement': True},
    )


class Winner(Base):
    """Модель победителей розыгрыша"""
    __tablename__ = "winners"
    
    id = Column(Integer, primary_key=True)
    giveaway_id = Column(Integer, ForeignKey('giveaways.id'), nullable=False)
    user_id = Column(BigInteger, nullable=False)
    username = Column(String(255), nullable=True)
    first_name = Column(String(255), nullable=True)
    full_name = Column(String(255), nullable=True)
    place = Column(Integer, nullable=False)  # 1, 2, 3... место
    won_at = Column(DateTime, default=datetime.utcnow)
    
    # Связь с розыгрышем
    giveaway = relationship("Giveaway", backref="winners")
    
    # Уникальный индекс: одно место в одном розыгрыше
    __table_args__ = (
        {'sqlite_autoincrement': True},
    )


class MailingStatus(Enum):
    """Статусы массовой рассылки"""
    PENDING = "pending"     # Ожидает запуска
    SENDING = "sending"     # В процессе отправки
    DONE = "done"           # Завершена
    CANCELLED = "cancelled" # Отменена


class Mailing(Base):
    """Модель массовой рассылки"""
    __tablename__ = "mailings"

    id = Column(Integer, primary_key=True)
    channel_id = Column(BigInteger, ForeignKey('channels.channel_id'), nullable=False) # Канал, из которого берется аудитория
    admin_id = Column(BigInteger, ForeignKey('admins.user_id'), nullable=False)       # Кто запустил рассылку
    audience_type = Column(String(50), nullable=False) # "active_30d" / "all"

    message_text = Column(Text, nullable=False) # Текст рассылки

    total_users = Column(Integer, nullable=False) # Общее количество пользователей для рассылки
    sent_count = Column(Integer, default=0)       # Сколько отправлено успешно
    failed_count = Column(Integer, default=0)     # Сколько не удалось отправить (без blocked)
    blocked_count = Column(Integer, default=0)    # Сколько заблокировало бота

    status = Column(String(20), default=MailingStatus.PENDING.value)

    created_at = Column(DateTime, default=datetime.utcnow)
    finished_at = Column(DateTime, nullable=True) # Время завершения/отмены рассылки

    # Связи
    channel = relationship("Channel", backref="mailings")
    admin = relationship("Admin", backref="started_mailings")
