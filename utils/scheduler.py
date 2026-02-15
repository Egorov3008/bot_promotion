import logging
import random
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional, List

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.date import DateTrigger

from config import config
from database.database import (
    finish_giveaway, get_participants, delete_finished_older_than,
    get_participants_count, get_channel, get_giveaway, get_active_giveaways
)
from database.models import Channel
from pyrogram_app import MailingMode
from pyrogram_app.pyro_client import get_pyrogram_client
from texts.messages import REMINDER_POST_TEMPLATE, MESSAGES
from utils.datetime_utils import format_datetime
from utils.keyboards import get_participate_keyboard, get_winers_keyboard

# Единый экземпляр планировщика
scheduler = AsyncIOScheduler(timezone=timezone.utc)

# Хранение состояния напоминаний: giveaway_id → флаги
REMINDER_SETTINGS: Dict[int, Dict[str, bool]] = {}


async def setup_scheduler(bot) -> None:
    """
    Запускает планировщик и восстанавливает задачи для активных розыгрышей.
    """
    active_giveaways = await get_active_giveaways()

    for giveaway in active_giveaways:
        end_time = make_aware(giveaway.end_time)

        now = datetime.now(timezone.utc)
        if end_time <= now:
            continue  # Розыгрыш уже должен быть завершён

        # Планируем завершение
        schedule_giveaway_finish(bot, giveaway.id, end_time)

        # Планируем напоминания
        await schedule_reminders(bot, giveaway)

    # Ежедневная очистка старых розыгрышей
    scheduler.add_job(
        cleanup_old_finished,
        'interval',
        days=1,
        args=[15],
        id="cleanup_old_finished",
        replace_existing=True
    )

    if not scheduler.running:
        scheduler.start()
        logging.info(f"✅ Планировщик запущен. Восстановлено задач: {len(active_giveaways)}")


