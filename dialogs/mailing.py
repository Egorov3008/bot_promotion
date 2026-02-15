import asyncio
import logging

from aiogram.enums import ContentType
from aiogram.types import CallbackQuery, Message
from aiogram_dialog import Dialog, DialogManager, Window, StartMode
from aiogram_dialog.widgets.input import MessageInput
from aiogram_dialog.widgets.kbd import Button, Select, Row, Cancel, Start, Back
from aiogram_dialog.widgets.text import Format, Const

from states.admin_states import MailingStates, AdminDialogStates, AdminStates
from texts.messages import MESSAGES, BUTTONS
from database.database import (get_all_channels, get_active_subscribers,
                                 get_all_active_subscribers,
                                 get_channel_subscribers_stats, create_mailing,
                                 get_active_mailing, update_mailing_stats,
                                 get_channel)
from pyrogram_app.pyro_client import get_pyrogram_client
from pyrogram_app.mailing_mode import MailingMode

logger = logging.getLogger(__name__)

# Глобальный реестр активных MailingMode для возможности остановки
_active_mailings: dict[int, MailingMode] = {}

# ---------------------------------------------------------------------------
# Getters
# ---------------------------------------------------------------------------

async def channels_getter(dialog_manager: DialogManager, **kwargs):
    """Геттер для получения списка каналов, которыми управляет админ."""
    channels = await get_all_channels()
    return {
        "channels": channels
    }


async def audience_getter(dialog_manager: DialogManager, **kwargs):
    """Геттер для получения статистики аудитории по каналу."""
    channel_id = dialog_manager.dialog_data.get("selected_channel_id")

    if not channel_id:
        return {
            "active_count": 0,
            "all_count": 0
        }

    # Получаем количество активных за 30 дней
    active_subscribers = await get_active_subscribers(channel_id, days=30)
    active_count = len(active_subscribers)

    # Получаем общее количество подписчиков
    stats = await get_channel_subscribers_stats(channel_id)
    all_count = stats.get("active", 0)

    # Сохраняем в dialog_data для последующего использования
    dialog_manager.dialog_data["audience_counts"] = {
        "active_30d": active_count,
        "all": all_count
    }

    return {
        "active_count": active_count,
        "all_count": all_count
    }


async def preview_getter(dialog_manager: DialogManager, **kwargs):
    """Геттер для превью рассылки — название канала, тип аудитории, текст."""
    channel_id = dialog_manager.dialog_data.get("selected_channel_id")
    audience_type = dialog_manager.dialog_data.get("audience_type", "all")
    message_text = dialog_manager.dialog_data.get("message_text", "")
    audience_counts = dialog_manager.dialog_data.get("audience_counts", {})

    # Получаем название канала
    channel_name = "—"
    if channel_id:
        channel = await get_channel(channel_id)
        if channel:
            channel_name = channel.channel_name

    # Человекочитаемый тип аудитории
    if audience_type == "active_30d":
        audience_label = "Активные за 30 дней"
        count = audience_counts.get("active_30d", 0)
    else:
        audience_label = "Все подписчики"
        count = audience_counts.get("all", 0)

    return {
        "channel": channel_name,
        "audience": audience_label,
        "count": count,
        "message": message_text,
    }


async def sending_getter(dialog_manager: DialogManager, **kwargs):
    """Геттер для окна прогресса рассылки."""
    return {
        "sent": dialog_manager.dialog_data.get("sent", 0),
        "total": dialog_manager.dialog_data.get("total", 0),
    }


async def done_getter(dialog_manager: DialogManager, **kwargs):
    """Геттер для окна итоговой статистики."""
    return {
        "sent": dialog_manager.dialog_data.get("sent", 0),
        "failed": dialog_manager.dialog_data.get("failed", 0),
        "blocked": dialog_manager.dialog_data.get("blocked", 0),
        "duration": dialog_manager.dialog_data.get("duration", "—"),
    }


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------

