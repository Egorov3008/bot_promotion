import logging
from datetime import datetime
from typing import List

from aiogram.types import CallbackQuery, Message
from aiogram_dialog import Dialog, Window, DialogManager
from aiogram_dialog.widgets.input import MessageInput
from aiogram_dialog.widgets.kbd import (
    Button, Row, Back, Start, ScrollingGroup, Select,
    Url, ListGroup, SwitchTo,
)
from aiogram_dialog.widgets.text import Format, Const

from database import Giveaway
from states.admin_states import ViewGiveawaysStates, AdminStates
from database.database import (
    get_active_giveaways,
    get_finished_giveaways_page,
    count_finished_giveaways,
    get_giveaway,
    get_winners,
    update_giveaway_fields,
)
from texts.messages import DETAIL_TEXT


# ─── Getters ───────────────────────────────────────────────


async def active_giveaways_getter(dialog_manager: DialogManager, **kwargs):
    """Геттер для списка активных розыгрышей"""
    giveaways = await get_active_giveaways()
    items = [
        {
            "id": g.id,
            "title": g.title[:30] if g.title else "",
            "participants_count": len(g.participants) if g.participants else 0,
        }
        for g in (giveaways or [])
    ]
    return {
        "giveaways": items,
        "count": len(items),
    }


async def finished_giveaways_getter(dialog_manager: DialogManager, **kwargs):
    """Геттер для списка завершенных розыгрышей"""
    page = dialog_manager.dialog_data.get("page", 1)
    page_size = 10

    giveaways: List[Giveaway] = await get_finished_giveaways_page(page, page_size)
    logging.debug(f"Получены данные Giveaways: {giveaways}")
    total_count = await count_finished_giveaways()
    total_pages = (total_count + page_size - 1) // page_size

    items = [
        {
            "id": g.id,
            "title": g.title[:30] if g.title else "",
        }
        for g in (giveaways or [])
    ]
    return {
        "giveaways": items,
        "count": len(items),
        "page": page,
        "total_pages": total_pages,
    }


def _truncate(text: str, max_len: int) -> str:
    """Обрезает текст до max_len символов с многоточием"""
    if len(text) <= max_len:
        return text
    return text[:max_len - 1] + "…"


# Лимит Telegram — 4096 символов. Фиксированная часть шаблона + короткие поля ≈ 500.
# Остаток (~3500) делим между description и message_winner.
_MAX_DESCRIPTION = 1500
_MAX_MESSAGE_WINNER = 1500


async def _base_detail_getter(dialog_manager: DialogManager) -> dict:
    """Базовый геттер деталей розыгрыша"""
    giveaway_id = dialog_manager.dialog_data.get("selected_giveaway_id")
    g = await get_giveaway(giveaway_id)
    if not g:
        raise ValueError(f"Розыгрыш с ID '{giveaway_id}' не найден.")
    return {
        "id": g.id,
        "title": _truncate(g.title or "", 255),
        "description": _truncate(g.description or "", _MAX_DESCRIPTION),
        "message_winner": _truncate(g.message_winner or "—", _MAX_MESSAGE_WINNER),
        "status": g.status,
        "channel_name": g.channel.channel_name if g.channel else "—",
        "participants_count": len(g.participants) if g.participants else 0,
        "winner_places": g.winner_places,
        "start_time": g.start_time.strftime("%d.%m.%Y %H:%M") if g.start_time else "—",
        "end_time": g.end_time.strftime("%d.%m.%Y %H:%M") if g.end_time else "—",
    }


async def active_detail_getter(dialog_manager: DialogManager, **kwargs):
    """Геттер для деталей активного розыгрыша"""
    return await _base_detail_getter(dialog_manager)


async def finished_detail_getter(dialog_manager: DialogManager, **kwargs):
    """Геттер для деталей завершённого розыгрыша + победители"""
    data = await _base_detail_getter(dialog_manager)
    giveaway_id = dialog_manager.dialog_data.get("selected_giveaway_id")
    winners = await get_winners(giveaway_id)
    data["winners"] = [
        {
            "place": w.place,
            "name": w.full_name or w.first_name or w.username or str(w.user_id),
            "url": f"tg://user?id={w.user_id}",
        }
        for w in (winners or [])
    ]
    data["has_winners"] = len(data["winners"]) > 0
    return data


# ─── Click handlers ────────────────────────────────────────


