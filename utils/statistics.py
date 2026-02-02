"""
Модуль для формирования статистики по розыгрышам и каналам.
"""

from datetime import datetime, timedelta, timezone
from typing import Dict, Optional

from database.database import (
    get_giveaway,
    get_participants_count,
    get_active_giveaways,
    get_finished_giveaways,
    get_all_channels,
    get_channel_subscribers_count,
)
from utils.datetime_utils import format_datetime


async def generate_giveaway_report(giveaway_id: int) -> Optional[Dict]:
    """
    Формирует подробный отчет по одному розыгрышу.

    Args:
        giveaway_id: ID розыгрыша

    Returns:
        Словарь с данными отчёта или None, если розыгрыш не найден
    """
    giveaway = await get_giveaway(giveaway_id)
    if not giveaway:
        return None

    participants_count = await get_participants_count(giveaway_id)
    channel_subscribers_count = await get_channel_subscribers_count(giveaway.channel_id)

    # Процент участников от подписчиков
    participation_rate = 0
    if channel_subscribers_count > 0:
        participation_rate = round((participants_count / channel_subscribers_count) * 100, 2)

    # Продолжительность розыгрыша
    duration_hours = round((giveaway.end_time - giveaway.start_time).total_seconds() / 3600, 1)

    report = {
        "id": giveaway.id,
        "title": giveaway.title,
        "status": giveaway.status.value,
        "start_time": format_datetime(giveaway.start_time),
        "end_time": format_datetime(giveaway.end_time),
        "duration_hours": duration_hours,
        "channel": {
            "name": giveaway.channel.channel_name,
            "username": giveaway.channel.channel_username,
        },
        "created_by": {
            "username": giveaway.creator.username,
            "first_name": giveaway.creator.first_name,
        },
        "settings": {
            "winner_places": giveaway.winner_places,
            "media_type": giveaway.media_type,
        },
        "statistics": {
            "participants": participants_count,
            "subscribers_at_end": channel_subscribers_count,
            "participation_rate": participation_rate,
        },
        "winners": []
    }

    # Добавляем победителей, если есть
    if giveaway.status == "finished" and giveaway.winners:
        for winner in sorted(giveaway.winners, key=lambda w: w.place):
            report["winners"].append({
                "place": winner.place,
                "user_id": winner.user_id,
                "username": winner.username,
                "first_name": winner.first_name,
            })

    return report


async def generate_channel_report(channel_id: int, days: int = 30) -> Optional[Dict]:
    """
    Формирует отчёт по активности в канале за последние N дней.

    Args:
        channel_id: ID канала
        days: Количество дней для анализа (по умолчанию 30)

    Returns:
        Словарь с данными отчёта
    """

    now = datetime.now(timezone.utc)
    start_date = now - timedelta(days=days)

    # Получаем канал
    channels = await get_all_channels()
    channel = next((c for c in channels if c.channel_id == channel_id), None)
    if not channel:
        return None

    # Получаем количество подписчиков на начало и конец периода
    # (в реальной реализации нужно хранить историю подписчиков)
    # Здесь используем текущее значение как приближённое
    subscribers_start = await get_channel_subscribers_count(channel_id, as_of=start_date)
    subscribers_end = await get_channel_subscribers_count(channel_id)

    new_subscribers = max(0, subscribers_end - subscribers_start)

    # Активные и завершённые розыгрыши за период
    finished_giveaways = [g for g in await get_finished_giveaways()
                          if g.channel_id == channel_id and g.end_time >= start_date]

    active_giveaways = [g for g in await get_active_giveaways()
                        if g.channel_id == channel_id]

    total_participants = 0
    avg_participation_rate = 0
    total_winners = 0

    participation_rates = []

    for gw in finished_giveaways:
        count = await get_participants_count(gw.id)
        total_participants += count
        subs_at_time = await get_channel_subscribers_count(channel_id, as_of=gw.end_time)
        rate = (count / subs_at_time * 100) if subs_at_time > 0 else 0
        participation_rates.append(rate)

    if participation_rates:
        avg_participation_rate = round(sum(participation_rates) / len(participation_rates), 2)

    total_winners = sum(len(gw.winners) for gw in finished_giveaways if gw.winners)

    return {
        "channel": {
            "id": channel.id,
            "channel_id": channel.channel_id,
            "name": channel.channel_name,
            "username": channel.channel_username,
            "added_by": {
                "username": channel.admin.username,
                "first_name": channel.admin.first_name,
            }
        },
        "period": {
            "days": days,
            "start_date": format_datetime(start_date),
            "end_date": format_datetime(now)
        },
        "subscribers": {
            "start": subscribers_start,
            "end": subscribers_end,
            "growth": new_subscribers,
            "growth_rate": round((new_subscribers / subscribers_start * 100), 2) if subscribers_start > 0 else 0
        },
        "giveaways": {
            "active": len(active_giveaways),
            "finished_in_period": len(finished_giveaways),
            "total_participants": total_participants,
            "avg_participation_rate": avg_participation_rate,
            "total_winners": total_winners
        },
        "engagement_score": round(
            (avg_participation_rate * (1 + (new_subscribers / subscribers_end if subscribers_end > 0 else 0))) / 2, 2
        ) if participation_rates else 0
    }


async def generate_overall_report(days: int = 30) -> Dict:
    """
    Формирует общий отчёт по всем каналам и розыгрышам за период.

    Args:
        days: Количество дней для анализа

    Returns:
        Словарь с общими метриками
    """
    now = datetime.now(timezone.utc)
    start_date = now - timedelta(days=days)

    channels = await get_all_channels()
    all_finished = await get_finished_giveaways()
    all_active = await get_active_giveaways()

    period_finished = [g for g in all_finished if g.end_time >= start_date]

    total_subscribers = 0
    total_new_subscribers = 0
    total_participants = 0
    participation_rates = []

    for channel in channels:
        current_subs = await get_channel_subscribers_count(channel.channel_id)
        start_subs = await get_channel_subscribers_count(channel.channel_id, as_of=start_date)

        total_subscribers += current_subs
        total_new_subscribers += max(0, current_subs - start_subs)

        for gw in [g for g in period_finished if g.channel_id == channel.channel_id]:
            count = await get_participants_count(gw.id)
            total_participants += count
            rate = (count / current_subs * 100) if current_subs > 0 else 0
            participation_rates.append(rate)

    avg_participation_rate = round(sum(participation_rates) / len(participation_rates), 2) if participation_rates else 0

    return {
        "period": {
            "days": days,
            "start_date": format_datetime(start_date),
            "end_date": format_datetime(now)
        },
        "overall": {
            "total_channels": len(channels),
            "total_subscribers": total_subscribers,
            "new_subscribers": total_new_subscribers,
            "growth_rate": round((total_new_subscribers / (total_subscribers - total_new_subscribers) * 100), 2)
            if total_subscribers > total_new_subscribers else 0,
            "active_giveaways": len(all_active),
            "finished_giveaways": len(period_finished),
            "total_participants": total_participants,
            "avg_participation_rate": avg_participation_rate,
            "engagement_index": round(avg_participation_rate * (1 + (total_new_subscribers / total_subscribers)), 2)
            if total_subscribers > 0 else 0
        }
    }
