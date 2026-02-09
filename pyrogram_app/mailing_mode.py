from pyrogram import Client
import asyncio
import logging
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass
import random


@dataclass
class MailingStats:
    """Статистика рассылки"""
    total_sent: int = 0
    successful: int = 0
    failed: int = 0
    blocked: int = 0
    throttled: int = 0
    other_errors: int = 0
    start_time: float = 0.0
    end_time: float = 0.0
    
    def duration_seconds(self) -> float:
        return self.end_time - self.start_time if self.end_time else 0.0
    
    def success_rate(self) -> float:
        return (self.successful / self.total_sent * 100) if self.total_sent > 0 else 0.0

class MailingMode:
    """
    Класс для массовой рассылки сообщений пользователям.
    
    Основные функции:
    - Массовая отправка сообщений списку пользователей
    - Обработка ошибок и блокировок
    - Поддержка различных типов сообщений
    - Регулирование скорости отправки
    """
    
    def __init__(self, pyro_client: Client, delay_range: Tuple[float, float] = (1.0, 3.0)):
        """
        Инициализация рассылочного режима.
        
        Args:
            pyro_client: Запущенный экземпляр Pyrogram Client
            delay_range: Диапазон задержки между отправками (min, max) в секундах
        """
        self.client = pyro_client
        self.logger = logging.getLogger(__name__)
        self.delay_min, self.delay_max = delay_range
        self._stop_event = asyncio.Event()
    
    async def send_message_to_user(
        self,
        user_id: int,
        text: str,
        parse_mode: Optional[str] = None,
        disable_web_page_preview: bool = False
    ) -> Tuple[bool, str]:
        """
        Отправка сообщения одному пользователю.
        
        Args:
            user_id: ID пользователя
            text: Текст сообщения
            parse_mode: Режим разметки (HTML, Markdown)
            disable_web_page_preview: Отключить превью ссылок
        
        Returns:
            Tuple[bool, str]: (успех, сообщение о результате)
        """
        try:
            await self.client.send_message(
                chat_id=user_id,
                text=text,
                parse_mode=parse_mode,
                disable_web_page_preview=disable_web_page_preview
            )
            return True, "Успешно отправлено"
            
        except Exception as e:
            error_msg = str(e).lower()
            
            if "blocked" in error_msg or "bot was blocked" in error_msg:
                return False, "Пользователь заблокировал бота"
            elif "flood" in error_msg or "too many requests" in error_msg:
                return False, "Превышен лимит запросов (Flood Wait)"
            elif "private" in error_msg or "need to accept the privacy policy" in error_msg:
                return False, "Аккаунт приватный или требует принятия политики конфиденциальности"
            elif "user is deactivated" in error_msg:
                return False, "Пользователь деактивирован"
            else:
                return False, f"Неизвестная ошибка: {e}"
    
    async def send_bulk_messages(
        self,
        user_ids: List[int],
        text: str,
        parse_mode: Optional[str] = None,
        disable_web_page_preview: bool = False,
        randomize_order: bool = True,
        progress_callback: Optional[callable] = None
    ) -> MailingStats:
        """
        Массовая рассылка сообщений пользователям.
        
        Args:
            user_ids: Список ID пользователей
            text: Текст сообщения для всех
            parse_mode: Режим разметки
            disable_web_page_preview: Отключить превью ссылок
            randomize_order: Перемешивать ли порядок пользователей
            progress_callback: Функция для обновления прогресса
        
        Returns:
            MailingStats: Статистика рассылки
        """
        stats = MailingStats()
        stats.start_time = asyncio.get_event_loop().time()
        
        if randomize_order:
            user_ids = user_ids.copy()
            random.shuffle(user_ids)
        
        self.logger.info(f"Начинаем массовую рассылку {len(user_ids)} пользователям")
        
        for i, user_id in enumerate(user_ids):
            # Проверка на остановку
            if self._stop_event.is_set():
                self.logger.info(f"Рассылка остановлена на {i}/{len(user_ids)} пользователей")
                break
            
            stats.total_sent += 1
            
            success, message = await self.send_message_to_user(
                user_id=user_id,
                text=text,
                parse_mode=parse_mode,
                disable_web_page_preview=disable_web_page_preview
            )
            
            if success:
                stats.successful += 1
            else:
                stats.failed += 1
                if "blocked" in message.lower():
                    stats.blocked += 1
                elif "flood" in message.lower():
                    stats.throttled += 1
                    # Дополнительная задержка при флуде
                    await asyncio.sleep(30)
                else:
                    stats.other_errors += 1
            
            # Обновление прогресса
            if progress_callback and (i + 1) % 10 == 0:
                await progress_callback(i + 1, len(user_ids), stats)
            
            # Случайная задержка между отправками
            delay = random.uniform(self.delay_min, self.delay_max)
            await asyncio.sleep(delay)
            
            # Дополнительная задержка каждые 50 сообщений
            if (i + 1) % 50 == 0:
                extra_delay = random.uniform(10, 20)
                self.logger.debug(f"Дополнительная задержка {extra_delay:.1f} сек после {i+1} сообщений")
                await asyncio.sleep(extra_delay)

        stats.end_time = asyncio.get_event_loop().time()
        self.logger.info(f"Рассылка завершена. Успешно: {stats.successful}/{stats.total_sent}")
        
        return stats
    
    async def send_personalized_messages(
        self,
        user_messages: List[Dict[str, any]],
        delay_range: Tuple[float, float] = None,
        progress_callback: Optional[callable] = None
    ) -> MailingStats:
        """
        Отправка персонализированных сообщений пользователям.
        
        Args:
            user_messages: Список словарей с ключами 'user_id', 'text', 'parse_mode'
            delay_range: Диапазон задержки (переопределяет self.delay_range)
            progress_callback: Функция для обновления прогресса
        
        Returns:
            MailingStats: Статистика рассылки
        """
        stats = MailingStats()
        stats.start_time = asyncio.get_event_loop().time()
        
        # Перемешиваем для обхода ограничений
        user_messages = user_messages.copy()
        random.shuffle(user_messages)
        
        current_delay_min, current_delay_max = self.delay_min, self.delay_max
        if delay_range:
            current_delay_min, current_delay_max = delay_range
        
        self.logger.info(f"Начинаем персонализированную рассылку {len(user_messages)} сообщений")
        
        for i, msg_data in enumerate(user_messages):
            # Проверка на остановку
            if self._stop_event.is_set():
                self.logger.info(f"Рассылка остановлена на {i}/{len(user_messages)} сообщениях")
                break
            
            user_id = msg_data.get('user_id')
            text = msg_data.get('text', '')
            parse_mode = msg_data.get('parse_mode')
            disable_preview = msg_data.get('disable_web_page_preview', False)
            
            if not user_id or not text:
                stats.failed += 1
                stats.other_errors += 1
                continue
                
            stats.total_sent += 1
            
            success, message = await self.send_message_to_user(
                user_id=user_id,
                text=text,
                parse_mode=parse_mode,
                disable_web_page_preview=disable_preview
            )
            
            if success:
                stats.successful += 1
            else:
                stats.failed += 1
                if "blocked" in message.lower():
                    stats.blocked += 1
                elif "flood" in message.lower():
                    stats.throttled += 1
                    # Дополнительная задержка при флуде
                    await asyncio.sleep(30)
                else:
                    stats.other_errors += 1
            
            # Обновление прогресса
            if progress_callback and (i + 1) % 10 == 0:
                await progress_callback(i + 1, len(user_messages), stats)
            
            # Случайная задержка между отправками
            delay = random.uniform(current_delay_min, current_delay_max)
            await asyncio.sleep(delay)
            
            # Дополнительная задержка каждые 50 сообщений
            if (i + 1) % 50 == 0:
                extra_delay = random.uniform(10, 20)
                self.logger.debug(f"Дополнительная задержка {extra_delay:.1f} сек после {i+1} сообщений")
                await asyncio.sleep(extra_delay)

        stats.end_time = asyncio.get_event_loop().time()
        self.logger.info(f"Персонализированная рассылка завершена. Успешно: {stats.successful}/{stats.total_sent}")
        
        return stats
        
    async def estimate_delivery_time(
        self,
        user_count: int,
        delay_range: Tuple[float, float] = None
    ) -> float:
        """
        Оценка времени доставки рассылки.
        
        Args:
            user_count: Количество пользователей
            delay_range: Диапазон задержки (min, max)
        
        Returns:
            float: Оценочное время в секундах
        """
        if delay_range is None:
            delay_range = (self.delay_min, self.delay_max)
            
        avg_delay = sum(delay_range) / 2
        base_time = user_count * avg_delay
        
        # Дополнительное время на дополнительные задержки каждые 50 сообщений
        extra_delays = (user_count // 50)
        extra_time = extra_delays * 15  # Средняя дополнительная задержка
        
        return base_time + extra_time
    
    def stop(self):
        """Остановка фоновых задач рассылки"""
        self._stop_event.set()
        self.logger.info("Рассылка остановлена")