async def on_giveaway_selected(callback: CallbackQuery, widget, manager: DialogManager, item_id: str):
    """Обработчик выбора розыгрыша — маршрутизация по типу списка"""
    giveaway_id = int(item_id)
    giveaway = await get_giveaway(giveaway_id)
    if not giveaway:
        return

    manager.dialog_data["selected_giveaway_id"] = giveaway_id
    list_type = manager.dialog_data.get("list_type", "active")
    if list_type == "finished":
        await manager.switch_to(ViewGiveawaysStates.VIEWING_FINISHED_DETAILS)
    else:
        await manager.switch_to(ViewGiveawaysStates.VIEWING_ACTIVE_DETAILS)


async def on_page_change(callback: CallbackQuery, widget, manager: DialogManager, action: str):
    """Обработчик смены страницы"""
    page = manager.dialog_data.get("page", 1)
    if action == "next":
        page += 1
    elif action == "prev" and page > 1:
        page -= 1
    manager.dialog_data["page"] = page


async def on_show_active(callback: CallbackQuery, widget, manager: DialogManager):
    """Показать активные розыгрыши"""
    manager.dialog_data["list_type"] = "active"
    await manager.switch_to(ViewGiveawaysStates.VIEWING_ACTIVE)


async def on_show_finished(callback: CallbackQuery, widget, manager: DialogManager):
    """Показать завершенные розыгрыши"""
    manager.dialog_data["list_type"] = "finished"
    manager.dialog_data["page"] = 1
    await manager.switch_to(ViewGiveawaysStates.VIEWING_FINISHED)


# ─── Edit handlers ─────────────────────────────────────────


async def on_edit_title(message: Message, widget: MessageInput, manager: DialogManager):
    """Изменить название розыгрыша"""
    giveaway_id = manager.dialog_data["selected_giveaway_id"]
    if len(message.text) > 255:
        await message.answer("Заголовок не должен превышать 255 символов.")
        return
    await update_giveaway_fields(giveaway_id, title=message.text)
    await manager.switch_to(ViewGiveawaysStates.VIEWING_ACTIVE_DETAILS)


async def on_edit_description(message: Message, widget: MessageInput, manager: DialogManager):
    """Изменить описание розыгрыщя"""

    giveaway_id = manager.dialog_data["selected_giveaway_id"]
    if len(message.text) > 4000:
        await message.answer("Описание не должно превышать 4000 символов.")
        return
    await update_giveaway_fields(giveaway_id, description=message.text)
    await manager.switch_to(ViewGiveawaysStates.VIEWING_ACTIVE_DETAILS)


async def on_edit_end_time(message: Message, widget: MessageInput, manager: DialogManager):
    """Изменить дату и время конца розыгрыша"""
    giveaway_id = manager.dialog_data["selected_giveaway_id"]
    try:
        end_time = datetime.strptime(message.text.strip(), "%d.%m.%Y %H:%M")
    except ValueError:
        await message.answer("Неверный формат. Используйте: ДД.ММ.ГГГГ ЧЧ:ММ")
        return
    if end_time <= datetime.now():
        await message.answer("Дата окончания должна быть в будущем.")
        return
    await update_giveaway_fields(giveaway_id, end_time=end_time)
    await manager.switch_to(ViewGiveawaysStates.VIEWING_ACTIVE_DETAILS)


async def on_edit_message_winner(message: Message, widget: MessageInput, manager: DialogManager):
    """Добавить сообщение о выигравших участниках"""
    giveaway_id = manager.dialog_data["selected_giveaway_id"]
    if len(message.text) > 4000:
        await message.answer("Сообщение не должно превышать 4000 символов.")
        return
    await update_giveaway_fields(giveaway_id, message_winner=message.text)
    await manager.switch_to(ViewGiveawaysStates.VIEWING_ACTIVE_DETAILS)


# ─── Windows ───────────────────────────────────────────────

# Выбор типа списка
choose_list_type_window = Window(
    Const("📋 Выберите тип розыгрышей:"),
    Row(
        Button(Const("🎯 Активные"), id="show_active", on_click=on_show_active),
        Button(Const("✅ Завершенные"), id="show_finished", on_click=on_show_finished),
    ),
    Start(Const("🏠 В меню"), id="main_menu", state=AdminStates.MAIN_MENU),
    state=ViewGiveawaysStates.CHOOSING_TYPE,
)

# Список активных
active_giveaways_window = Window(
    Format("🎯 Активные розыгрыши ({count}):"),
    ScrollingGroup(
        Select(
            Format("#{item[id]} {item[title]}"),
            id="s_active_giveaway",
            item_id_getter=lambda x: x["id"],
            items="giveaways",
            on_click=on_giveaway_selected,
        ),
        width=1,
        height=5,
        id="active_giveaways_scroller",
    ),
    Back(Const("◀️ Назад"), id="back"),
    state=ViewGiveawaysStates.VIEWING_ACTIVE,
    getter=active_giveaways_getter,
)

