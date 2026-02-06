import logging
import logging
import random
from datetime import datetime, timedelta, timezone
from typing import Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.date import DateTrigger

from config import config
from database.database import get_active_giveaways, finish_giveaway, get_participants, delete_finished_older_than, \
    get_participants_count, get_channel, get_giveaway
from database.models import Channel
from texts.messages import REMINDER_POST_TEMPLATE, MESSAGES
from utils.datetime_utils import format_datetime
from utils.keyboards import get_participate_keyboard, get_winers_keyboard

scheduler = AsyncIOScheduler(timezone=timezone.utc)

# Словарь для хранения настроек напоминаний по розыгрышам
REMINDER_SETTINGS = {
    # giveaway_id: {
    #   "enabled": bool,
    #   "reminded_3d": False,
    #   "reminded_1d": False,
    #   "reminded_3h": False
    # }
}


# utils/scheduler.py

from datetime import datetime, timezone
from database.database import get_active_giveaways
from .datetime_utils import parse_datetime  # убедитесь, что возвращает tz-aware

async def setup_scheduler(bot):
    scheduler = AsyncIOScheduler(timezone="UTC")

    active_giveaways = await get_active_giveaways()

    for giveaway in active_giveaways:
        # Приводим end_time к offset-aware
        if giveaway.end_time.tzinfo is None:
            end_time = giveaway.end_time.replace(tzinfo=timezone.utc)
        else:
            end_time = giveaway.end_time

        now = datetime.now(timezone.utc)

        if end_time > now:
            delay = (end_time - now).total_seconds()
            scheduler.add_job(
                finish_giveaway_task,
                'date',
                run_date=end_time,
                args=[bot, giveaway.id],
                id=f"giveaway_{giveaway.id}"
            )
            # Планируем напоминания
            await schedule_reminders(bot, giveaway)

    # Ежедневная очистка
    scheduler.add_job(
        cleanup_old_finished,
        'interval',
        days=1,
        args=[15]
    )

    scheduler.start()
    logging.info(f"✅ Планировщик запущен. Запланировано активных розыгрышей: {len(active_giveaways)}")

def schedule_giveaway_finish(bot, giveaway_id: int, end_time: datetime):
    """Планирование завершения розыгрыша"""
    job_id = f"finish_giveaway_{giveaway_id}"

    if scheduler.get_job(job_id):
        scheduler.remove_job(job_id)

    scheduler.add_job(
        finish_giveaway_task,
        DateTrigger(run_date=end_time),
        args=[bot, giveaway_id],
        id=job_id,
        name=f"Завершение розыгрыша #{giveaway_id}"
    )

    logging.info(f"Запланировано завершение розыгрыша #{giveaway_id} на {format_datetime(end_time)}")


def schedule_reminders(bot, giveaway):
    """Планирование многоуровневых напоминаний"""
    now = datetime.now(timezone.utc)
    duration = giveaway.end_time - now

    # Настройки напоминаний
    settings = REMINDER_SETTINGS.setdefault(giveaway.id, {
        "enabled": True,
        "reminded_3d": False,
        "reminded_1d": False,
        "reminded_3h": False
    })

    if not settings["enabled"]:
        return

    # Напоминание за 3 дня
    if duration > timedelta(days=3):
        reminder_time = giveaway.end_time - timedelta(days=3)
        job_id = f"reminder_3d_{giveaway.id}"
        if not scheduler.get_job(job_id):
            scheduler.add_job(
                send_reminder,
                DateTrigger(run_date=reminder_time),
                args=[bot, giveaway.id, "3d"],
                id=job_id
            )

    # Напоминание за 1 день
    if duration > timedelta(days=1):
        reminder_time = giveaway.end_time - timedelta(days=1)
        job_id = f"reminder_1d_{giveaway.id}"
        if not scheduler.get_job(job_id):
            scheduler.add_job(
                send_reminder,
                DateTrigger(run_date=reminder_time),
                args=[bot, giveaway.id, "1d"],
                id=job_id
            )

    # Напоминание за 3 часа
    reminder_time = giveaway.end_time - timedelta(hours=3)
    if reminder_time > now:
        job_id = f"reminder_3h_{giveaway.id}"
        if not scheduler.get_job(job_id):
            scheduler.add_job(
                send_reminder,
                DateTrigger(run_date=reminder_time),
                args=[bot, giveaway.id, "3h"],
                id=job_id
            )