def make_aware(dt: datetime) -> datetime:
    """Приводит datetime к offset-aware (UTC), если нужно."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def schedule_giveaway_finish(bot, giveaway_id: int, end_time: datetime) -> None:
    """
    Планирует завершение розыгрыша по времени.
    """
    job_id = f"finish_giveaway_{giveaway_id}"

    if scheduler.get_job(job_id):
        scheduler.remove_job(job_id)

    scheduler.add_job(
        finish_giveaway_task,
        trigger=DateTrigger(run_date=end_time),
        args=[bot, giveaway_id],
        id=job_id,
        name=f"Завершение розыгрыша #{giveaway_id}"
    )

    logging.info(f"Запланировано завершение розыгрыша #{giveaway_id} на {format_datetime(end_time)}")


async def schedule_reminders(bot, giveaway) -> None:
    """
    Планирует все напоминания (3 дня, 1 день, 3 часа) до окончания розыгрыша.
    """
    now = datetime.now(timezone.utc)
    end_time = make_aware(giveaway.end_time)
    duration = end_time - now

    settings = REMINDER_SETTINGS.setdefault(giveaway.id, {
        "enabled": True,
        "reminded_3d": False,
        "reminded_1d": False,
        "reminded_3h": False
    })

    if not settings["enabled"]:
        return

    _schedule_single_reminder(bot, giveaway, "3d", duration, timedelta(days=3))
    _schedule_single_reminder(bot, giveaway, "1d", duration, timedelta(days=1))
    _schedule_single_reminder(bot, giveaway, "3h", duration, timedelta(hours=3))


def _schedule_single_reminder(bot, giveaway, level: str, duration: timedelta, threshold: timedelta) -> None:
    """
    Внутренняя функция для планирования одного напоминания.
    """
    if duration <= threshold:
        return

    reminder_time = make_aware(giveaway.end_time) - threshold
    job_id = f"reminder_{level}_{giveaway.id}"

    if not scheduler.get_job(job_id):
        scheduler.add_job(
            send_reminder,
            trigger=DateTrigger(run_date=reminder_time),
            args=[bot, giveaway.id, level],
            id=job_id
        )


async def send_reminder(bot, giveaway_id: int, level: str) -> None:
    """
    Отправляет напоминание участникам за N времени до конца.
    """
    settings = REMINDER_SETTINGS.get(giveaway_id)
    if not settings or not settings["enabled"]:
        return

    flag_key = f"reminded_{level}"
    if settings.get(flag_key):
        return

    giveaway = await get_giveaway(giveaway_id)
    if not giveaway or giveaway.status != "active":
        return

    end_time = make_aware(giveaway.end_time)
    if end_time <= datetime.now(timezone.utc):
        return

    time_labels = {"3d": "через 3 дня", "1d": "завтра", "3h": "через 3 часа"}
    text = REMINDER_POST_TEMPLATE.format(
        title=giveaway.title,
        description=giveaway.description,
        winner_places=giveaway.winner_places,
        end_time=format_datetime(end_time),
        time_left=time_labels[level],
        participants=await get_participants_count(giveaway_id)
    )
    keyboard = get_participate_keyboard(giveaway.id, await get_participants_count(giveaway_id))

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


def disable_all_reminders(giveaway_id: int) -> None:
    """
    Отключает все напоминания для розыгрыша.
    """
    settings = REMINDER_SETTINGS.get(giveaway_id)
    if settings:
        settings["enabled"] = False

    for level in ["3d", "1d", "3h"]:
        job_id = f"reminder_{level}_{giveaway_id}"
        if scheduler.get_job(job_id):
            scheduler.remove_job(job_id)

    logging.info(f"Напоминания отключены для розыгрыша {giveaway_id}")


async def check_user_subscription(bot, user_id: int, channel_id: int) -> bool:
    """
    Проверяет подписку пользователя на канал.
    """
    try:
        member = await bot.get_chat_member(chat_id=channel_id, user_id=user_id)
        return member.status in ["member", "administrator", "creator"]
    except Exception as e:
        logging.warning(f"Ошибка проверки подписки {user_id} на {channel_id}: {e}")
        return False


def cancel_giveaway_schedule(giveaway_id: int) -> None:
    """
    Отменяет автоматическое завершение розыгрыша.
    """
    job_id = f"finish_giveaway_{giveaway_id}"
    if scheduler.get_job(job_id):
        scheduler.remove_job(job_id)
        logging.info(f"Отменено завершение розыгрыша #{giveaway_id}")


async def finish_giveaway_task(bot, giveaway_id: int) -> None:
    """
    Основная задача завершения розыгрыша: выбор победителей, рассылка, обновление БД.
    """
    try:
        giveaway = await get_giveaway(giveaway_id)
        if not giveaway or giveaway.status != "active":
            return

        end_time = make_aware(giveaway.end_time)
        if end_time > datetime.now(timezone.utc):
            logging.warning(f"Розыгрыш #{giveaway_id} ещё не завершился. Пропуск.")
            return

        participants = await get_participants(giveaway_id)
        subscribed = [
            p for p in participants
            if await check_user_subscription(bot, p.user_id, giveaway.channel_id)
        ]

        if not subscribed:
            await finish_giveaway(giveaway_id)
            await _send_no_participants_message(bot, giveaway)
            return

        winner_places = min(giveaway.winner_places, len(subscribed))
        winners = random.sample(subscribed, winner_places)

        channel: Optional[Channel] = await get_channel(giveaway.channel_id)
        winners_data = []
        winners_list = []

        # 🔹 Получаем запущенный экземпляр PyrogramClient
        pyro_client_wrapper = get_pyrogram_client()
        if not pyro_client_wrapper.is_running:
            logging.error("Pyrogram клиент не запущен! Невозможно отправить сообщения победителям.")
            return

        # 🔹 Экспортируем внутренний Client и используем MailingMode
        client = await pyro_client_wrapper.export()
        mailer = MailingMode(client, delay_range=(1.5, 3.0))  # Задержка между сообщениями

        for i, w in enumerate(winners, 1):
            name = f"@{w.username}" if w.username else (w.first_name or w.full_name)
            emoji = {1: "🥇", 2: "🥈", 3: "🥉"}.get(i, f"{i}")
            winners_list.append(f"{emoji} <b>{i} место:</b> {name}")

            # 📨 Отправляем персональное сообщение через MailingMode
            success, delivery_message = await mailer.send_message_to_user(
                user_id=w.user_id,
                text=giveaway.message_winner or (
                    "Поздравляем! Вы выиграли розыгрыш!\n"
                    "Скоро с вами свяжется администратор."
                ),
                parse_mode="HTML",
            )

            winners_data.append({
                "user_id": w.user_id,
                "username": w.username,
                "first_name": w.first_name,
                "full_name": w.full_name,
                "place": i,
                "sender_check": success,
                "delivery_message": delivery_message
            })

            if not success:
                logging.warning(f"Не удалось отправить сообщение победителю {w.user_id}: {delivery_message}")

        # 🔚 Завершаем розыгрыш
        await finish_giveaway(giveaway_id=giveaway_id, winners_data=winners_data)
        await _send_winner_announcement(bot, giveaway, winners_list)
        await _send_admin_results(bot, channel, winners_list, winners_data)

    except Exception as e:
        logging.error(f"Ошибка при завершении розыгрыша #{giveaway_id}: {e}", exc_info=True)

async def _send_no_participants_message(bot, giveaway) -> None:
    """Отправляет сообщение о завершении без участников."""
    message = "🎊 <b>РОЗЫГРЫШ ЗАВЕРШЕН!</b>\n\n😔 К сожалению, в розыгрыше не было участников."
    try:
        await bot.send_message(
            chat_id=giveaway.channel_id,
            text=message,
            parse_mode="HTML",
            reply_to_message_id=giveaway.message_id
        )
    except Exception as e:
        logging.error(f"Ошибка отправки сообщения о пустом розыгрыше: {e}")


async def _send_winner_announcement(bot, giveaway, winners_list: List[str]) -> None:
    """Отправляет результаты в канал."""
    message = "🎊 <b>РОЗЫГРЫШ ЗАВЕРШЕН!</b>\n\n" + "\n".join(winners_list) + "\n\n🎉 Поздравляем!"
    try:
        await bot.send_message(
            chat_id=giveaway.channel_id,
            text=message,
            parse_mode="HTML",
            reply_to_message_id=giveaway.message_id
        )
        logging.debug(f"Сообщение о победителях отправлено в канал {giveaway.channel_id}")
    except Exception as e:
        logging.error(f"Ошибка отправки результата в канал: {e}")


async def _send_admin_results(bot, channel: Optional[Channel], winners_list: List[str],
                              winners_data: List[dict]) -> None:
    """Отправляет результаты администратору канала с информацией о доставке ЛС."""
    admin_id = channel.admin.user_id if channel and channel.admin else config.MAIN_ADMIN_ID

    # Формируем список статусов отправки ЛС
    dm_status_lines = []
    for winner in winners_data:
        user_display = f"@{winner['username']}" if winner['username'] else (
                    winner['first_name'] or f"ID:{winner['user_id']}")
        place_emoji = {1: "🥇", 2: "🥈", 3: "🥉"}.get(winner['place'], f"{winner['place']}")

        try:
            # Проверяем, было ли успешное сообщение через Pyrogram
            sender_check = winner.get("sender_check")
            if sender_check:
                dm_status_lines.append(f"{place_emoji} {user_display} — ✅ Успешно")
            else:
                dm_status_lines.append(f"{place_emoji} {user_display} — ❌ Не доставлено")
        except Exception:
            dm_status_lines.append(f"{place_emoji} {user_display} — ❌ Ошибка отправки")

    dm_status_text = "\n".join(dm_status_lines)

    # Формируем итоговое сообщение
    message_text = MESSAGES.get("result_giveaway").format(
        winner="\n".join(winners_list),
        dm_status=dm_status_text
    )

    keyboard = await get_winers_keyboard(winners_data)

    try:
        await bot.send_message(
            chat_id=admin_id,
            text=message_text,
            reply_markup=keyboard,
            parse_mode="HTML"
        )
        logging.debug(f"Результаты розыгрыша с статусами ЛС отправлены администратору {admin_id}")
    except Exception as e:
        logging.error(f"Ошибка при отправке результатов администратору {admin_id}: {e}")


async def cleanup_old_finished(days: int) -> None:
    """
    Очищает завершённые розыгрыши старше указанного количества дней.
    """
    try:
        deleted = await delete_finished_older_than(days)
        if deleted:
            logging.info(f"Очищено {deleted} завершённых розыгрышей (старше {days} дней)")
    except Exception as e:
        logging.error(f"Ошибка при очистке завершённых розыгрышей: {e}")


def get_scheduler_status() -> dict:
    """
    Возвращает текущий статус планировщика.
    """
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
