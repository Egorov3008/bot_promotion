from pyrogram import Client
import asyncio
import logging
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass
import random
from pyrogram.errors import UserBlocked, FloodWait, UserIsBlocked


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
        disable_web_page_preview: bool = False,
        max_retries: int = 3,
    ) -> Tuple[bool, str]:
        """
        Отправка сообщения одному пользователю с retry при FloodWait.

        Args:
            user_id: ID пользователя
            text: Текст сообщения
            parse_mode: Режим разметки (HTML, Markdown)
            disable_web_page_preview: Отключить превью ссылок
            max_retries: Максимальное количество повторных попыток при FloodWait

        Returns:
            Tuple[bool, str]: (успех, сообщение о результате)
        """
        for attempt in range(max_retries + 1):
            try:
                await self.client.send_message(
                    chat_id=user_id,
                    text=text,
                    parse_mode=parse_mode,
                    disable_web_page_preview=disable_web_page_preview
                )
                return True, "SUCCESS"
            except UserBlocked:
                self.logger.warning(f"Пользователь {user_id} заблокировал бота.")
                return False, "USER_BLOCKED"
            except UserIsBlocked:
                self.logger.warning(f"Сообщения для пользователя {user_id} заблокированы.")
                return False, "USER_IS_BLOCKED"
            except FloodWait as e:
                if attempt < max_retries:
                    self.logger.warning(
                        f"FloodWait для {user_id}: пауза {e.value} сек (попытка {attempt + 1}/{max_retries})"
                    )
                    await asyncio.sleep(e.value)
                else:
                    self.logger.warning(
                        f"FloodWait для {user_id}: исчерпаны попытки после {e.value} сек ожидания."
                    )
                    return False, f"FLOOD_WAIT:{e.value}"
            except Exception as e:
                self.logger.error(f"Неизвестная ошибка при отправке сообщения {user_id}: {e}")
                return False, f"OTHER_ERROR:{e}"
        return False, "MAX_RETRIES_EXCEEDED"

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
                if message == "USER_BLOCKED" or message == "USER_IS_BLOCKED":
                    stats.blocked += 1
                elif message.startswith("FLOOD_WAIT"):
                    stats.throttled += 1
                    try:
                        wait_time = int(message.split(":")[1])
                        await asyncio.sleep(wait_time)
                    except (ValueError, IndexError):
                        await asyncio.sleep(30) # Default to 30 seconds if parse fails
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
                if message == "USER_BLOCKED" or message == "USER_IS_BLOCKED":
                    stats.blocked += 1
                elif message.startswith("FLOOD_WAIT"):
                    stats.throttled += 1
                    try:
                        wait_time = int(message.split(":")[1])
                        await asyncio.sleep(wait_time)
                    except (ValueError, IndexError):
                        await asyncio.sleep(30) # Default to 30 seconds if parse fails
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
