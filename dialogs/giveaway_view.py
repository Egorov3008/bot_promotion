from aiogram.types import CallbackQuery
from aiogram_dialog import Dialog, Window, DialogManager
from aiogram_dialog.widgets.kbd import Button, Row, Back, Start
from aiogram_dialog.widgets.text import Format, Const

# Используемые импорты - оставляем только то, что действительно используем
from states.admin_states import ViewGiveawaysStates, EditGiveawayStates, AdminStates
from database.database import (
    get_active_giveaways,
    get_finished_giveaways_page,
    count_finished_giveaways,
    get_giveaway,
)


async def active_giveaways_getter(dialog_manager: DialogManager, **kwargs):
    """Геттер для активных розыгрышей"""
    giveaways = await get_active_giveaways()
    return {
        "giveaways": giveaways,
        "count": len(giveaways) if giveaways else 0
    }


async def finished_giveaways_getter(dialog_manager: DialogManager, **kwargs):
    """Геттер для завершенных розыгрышей"""
    page = dialog_manager.dialog_data.get("page", 1)
    page_size = 10

    giveaways = await get_finished_giveaways_page(page, page_size)
    total_count = await count_finished_giveaways()
    total_pages = (total_count + page_size - 1) // page_size

    return {
        "giveaways": giveaways,
        "count": len(giveaways) if giveaways else 0,
        "page": page,
        "total_pages": total_pages,
    }


async def on_giveaway_selected(callback: CallbackQuery, widget, manager: DialogManager, item_id: str):
    """Обработчик выбора розыгрыша"""
    giveaway_id = int(item_id)
    giveaway = await get_giveaway(giveaway_id)

    if giveaway:
        manager.dialog_data["selected_giveaway_id"] = giveaway_id
        await manager.switch_to(ViewGiveawaysStates.VIEWING_DETAILS)


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


# Окно выбора типа списка
choose_list_type_window = Window(
    Const("📋 Выберите тип розыгрышей:"),
    Row(
        Button(Const("🎯 Активные"), id="show_active", on_click=on_show_active),
        Button(Const("✅ Завершенные"), id="show_finished", on_click=on_show_finished),
    ),
    Start(Const("🏠 В меню"), id="main_menu", state=AdminStates.MAIN_MENU),
    state=ViewGiveawaysStates.CHOOSING_TYPE,
)

# Окно просмотра активных розыгрышей
active_giveaways_window = Window(
    Format("🎯 Активные розыгрыши ({count}):"),
    # TODO: Здесь нужно добавить виджет для отображения списка розыгрышей
    Back(Const("◀️ Назад"), id="back"),
    state=ViewGiveawaysStates.VIEWING_ACTIVE,  # Уникальное состояние
    getter=active_giveaways_getter,
)

# Окно просмотра завершенных розыгрышей
finished_giveaways_window = Window(
    Format("📋 Завершенные розыгрыши (стр. {page}/{total_pages}, всего: {count}):"),
    # TODO: Здесь нужно добавить виджет для отображения списка розыгрышей
    Row(
        Button(Const("◀️ Предыдущая"), id="prev_page", on_click=lambda c, w, m: on_page_change(c, w, m, "prev")),
        Button(Const("▶️ Следующая"), id="next_page", on_click=lambda c, w, m: on_page_change(c, w, m, "next")),
    ),
    Back(Const("◀️ Назад"), id="back"),
    state=ViewGiveawaysStates.VIEWING_FINISHED,  # Уникальное состояние
    getter=finished_giveaways_getter,
)

# Окно детального просмотра розыгрыша
giveaway_details_window = Window(
    Format("🎯 Розыгрыш #{selected_giveaway_id}"),
    # TODO: Добавьте детальную информацию о розыгрыше с помощью геттера
    Row(
        # Просто переходим к редактированию
        Button(Const("✏️ Редактировать"), id="edit", on_click=lambda c, w, m: m.start(EditGiveawayStates.MAIN)),
        # Кнопка победителей - если состояние не существует, она просто ничего не сделает
        Button(Const("🏆 Победители"), id="winners", on_click=lambda c, w, m: None),
    ),
    Back(Const("◀️ Назад"), id="back"),
    state=ViewGiveawaysStates.VIEWING_DETAILS,
)

# Создаем диалог
giveaway_view_dialog = Dialog(
    choose_list_type_window,
    active_giveaways_window,
    finished_giveaways_window,
    giveaway_details_window,
)