async def on_channel_selected(callback: CallbackQuery, widget: Select, manager: DialogManager, item_id: str):
    """Обработчик выбора канала."""
    await callback.answer()
    try:
        channel_id = int(item_id)
        manager.dialog_data["selected_channel_id"] = channel_id

        # Проверка на активную рассылку
        active_mailing = await get_active_mailing(channel_id)
        if active_mailing:
            await callback.message.answer(MESSAGES["mailing_already_running"])
            await manager.done()
            return

        await manager.switch_to(MailingStates.SELECT_AUDIENCE)
    except ValueError:
        await callback.answer("Некорректный канал.")


async def on_audience_selected(callback: CallbackQuery, button: Button, manager: DialogManager):
    """Обработчик выбора типа аудитории."""
    await callback.answer()
    audience_type = button.widget_id  # "active_30d" или "all"
    manager.dialog_data["audience_type"] = audience_type
    await manager.switch_to(MailingStates.INPUT_MESSAGE)


async def on_message_input(message: Message, widget: MessageInput, manager: DialogManager):
    """Обработчик ввода текста сообщения."""
    if not message.text:
        await message.answer("Пожалуйста, отправьте текстовое сообщение.")
        return

    text = message.text.strip()
    if not text:
        await message.answer("Сообщение не может быть пустым.")
        return

    manager.dialog_data["message_text"] = text
    await manager.switch_to(MailingStates.PREVIEW)


async def on_confirm(callback: CallbackQuery, button: Button, manager: DialogManager):
    """Обработчик подтверждения и запуска рассылки."""
    await callback.answer()

    # Получаем данные из dialog_data
    channel_id = manager.dialog_data["selected_channel_id"]
    audience_type = manager.dialog_data["audience_type"]
    message_text = manager.dialog_data["message_text"]
    audience_counts = manager.dialog_data["audience_counts"]

    # Определяем количество получателей
    total_users = audience_counts["active_30d"] if audience_type == "active_30d" else audience_counts["all"]

    # Создаем запись о рассылке в БД
    mailing = await create_mailing(
        channel_id=channel_id,
        admin_id=callback.from_user.id,
        audience_type=audience_type,
        message_text=message_text,
        total_users=total_users
    )

    # Сохраняем ID рассылки
    manager.dialog_data["mailing_id"] = mailing.id

    # Запускаем рассылку в фоне
    task = asyncio.create_task(
        _run_mailing_task(
            manager=manager,
            mailing=mailing,
            audience_type=audience_type
        )
    )
    task.add_done_callback(_task_done_callback)

    await manager.switch_to(MailingStates.SENDING)


def _task_done_callback(task: asyncio.Task):
    """Обработка завершения фоновой задачи рассылки."""
    if task.cancelled():
        logger.info("Задача рассылки была отменена")
    elif task.exception():
        logger.error("Ошибка в задаче рассылки: %s", task.exception(), exc_info=task.exception())


async def on_stop_mailing(callback: CallbackQuery, button: Button, manager: DialogManager):
    """Обработчик остановки рассылки."""
    await callback.answer("Рассылка останавливается...")

    # Останавливаем рассылку через глобальный реестр
    mailing_id = manager.dialog_data.get("mailing_id")
    if mailing_id and mailing_id in _active_mailings:
        _active_mailings[mailing_id].stop()

    await manager.switch_to(MailingStates.DONE)


# ---------------------------------------------------------------------------
# Фоновая задача рассылки
# ---------------------------------------------------------------------------

