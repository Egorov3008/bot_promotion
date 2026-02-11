"""
Диалоги просмотра розыгрышей.

Сценарии для переноса из handlers/giveaway_handlers.py:
- выбор типа списка (активные / завершённые) — ViewGiveawaysStates.CHOOSING_TYPE;
- просмотр списка (с пагинацией для завершённых) — VIEWING_LIST;
- просмотр деталей конкретного розыгрыша — VIEWING_DETAILS.

Используются функции из database.database:
- get_active_giveaways, get_finished_giveaways_page, count_finished_giveaways,
  get_giveaway, get_participants_count, get_winners.
"""

from typing import Any, Dict, List

from aiogram.types import CallbackQuery

from aiogram_dialog import Dialog, DialogManager, Window, StartMode
from aiogram_dialog.widgets.kbd import Button, Row, Select
from aiogram_dialog.widgets.text import Const, Format

from states.admin_states import ViewGiveawaysStates, EditGiveawayStates
from texts.messages import MESSAGES, BUTTONS
from texts.messages import ADMIN_GIVEAWAY_ITEM
from utils.datetime_utils import format_datetime
from database.database import (
    get_active_giveaways,
    get_finished_giveaways_page,
    count_finished_giveaways,
    get_giveaway,
    get_participants_count,
    get_winners,
)
from database.models import Giveaway


async def active_giveaways_getter(dialog_manager: DialogManager, **kwargs) -> Dict[str, Any]:
    """Геттер для списка активных розыгрышей."""
    giveaways = await get_active_giveaways()
    return {"giveaways": giveaways}