async def send_reminder(bot, giveaway_id: int, level: str):
    """Отправка напоминания"""

    settings = REMINDER_SETTINGS.get(giveaway_id)
    if not settings or not settings["enabled"]:
        return

    # Проверяем, отправляли ли уже это напоминание
    flag_key = f"reminded_{level}"
    if settings.get(flag_key):
        return

    giveaway = await get_giveaway(giveaway_id)
    if not giveaway or giveaway.status != "active":
        return

    # Не отправляем, если розыгрыш закончился
    if giveaway.end_time <= datetime.now(timezone.utc):
        return

    # Формируем текст
    time_labels = {
        "3d": "через 3 дня",
        "1d": "завтра",
        "3h": "через 3 часа"
    }

    text = REMINDER_POST_TEMPLATE.format(
        title=giveaway.title,
        description=giveaway.description,
        winner_places=giveaway.winner_places,
        end_time=format_datetime(giveaway.end_time),
        time_left=time_labels[level],
        participants=await get_participants_count(giveaway_id)
    )

    keyboard = get_participate_keyboard(giveaway.id, await get_participants_count(giveaway.id))

    try:
        await bot.send_message(
            chat_id=giveaway.channel_id,
            text=text,
            reply_markup=keyboard,
            disable_web_page_preview=False
        )
        settings[flag_key] = True
        logging.info(f"✅ Отправлено напоминание {level} для розыгрыша {giveaway_id}")
    except Exception as e:
        logging.error(f"❌ Ошибка при отправке напоминания {level} для розыгрыша {giveaway_id}: {e}")


def disable_all_reminders(giveaway_id: int):
    """Отключение всех напоминаний для розыгрыша"""
    settings = REMINDER_SETTINGS.get(giveaway_id)
    if settings:
        settings["enabled"] = False

    # Отменяем запланированные напоминания
    for level in ["3d", "1d", "3h"]:
        job_id = f"reminder_{level}_{giveaway_id}"
        if scheduler.get_job(job_id):
            scheduler.remove_job(job_id)

    logging.info(f"Напоминания отключены для розыгрыша {giveaway_id}")


async def check_user_subscription(bot, user_id: int, channel_id: int) -> bool:
    """
    Проверяет, подписан ли пользователь на канал.

    Args:
        bot: Экземпляр бота (aiogram)
        user_id: ID пользователя
        channel_id: ID канала (можно с @ или без, но лучше целое число с -100)

    Returns:
        bool: True, если пользователь подписан (member, administrator, creator), иначе False
    """
    try:
        chat_member = await bot.get_chat_member(chat_id=channel_id, user_id=user_id)
        status = chat_member.status
        return status in ["member", "administrator", "creator"]
    except Exception as e:
        logging.warning(f"Ошибка при проверке подписки пользователя {user_id} на канал {channel_id}: {e}")
        return False


def cancel_giveaway_schedule(giveaway_id: int):
    """Отмена планирования завершения розыгрыша"""
    job_id = f"finish_giveaway_{giveaway_id}"
    if scheduler.get_job(job_id):
        scheduler.remove_job(job_id)
        logging.info(f"Отменено автоматическое завершение розыгрыша #{giveaway_id}")


