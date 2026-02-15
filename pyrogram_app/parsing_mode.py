"""
Модуль парсинга каналов и мониторинга активности пользователей.
Отвечает за: сбор подписчиков, проверка активности, отслеживание реакций.
"""
import asyncio
import logging
from typing import Dict, List, Optional, Tuple, Any, Callable
from dataclasses import dataclass
from datetime import datetime

from pyrogram import Client
from pyrogram.errors import FloodWait, BadRequest
from pyrogram.enums import ChatMemberStatus

from utils.channel_parser import (
    parse_channel_subscribers, 
    check_pyrogram_client_admin_rights
)


@dataclass
class ParsingStats:
    """Статистика парсинга канала"""
    total_processed: int = 0
    with_username: int = 0
    without_username: int = 0
    bots_count: int = 0
    added: int = 0
    updated: int = 0
    start_time: datetime = None
    end_time: datetime = None
    
    def duration_seconds(self) -> float:
        if self.start_time and self.end_time:
            return (self.end_time - self.start_time).total_seconds()
        return 0.0


@dataclass
class SubscriberInfo:
    """Информация о подписчике канала"""
    user_id: int
    first_name: str
    username: Optional[str]
    is_bot: bool = False
    last_seen: datetime = None
    is_active: bool = True


class ParsingMode:
    """
    Класс для парсинга каналов и мониторинга активности пользователей.
    
    Основные функции:
    - Полный парсинг подписчиков канала
    - Инкрементальное обновление (добавление новых подписчиков)
    - Проверка активности пользователей
    - Мониторинг реакций и взаимодействий
    """
    
    def __init__(self, pyro_client: Client):
        """
        Инициализация парсера.
        
        Args:
            pyro_client: Запущенный экземпляр Pyrogram Client
        """
        self.client = pyro_client
        self.logger = logging.getLogger(__name__)
        self._stop_event = asyncio.Event()
    
    async def check_admin_rights(self, channel_id: int) -> Tuple[bool, str]:
        """
        Проверка прав администратора в канале.
        
        Args:
            channel_id: ID канала
            
        Returns:
            Tuple[bool, str]: (есть ли права, сообщение о статусе)
        """
        has_rights = await check_pyrogram_client_admin_rights(
            self.client, channel_id
        )
        
        if has_rights:
            return True, "✅ Бот имеет права администратора"
        else:
            return False, "❌ У бота нет прав администратора в канале"
    
    async def parse_full(
        self, 
        channel_id: int,
        progress_callback: Optional[Callable[[ParsingStats], None]] = None
    ) -> Tuple[List[Dict], ParsingStats]:
        """
        Полный парсинг всех подписчиков канала.
        
        Args:
            channel_id: ID канала
            progress_callback: Опциональный callback для обновления прогресса
            
        Returns:
            Tuple[List[Dict], ParsingStats]: (список подписчиков, статистика)
        """
        stats = ParsingStats(start_time=datetime.now())
        
        self.logger.info(f"Начинаем полный парсинг канала {channel_id}")
        
        try:
            subscribers, with_username_count, bots_count = await parse_channel_subscribers(
                client=self.client,
                channel_id=channel_id
            )
            
            # Обновляем статистику
            stats.total_processed = len(subscribers) + bots_count
            stats.with_username = len(subscribers)
            stats.bots_count = bots_count
            stats.end_time = datetime.now()
            
            self.logger.info(
                f"Парсинг канала {channel_id} завершён: "
                f"всего={stats.total_processed}, "
                f"с username={stats.with_username}, "
                f"ботов={stats.bots_count}"
            )
            
            # Вызываем callback если передан
            if progress_callback:
                await progress_callback(stats)
            
            return subscribers, stats
            
        except ValueError as e:
            self.logger.error(f"Ошибка прав доступа: {e}")
            stats.end_time = datetime.now()
            raise
        except Exception as e:
            self.logger.error(f"Критическая ошибка при парсинге: {e}")
            stats.end_time = datetime.now()
            raise
    
    async def parse_incremental(
        self,
        channel_id: int,
        known_users: List[int],
        batch_size: int = 100
    ) -> Tuple[List[Dict], ParsingStats]:
        """
        Инкрементальный парсинг - добавление только новых подписчиков.
        
        Эффективен для обновления базы без полного перебора канала.
        
        Args:
            channel_id: ID канала
            known_users: Список известных user_id
            batch_size: Размер пакета для обработки
            
        Returns:
            Tuple[List[Dict], ParsingStats]: (новые подписчики, статистика)
        """
        stats = ParsingStats(start_time=datetime.now())
        known_set = set(known_users)
        new_subscribers = []
        
        self.logger.info(
            f"Начинаем инкрементальный парсинг канала {channel_id}. "
            f"Известных пользователей: {len(known_set)}"
        )
        
        try:
            async for member in self.client.get_chat_members(chat_id=channel_id):
                user = member.user
                
                if user.id in known_set:
                    continue
                
                if user.is_bot:
                    stats.bots_count += 1
                    continue
                
                subscriber = {
                    "user_id": user.id,
                    "first_name": user.first_name,
                    "username": user.username
                }
                
                new_subscribers.append(subscriber)
                stats.with_username += 1
                stats.total_processed += 1
                
                # Небольшая задержка для Rate Limits
                if len(new_subscribers) % batch_size == 0:
                    await asyncio.sleep(0.1)
                    self.logger.debug(f"Обработано {len(new_subscribers)} новых пользователей")
            
            stats.end_time = datetime.now()
            
            self.logger.info(
                f"Инкрементальный парсинг завершён: найдено {len(new_subscribers)} новых"
            )
            
            return new_subscribers, stats
            
        except FloodWait as e:
            self.logger.warning(f"FloodWait при инкрементальном парсинге: {e.value} сек")
            await asyncio.sleep(e.value + 1)
            stats.end_time = datetime.now()
            return new_subscribers, stats
        except Exception as e:
            self.logger.error(f"Ошибка при инкрементальном парсинге: {e}")
            stats.end_time = datetime.now()
            raise
    
    async def get_channel_members_count(self, channel_id: int) -> int:
        """
        Получение количества участников канала.
        
        Args:
            channel_id: ID канала
            
        Returns:
            int: Количество участников
        """
        try:
            chat = await self.client.get_chat(chat_id=channel_id)
            return chat.members_count or 0
        except Exception as e:
            self.logger.error(f"Не удалось получить количество участников: {e}")
            return 0
    
    async def get_member_info(self, channel_id: int, user_id: int) -> Optional[Dict]:
        """
        Получение информации о конкретном участнике канала.
        
        Args:
            channel_id: ID канала
            user_id: ID пользователя
            
        Returns:
            Optional[Dict]: Информация о пользователе или None
        """
        try:
            member = await self.client.get_chat_member(
                chat_id=channel_id,
                user_id=user_id
            )
            
            return {
                "user_id": member.user.id,
                "first_name": member.user.first_name,
                "username": member.user.username,
                "status": member.status.value,
                "joined_date": member.joined_date.isoformat() if member.joined_date else None
            }
        except BadRequest as e:
            self.logger.warning(f"Пользователь {user_id} не в канале: {e}")
            return None
        except Exception as e:
            self.logger.error(f"Ошибка получения инфо о пользователе {user_id}: {e}")
            return None
    
    async def check_user_activity(
        self,
        channel_id: int,
        user_ids: List[int],
        check_reactions: bool = True
    ) -> Dict[int, Dict[str, Any]]:
        """
        Проверка активности списка пользователей.
        
        Args:
            channel_id: ID канала
            user_ids: Список ID пользователей для проверки
            check_reactions: Проверять ли реакции на последние сообщения
            
        Returns:
            Dict[int, Dict]: Словарь user_id -> информация об активности
        """
        activity_report = {}
        
        self.logger.info(f"Проверка активности {len(user_ids)} пользователей")
        
        for user_id in user_ids:
            try:
                member_info = await self.get_member_info(channel_id, user_id)
                
                if member_info:
                    # Проверяем статус участника
                    is_active = member_info["status"] in [
                        ChatMemberStatus.ADMINISTRATOR.value,
                        ChatMemberStatus.MEMBER.value,
                        ChatMemberStatus.OWNER.value
                    ]
                    
                    activity_report[user_id] = {
                        "in_channel": True,
                        "is_active": is_active,
                        "status": member_info["status"],
                        "username": member_info.get("username"),
                        "first_name": member_info.get("first_name"),
                        "last_seen": member_info.get("joined_date")
                    }
                else:
                    activity_report[user_id] = {
                        "in_channel": False,
                        "is_active": False,
                        "status": "left",
                        "username": None,
                        "first_name": None,
                        "last_seen": None
                    }
                    
            except Exception as e:
                self.logger.warning(f"Ошибка проверки пользователя {user_id}: {e}")
                activity_report[user_id] = {
                    "in_channel": False,
                    "is_active": False,
                    "status": "error",
                    "error": str(e)
                }
        
        return activity_report
    
    async def get_recent_message_reactions(
        self,
        channel_id: int,
        message_id: int
    ) -> Dict[str, List[int]]:
        """
        Получение реакций на конкретное сообщение.
        
        Args:
            channel_id: ID канала
            message_id: ID сообщения
            
        Returns:
            Dict[str, List[int]]: Словарь emoji -> список user_id
        """
        try:
            message = await self.client.get_messages(
                chat_id=channel_id,
                message_ids=message_id
            )
            
            if not message or not message.reactions:
                return {}
            
            reactions = {}
            for reaction in message.reactions.results:
                emoji = getattr(reaction, 'emoji', None) or str(reaction)
                user_ids = [
                    peer.user_id for peer in getattr(reaction, 'peer_ids', [])
                ]
                reactions[emoji] = user_ids
            
            return reactions
            
        except Exception as e:
            self.logger.error(f"Ошибка получения реакций: {e}")
            return {}
    
    async def get_channel_info(self, channel_id: int) -> Optional[Dict]:
        """
        Получение полной информации о канале.
        
        Args:
            channel_id: ID канала
            
        Returns:
            Optional[Dict]: Информация о канале или None
        """
        try:
            chat = await self.client.get_chat(chat_id=channel_id)
            
            return {
                "id": chat.id,
                "title": chat.title,
                "username": chat.username,
                "members_count": chat.members_count,
                "description": chat.description,
                "is_verified": chat.is_verified,
                "is_scam": chat.is_scam,
                "is_fake": chat.is_fake,
                "dc_id": chat.dc_id
            }
        except Exception as e:
            self.logger.error(f"Ошибка получения инфо о канале: {e}")
            return None
    
    async def parse_full_batched(
        self,
        channel_id: int,
        batch_size: int = 200,
        progress_callback: Optional[Callable] = None,
    ) -> Tuple[List[Dict], ParsingStats]:
        """
        Полный парсинг с батчевой обработкой, прогрессом и возможностью отмены.

        Args:
            channel_id: ID канала
            batch_size: Размер пакета (по умолчанию 200 — размер страницы API)
            progress_callback: async callback(stats, total) для обновления прогресса

        Returns:
            Tuple[List[Dict], ParsingStats]: (список подписчиков, статистика)
        """
        self._stop_event.clear()
        stats = ParsingStats(start_time=datetime.now())
        subscribers: List[Dict] = []

        total = await self.get_channel_members_count(channel_id)
        self.logger.info(
            f"Начинаем батчевый парсинг канала {channel_id}, "
            f"всего участников: {total}"
        )

        try:
            async for member in self.client.get_chat_members(chat_id=channel_id):
                if self._stop_event.is_set():
                    self.logger.info("Парсинг остановлен по запросу")
                    break

                user = member.user

                if user.is_bot:
                    stats.bots_count += 1
                    stats.total_processed += 1
                else:
                    subscriber = {
                        "user_id": user.id,
                        "first_name": user.first_name or "",
                        "last_name": user.last_name or "",
                        "username": user.username,
                    }
                    subscribers.append(subscriber)
                    stats.total_processed += 1
                    if user.username:
                        stats.with_username += 1
                    else:
                        stats.without_username += 1

                # Каждые batch_size — прогресс, проверка стопа, пауза
                if stats.total_processed % batch_size == 0:
                    if progress_callback:
                        try:
                            await progress_callback(stats, total)
                        except Exception as e:
                            self.logger.warning(f"Ошибка в progress_callback: {e}")

                    if self._stop_event.is_set():
                        self.logger.info("Парсинг остановлен по запросу")
                        break

                    await asyncio.sleep(1)

        except FloodWait as e:
            self.logger.warning(f"FloodWait: ожидание {e.value} сек")
            await asyncio.sleep(e.value + 1)
            # Возвращаем то что успели собрать
        except Exception as e:
            self.logger.error(f"Ошибка при батчевом парсинге: {e}")
            stats.end_time = datetime.now()
            raise

        stats.end_time = datetime.now()

        self.logger.info(
            f"Батчевый парсинг канала {channel_id} завершён: "
            f"собрано={len(subscribers)}, ботов={stats.bots_count}, "
            f"обработано={stats.total_processed}"
        )

        # Финальный callback
        if progress_callback:
            try:
                await progress_callback(stats, total)
            except Exception:
                pass

        return subscribers, stats

    def stop(self):
        """Остановка фоновых задач парсинга"""
        self._stop_event.set()
        self.logger.info("Парсинг остановлен")


# Алиас для обратной совместимости
UserParser = ParsingMode