async def finished_giveaways_getter(dialog_manager: DialogManager, **kwargs) -> Dict[str, Any]:
    """Геттер для страницы завершённых розыгрышей."""
    page = dialog_manager.dialog_data.get("page", 1)
    page_size = 10
    total = await count_finished_giveaways()
    total_pages = max(1, (total + page_size - 1) // page_size) if total else 1

    if total == 0:
        return {"giveaways": [], "page": 1, "total_pages": 1}

    if page < 1:
        page = 1
    if page > total_pages:
        page = total_pages

    giveaways = await get_finished_giveaways_page(page, page_size)
    dialog_manager.dialog_data["page"] = page
    dialog_manager.dialog_data["total_pages"] = total_pages

    return {"giveaways": giveaways, "page": page, "total_pages": total_pages}


async def show_active(callback: CallbackQuery, button: Button, manager: DialogManager) -> None:
    """Кнопка 'Активные розыгрыши'."""
    await callback.answer()
    await manager.switch_to(ViewGiveawaysStates.VIEWING_LIST)
    manager.dialog_data["list_type"] = "active"


async def show_finished(callback: CallbackQuery, button: Button, manager: DialogManager) -> None:
    """Кнопка 'Завершённые розыгрыши'."""
    await callback.answer()
    manager.dialog_data["page"] = 1
    await manager.switch_to(ViewGiveawaysStates.VIEWING_LIST)
    manager.dialog_data["list_type"] = "finished"


async def on_giveaway_selected(
    callback: CallbackQuery,
    widget: Select,
    manager: DialogManager,
    item_id: str,
) -> None:
    """Выбор розыгрыша для просмотра деталей."""
    try:
        giveaway_id = int(item_id)
    except ValueError:
        await callback.answer("Некорректный розыгрыш", show_alert=True)
        return

    giveaway = await get_giveaway(giveaway_id)
    if not giveaway:
        await callback.answer("❌ Розыгрыш не найден", show_alert=True)
        return

    participants_count = await get_participants_count(giveaway_id)

    channel_name = giveaway.channel.channel_name if giveaway.channel else "Неизвестен"
    status_emoji = "🟢" if giveaway.status == "active" else "🔴"
    status_text = "Активный" if giveaway.status == "active" else "Завершенный"

    winners_block = ""
    if giveaway.status == "finished":
        winners = await get_winners(giveaway_id)
        if winners:
            lines: List[str] = []
            for w in winners:
                place_emoji = {1: "🥇", 2: "🥈", 3: "🥉"}.get(w.place, f"{w.place}️⃣")
                name = w.first_name or "Пользователь"
                if w.username:
                    name = f"@{w.username}"
                lines.append(f"{place_emoji} <b>{w.place} место:</b> {name}")
            winners_block = "\n\n" + "\n".join(lines)

    details_text = MESSAGES["giveaway_details"].format(
        id=giveaway.id,
        title=giveaway.title,
        description=giveaway.description,
        channel=channel_name,
        participants=participants_count,
        status=f"{status_emoji} {status_text}",
        created=format_datetime(giveaway.created_at),
        end_time=format_datetime(giveaway.end_time),
    ) + winners_block

    manager.dialog_data["current_giveaway_id"] = giveaway_id

    await manager.switch_to(ViewGiveawaysStates.VIEWING_DETAILS)
    await callback.message.edit_text(details_text, parse_mode="HTML")
    await callback.answer()


async def next_finished_page(callback: CallbackQuery, button: Button, manager: DialogManager) -> None:
    """Переключение на следующую страницу завершённых розыгрышей."""
    page = manager.dialog_data.get("page", 1)
    total_pages = manager.dialog_data.get("total_pages", 1)
    if page < total_pages:
        manager.dialog_data["page"] = page + 1
    await callback.answer()


async def prev_finished_page(callback: CallbackQuery, button: Button, manager: DialogManager) -> None:
    """Переключение на предыдущую страницу завершённых розыгрышей."""
    page = manager.dialog_data.get("page", 1)
    if page > 1:
        manager.dialog_data["page"] = page - 1
    await callback.answer()


async def back_to_list(callback: CallbackQuery, button: Button, manager: DialogManager) -> None:
    """Назад к списку розыгрышей (из деталей)."""
    list_type = manager.dialog_data.get("list_type", "active")
    await callback.answer()
    await manager.switch_to(ViewGiveawaysStates.VIEWING_LIST)
    if list_type == "finished":
        # остаёмся на текущей странице
        pass


async def go_back_to_choose_type(callback: CallbackQuery, button: Button, manager: DialogManager) -> None:
    """Назад к выбору типа списка."""
    await callback.answer()
    await manager.switch_to(ViewGiveawaysStates.CHOOSING_TYPE)


async def start_edit_from_details(callback: CallbackQuery, button: Button, manager: DialogManager) -> None:
    """Переход в диалог редактирования из деталей."""
    await callback.answer()
    current_id = manager.dialog_data.get("current_giveaway_id")
    if not current_id:
        await callback.answer("Розыгрыш не выбран", show_alert=True)
        return
    await manager.start(EditGiveawayStates.CHOOSING_FIELD, mode=StartMode.NORMAL)


async def start_delete_from_details(callback: CallbackQuery, button: Button, manager: DialogManager) -> None:
    """Переход к подтверждению удаления из деталей."""
    await callback.answer()
    current_id = manager.dialog_data.get("current_giveaway_id")
    if not current_id:
        await callback.answer("Розыгрыш не выбран", show_alert=True)
        return
    await manager.switch_to(EditGiveawayStates.CONFIRM_EDIT)


giveaway_view_dialog = Dialog(
    # Выбор типа списка
    Window(
        Const(MESSAGES["choose_giveaway_type"]),
        Row(
            Button(Const(BUTTONS["active_giveaways"]), id="active_list_btn", on_click=show_active),
            Button(Const(BUTTONS["finished_giveaways"]), id="finished_list_btn", on_click=show_finished),
        ),
        state=ViewGiveawaysStates.CHOOSING_TYPE,
    ),
    # Список активных или завершённых
    Window(
        Const(MESSAGES["active_giveaways"]),
        Select(
            Format("#{item.id} {item.title}"),
            id="active_giveaway_select",
            item_id_getter=lambda g: str(g.id),
            items="giveaways",
            on_click=on_giveaway_selected,
        ),
        Row(
            Button(Const(BUTTONS["back"]), id="back_to_type_from_active", on_click=go_back_to_choose_type),
        ),
        getter=active_giveaways_getter,
        state=ViewGiveawaysStates.VIEWING_LIST,
        when=lambda data, w, m: m.dialog_data.get("list_type") != "finished",
    ),
    # Список завершённых с пагинацией
    Window(
        Const(MESSAGES["finished_giveaways"]),
        Select(
            Format("#{item.id} {item.title}"),
            id="finished_giveaway_select",
            item_id_getter=lambda g: str(g.id),
            items="giveaways",
            on_click=on_giveaway_selected,
        ),
        Row(
            Button(Const("« Назад"), id="prev_page_btn", on_click=prev_finished_page),
            Button(Format("Стр. {page}/{total_pages}"), id="page_info_btn"),
            Button(Const("Вперёд »"), id="next_page_btn", on_click=next_finished_page),
        ),
        Row(
            Button(Const(BUTTONS["back"]), id="back_to_type_from_finished", on_click=go_back_to_choose_type),
        ),
        getter=finished_giveaways_getter,
        state=ViewGiveawaysStates.VIEWING_LIST,
        when=lambda data, w, m: m.dialog_data.get("list_type") == "finished",
    ),
    # Окно деталей (текст уже сформирован on_giveaway_selected)
    Window(
        Const(""),  # текст деталей уже отправлен в on_giveaway_selected
        Row(
            Button(Const(BUTTONS["back_to_list"]), id="back_to_list_btn", on_click=back_to_list),
            Button(Const(BUTTONS["edit_giveaway"]), id="edit_giveaway_btn", on_click=start_edit_from_details),
            Button(Const(BUTTONS["delete_giveaway"]), id="delete_giveaway_btn", on_click=start_delete_from_details),
        ),
        state=ViewGiveawaysStates.VIEWING_DETAILS,
    ),
)

