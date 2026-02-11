# database/cache.py
from aiocache import cached
from aiocache.base import BaseCache
from aiocache.decorators import cached

def cached_with_ttl(ttl: int, cache: BaseCache = None):
    """
    Декоратор для кэширования результатов асинхронных функций с TTL.
    По умолчанию использует In-memory кэш.

    Args:
        ttl (int): Время жизни кэша в секундах.
        cache (BaseCache): Опционально, можно передать настроенный экземпляр кэша aiocache.
                           Если None, используется In-memory кэш по умолчанию.
    """
    return cached(ttl=ttl, cache=cache)