async def finish_giveaway_task(bot, giveaway_id: int):
    """Задача завершения розыгрыша"""
    try:
        giveaway = await get_giveaway(giveaway_id)

        if not giveaway or giveaway.status != "active":
            return

        participants = await get_participants(giveaway_id)
        relevant_participants = [p for p in participants if
                                 await check_user_subscription(bot, p.user_id, giveaway.channel_id)]

        if not relevant_participants:
            await finish_giveaway(giveaway_id)
            no_participants_message = "🎊 <b>РОЗЫГРЫШ ЗАВЕРШЕН!</b>\n\n😔 К сожалению, в розыгрыше не было участников."

            try:
                await bot.send_message(
                    chat_id=giveaway.channel_id,
                    text=no_participants_message,
                    parse_mode="HTML",
                    reply_to_message_id=giveaway.message_id if giveaway.message_id else None
                )
            except Exception as e:
                logging.error(f"Ошибка отправки сообщения о завершении розыгрыша без участников: {e}")
            return

        winner_places = giveaway.winner_places
        if len(relevant_participants) < winner_places:
            winner_places = len(relevant_participants)

        winners = random.sample(relevant_participants, winner_places)
        channel: Optional[Channel] = await get_channel(giveaway.channel_id)
        winners_data = []
        winners_list = []

        for i, winner in enumerate(winners, 1):
            winner_name = winner.first_name or winner.full_name
            if winner.username:
                winner_name = f"@{winner.username}"

            if winner_places == 1:
                winners_list.append(f"🏆 <b>Победитель:</b> {winner_name}")
            else:
                place_emoji = {1: "🥇", 2: "🥈", 3: "🥉"}.get(i, f"{i}")
                winners_list.append(f"{place_emoji} <b>{i} место:</b> {winner_name}")

            winners_data.append({
                "user_id": winner.user_id,
                "username": winner.username,
                "first_name": winner.first_name,
                "full_name": winner.full_name,
                "place": i
            })
            await bot.send_message(
                chat_id=winner.user_id,
                text="🎉 <b>Поздравляем с победой!</b>\n\nВы выиграли розыгрыш!"
            )

        await finish_giveaway(giveaway_id=giveaway_id, winners_data=winners_data)

        winner_message = (
                "🎊 <b>РОЗЫГРЫШ ЗАВЕРШЕН!</b>\n\n" + "\n".join(winners_list) + "\n\n🎉 Поздравляем!"
        )
        keyboard_admin = await get_winers_keyboard(winners_data)

        try:
            await bot.send_message(
                chat_id=giveaway.channel_id,
                text=winner_message,
                parse_mode="HTML",
                reply_to_message_id=giveaway.message_id if giveaway.message_id else None
            )

            logging.debug(f"Отправлено сообщение о победителе для розыгрыша #{giveaway_id}")

        except Exception as e:
            logging.error(f"Ошибка отправки сообщения о победителе: {e}")

        admin_id = channel.admin.user_id
        if not channel.admin:
            logging.error(f"Администратор канала {channel.id} не найден")
            admin_id = config.MAIN_ADMIN_ID

        await bot.send_message(
                chat_id=admin_id,
                text=MESSAGES.get("result_giveaway").format(winner="\n".join(winners_list)),
                reply_markup=keyboard_admin
            )
        logging.debug(f"Отправлено сообщение об итогах для администратора канала {channel.admin}")
        logging.info(f"Розыгрыш #{giveaway_id} завершен. Итоги опубликованы.")



    except Exception as e:
        logging.error(f"Ошибка при завершении розыгрыша #{giveaway_id}: {e}")


async def cleanup_old_finished(days: int):
    try:
        deleted = await delete_finished_older_than(days)
        if deleted:
            logging.info(f"Очищено завершенных розыгрышей: {deleted} (старше {days} дней)")
    except Exception as e:
        logging.error(f"Ошибка очистки завершенных розыгрышей: {e}")


def get_scheduler_status() -> dict:
    """Получение статуса планировщика"""
    jobs = scheduler.get_jobs()
    return {
        "running": scheduler.running,
        "jobs_count": len(jobs),
        "jobs": [
            {
                "id": job.id,
                "name": job.name,
                "next_run_time": job.next_run_time
            }
            for job in jobs
        ]
    }