# Список завершённых
finished_giveaways_window = Window(
    Format("📋 Завершенные розыгрыши (стр. {page}/{total_pages}, всего: {count}):"),
    ScrollingGroup(
        Select(
            Format("#{item[id]} {item[title]}"),
            id="s_finished_giveaway",
            item_id_getter=lambda x: x["id"],
            items="giveaways",
            on_click=on_giveaway_selected,
        ),
        width=1,
        height=5,
        id="finished_giveaways_scroller",
    ),
    Row(
        Button(Const("◀️ Предыдущая"), id="prev_page", on_click=lambda c, w, m: on_page_change(c, w, m, "prev")),
        Button(Const("▶️ Следующая"), id="next_page", on_click=lambda c, w, m: on_page_change(c, w, m, "next")),
    ),
    Back(Const("◀️ Назад"), id="back"),
    state=ViewGiveawaysStates.VIEWING_FINISHED,
    getter=finished_giveaways_getter,
)

# Детали завершённого розыгрыша
finished_details_window = Window(
    Format(DETAIL_TEXT),
    Const("\n<b>🏆 Победители:</b>", when="has_winners"),
    ListGroup(
        Url(
            Format("{item[place]}. {item[name]}"),
            url=Format("{item[url]}"),
            id="winner_url",
        ),
        id="winners_list",
        item_id_getter=lambda x: x["place"],
        items="winners",
    ),
    Const("\nПобедители не определены", when=lambda data, *a, **k: not data.get("has_winners")),
    Back(Const("◀️ Назад"), id="back"),
    state=ViewGiveawaysStates.VIEWING_FINISHED_DETAILS,
    getter=finished_detail_getter,
)

# Детали активного розыгрыша
active_details_window = Window(
    Format(DETAIL_TEXT),
    Row(
        SwitchTo(Const("✏️ Заголовок"), id="edit_title", state=ViewGiveawaysStates.EDITING_TITLE),
        SwitchTo(Const("✏️ Описание"), id="edit_desc", state=ViewGiveawaysStates.EDITING_DESCRIPTION),
    ),
    Row(
        SwitchTo(Const("✏️ Дата окончания"), id="edit_end", state=ViewGiveawaysStates.EDITING_END_TIME),
        SwitchTo(Const("✏️ Сообщение победителям"), id="edit_msg", state=ViewGiveawaysStates.EDITING_MESSAGE_WINNER),
    ),
    Back(Const("◀️ Назад"), id="back"),
    state=ViewGiveawaysStates.VIEWING_ACTIVE_DETAILS,
    getter=active_detail_getter,
)

# Окна редактирования полей
edit_title_window = Window(
    Const("✏️ Введите новый заголовок (макс. 255 символов):"),
    MessageInput(on_edit_title),
    SwitchTo(Const("◀️ Отмена"), id="cancel_edit", state=ViewGiveawaysStates.VIEWING_ACTIVE_DETAILS),
    state=ViewGiveawaysStates.EDITING_TITLE,
)

edit_description_window = Window(
    Const("✏️ Введите новое описание (макс. 4000 символов):"),
    MessageInput(on_edit_description),
    SwitchTo(Const("◀️ Отмена"), id="cancel_edit", state=ViewGiveawaysStates.VIEWING_ACTIVE_DETAILS),
    state=ViewGiveawaysStates.EDITING_DESCRIPTION,
)

edit_end_time_window = Window(
    Const("✏️ Введите новую дату окончания (формат: ДД.ММ.ГГГГ ЧЧ:ММ):"),
    MessageInput(on_edit_end_time),
    SwitchTo(Const("◀️ Отмена"), id="cancel_edit", state=ViewGiveawaysStates.VIEWING_ACTIVE_DETAILS),
    state=ViewGiveawaysStates.EDITING_END_TIME,
)

edit_message_winner_window = Window(
    Const("✏️ Введите новое сообщение для победителей (макс. 4000 символов):"),
    MessageInput(on_edit_message_winner),
    SwitchTo(Const("◀️ Отмена"), id="cancel_edit", state=ViewGiveawaysStates.VIEWING_ACTIVE_DETAILS),
    state=ViewGiveawaysStates.EDITING_MESSAGE_WINNER,
)


# ─── Dialog ────────────────────────────────────────────────

giveaway_view_dialog = Dialog(
    choose_list_type_window,
    active_giveaways_window,
    finished_giveaways_window,
    finished_details_window,
    active_details_window,
    edit_title_window,
    edit_description_window,
    edit_end_time_window,
    edit_message_winner_window,
)