async def _run_mailing_task(
    manager: DialogManager,
    mailing,
    audience_type: str
):
    """Фоновая задача для выполнения массовой рассылки."""
    bg_manager = manager.bg()

    # Получаем Pyrogram Client
    pyro_wrapper = get_pyrogram_client()
    pyro_client = await pyro_wrapper.export()

    # Инициализируем mailing_mode
    mailing_mode = MailingMode(pyro_client, delay_range=(1, 3))

    # Регистрируем в глобальном реестре для возможности остановки
    _active_mailings[mailing.id] = mailing_mode

    try:
        # Получаем список пользователей
        if audience_type == "active_30d":
            subs = await get_active_subscribers(mailing.channel_id, days=30)
        else:
            subs = await get_all_active_subscribers(mailing.channel_id)
        user_ids = [sub.user_id for sub in subs]

        # Обновляем статус — рассылка начинается
        await update_mailing_stats(
            mailing_id=mailing.id,
            sent=0, failed=0, blocked=0, status="sending"
        )

        await bg_manager.update(
            {
                "status": "sending",
                "sent": 0,
                "total": len(user_ids),
                "blocked": 0,
                "failed": 0,
            }
        )

        # Функция обратного вызова для обновления прогресса
        async def progress_callback(sent, total, stats):
            await bg_manager.update(
                {
                    "sent": sent,
                    "total": total,
                    "blocked": stats.blocked,
                    "failed": stats.failed,
                }
            )
            await update_mailing_stats(
                mailing_id=mailing.id,
                sent=stats.successful,
                failed=stats.failed,
                blocked=stats.blocked,
                status="sending"
            )

        # Запускаем рассылку
        stats = await mailing_mode.send_bulk_messages(
            user_ids=user_ids,
            text=mailing.message_text,
            progress_callback=progress_callback
        )

        # Обновляем итоговую статистику
        status = "done" if not mailing_mode._stop_event.is_set() else "cancelled"
        await update_mailing_stats(
            mailing_id=mailing.id,
            sent=stats.successful,
            failed=stats.failed,
            blocked=stats.blocked,
            status=status
        )

        await bg_manager.update(
            {
                "status": status,
                "sent": stats.successful,
                "failed": stats.failed,
                "blocked": stats.blocked,
                "duration": f"{stats.duration_seconds():.1f} сек"
            }
        )

        # Переключаемся на финальное окно
        try:
            await bg_manager.switch_to(MailingStates.DONE)
        except Exception as e:
            logger.error("Ошибка переключения на DONE: %s", e)

    finally:
        # Убираем из реестра
        _active_mailings.pop(mailing.id, None)


# ---------------------------------------------------------------------------
# Windows
# ---------------------------------------------------------------------------

mailing_dialog = Dialog(
    # Выбор канала
    Window(
        Const(MESSAGES["mailing_select_channel"]),
        Select(
            Format("{item.channel_name}"),
            id="channel_select",
            item_id_getter=lambda channel: str(channel.channel_id),
            items="channels",
            on_click=on_channel_selected,
        ),
        Start(Const(BUTTONS["cancel"]), id='back', state=AdminStates.MAIN_MENU, mode=StartMode.RESET_STACK),
        getter=channels_getter,
        state=MailingStates.SELECT_CHANNEL
    ),
    # Выбор аудитории
    Window(
        Const(MESSAGES["mailing_select_audience"]),
        Row(
            Button(
                Format(BUTTONS["mailing_active_users"]),
                id="active_30d",
                on_click=on_audience_selected
            ),
            Button(
                Format(BUTTONS["mailing_all_users"]),
                id="all",
                on_click=on_audience_selected
            ),
        ),
        Back(Const(BUTTONS["back"])),
        getter=audience_getter,
        state=MailingStates.SELECT_AUDIENCE,
    ),
    # Ввод сообщения
    Window(
        Const(MESSAGES["mailing_input_message"]),
        MessageInput(on_message_input, content_types=[ContentType.TEXT]),
        Back(Const(BUTTONS["back"])),
        state=MailingStates.INPUT_MESSAGE,
    ),
    # Превью и подтверждение
    Window(
        Format(MESSAGES["mailing_preview"]),
        Row(
            Button(Const(BUTTONS["mailing_send"]), id="confirm", on_click=on_confirm),
            Button(Const(BUTTONS["mailing_edit"]), id="edit", on_click=lambda c, b, m: m.switch_to(MailingStates.INPUT_MESSAGE)),
        ),
        Button(Const(BUTTONS["cancel"]), id="cancel", on_click=lambda c, b, m: m.done()),
        getter=preview_getter,
        state=MailingStates.PREVIEW,
    ),
    # Процесс рассылки
    Window(
        Format(MESSAGES["mailing_sending"]),
        Button(Const(BUTTONS["mailing_stop"]), id="stop", on_click=on_stop_mailing),
        getter=sending_getter,
        state=MailingStates.SENDING,
    ),
    # Итоговая статистика
    Window(
        Format(MESSAGES["mailing_done"]),
        Start(Const(BUTTONS["mailing_menu"]), id="back_to_menu", state=AdminDialogStates.MAIN_MENU),
        getter=done_getter,
        state=MailingStates.DONE,
    ),
)
