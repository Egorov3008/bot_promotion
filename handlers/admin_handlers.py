import asyncio
import logging
from datetime import datetime
from typing import Optional

from aiogram import Dispatcher, Router, F
from aiogram.filters import StateFilter, Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery

from database.database import (
    get_all_admins, add_admin, remove_admin,
    get_all_channels, add_channel, remove_channel, add_channel_by_username,
    is_admin, get_channel, bulk_add_channel_subscribers,
    get_channel_subscribers_stats, clear_channel_subscribers
)
from database.models import Channel
from pyrogram_app.pyro_client import PyrogramClient
from states.admin_states import (
    AdminManagementStates, ChannelManagementStates,
    ViewGiveawaysStates, ChannelParsingStates
)
from texts.messages import MESSAGES, ADMIN_USER_ITEM, ADMIN_CHANNEL_ITEM
from utils.keyboards import (
    get_admin_management_keyboard, get_admins_list_keyboard,
    get_channel_management_keyboard, get_channels_list_keyboard,
    get_back_to_menu_keyboard, get_confirm_keyboard,
    get_giveaway_types_keyboard, get_add_channel_method_keyboard,
    get_start_parsing_keyboard, get_parsing_progress_keyboard,
    get_parsing_result_keyboard, get_cancel_parsing_keyboard,
    get_channel_parsing_actions_keyboard
)
from utils.channel_parser import (
    parse_channel_subscribers, check_pyrogram_client_admin_rights, get_pyrogram_client
)

router = Router()


# Управление администраторами
@router.callback_query(F.data == "admin_management")
async def callback_admin_management(callback: CallbackQuery, state: FSMContext):
    """Главное меню управления админами"""
    await state.set_state(AdminManagementStates.MAIN_ADMIN_MENU)
    await callback.message.edit_text(
        MESSAGES["admin_management_menu"],
        reply_markup=get_admin_management_keyboard()
    )
    await callback.answer()


@router.callback_query(F.data == "view_admins", StateFilter(AdminManagementStates.MAIN_ADMIN_MENU))
async def callback_view_admins(callback: CallbackQuery):
    """Просмотр списка администраторов"""
    admins = await get_all_admins()

    if not admins:
        await callback.answer("👥 Администраторов не найдено", show_alert=True)
        return

    admin_list = []
    for admin in admins:
        admin_info = ADMIN_USER_ITEM.format(
            name=admin.first_name or "Без имени",
            username=admin.username or "без username",
            user_id=admin.user_id
        )
        if admin.is_main_admin:
            admin_info += "\n👑 <b>Главный администратор</b>"
        admin_list.append(admin_info)

    admin_text = MESSAGES["current_admins"].format(admins="\n\n".join(admin_list))

    await callback.message.edit_text(
        admin_text,
        reply_markup=get_admins_list_keyboard(admins, "view")
    )
    await callback.answer()


@router.callback_query(F.data == "add_admin", StateFilter(AdminManagementStates.MAIN_ADMIN_MENU))
async def callback_add_admin(callback: CallbackQuery, state: FSMContext):
    """Начало добавления администратора"""
    await state.set_state(AdminManagementStates.WAITING_NEW_ADMIN_ID)
    await callback.message.edit_text(
        MESSAGES["enter_new_admin_id"],
        reply_markup=get_back_to_menu_keyboard()
    )
    await callback.answer()


@router.message(StateFilter(AdminManagementStates.WAITING_NEW_ADMIN_ID))
async def process_new_admin_id(message: Message, state: FSMContext, bot):
    """
    Обработка добавления админа через:
    - @username
    - t.me/username
    - https://t.me/username
    - user_id (число)
    """
    text = message.text.strip()
    username = None

    # Извлекаем username из разных форматов
    if text.startswith('@'):
        username = text[1:]
    elif 't.me/' in text:
        # Поддержка: https://t.me/username, t.me/username
        start = text.rfind('/') + 1
        username = text[start:]
    elif text.isdigit():
        # Это user_id — оставляем как есть
        try:
            user_id = int(text)
            await _save_admin_and_confirm(message, state, user_id=user_id, username=None, full_name=f"ID: {user_id}")
            return
        except ValueError:
            pass

    if not username:
        await message.answer(MESSAGES["invalid_username_or_id"])
        return

    # Пытаемся получить информацию о пользователе через get_chat
    try:
        chat = await bot.get_chat(f"@{username}" if not username.startswith('@') else username)

        if chat.type not in ("private",):  # Убедимся, что это пользователь
            await message.answer("❌ Указанная ссылка ведёт не на пользователя.")
            return

        user_id = chat.id
        full_name = f"{chat.first_name} {chat.last_name}" if chat.last_name else chat.first_name
        await _save_admin_and_confirm(message, state, user_id=user_id, username=chat.username, full_name=full_name)

    except Exception as e:
        # Логируем ошибку, но не показываем пользователю детали
        logging.warning(f"Не удалось найти пользователя по username '{username}': {e}")

        # Предлагаем ввести ID вручную
        await message.answer(
            MESSAGES["cannot_resolve_username"].format(username=username) +
            "\n\n" + MESSAGES["fallback_enter_id"],
            parse_mode="HTML"
        )


async def _save_admin_and_confirm(message: Message, state: FSMContext, user_id: int, username: str, full_name: str):
    """Сохраняет данные админа и переходит к подтверждению"""
    # Проверим, не является ли уже админом
    if await is_admin(user_id):
        await message.answer(MESSAGES["admin_already_exists"])
        await state.clear()
        return

    await state.update_data(
        new_admin_id=user_id,
        new_admin_username=username,
        new_admin_name=full_name
    )
    await state.set_state(AdminManagementStates.CONFIRM_ADD_ADMIN)

    display_name = f"<a href='tg://user?id={user_id}'>{full_name}</a>" if full_name else f"ID: {user_id}"

    await message.answer(
        MESSAGES["confirm_add_admin"].format(user=display_name),
        reply_markup=get_confirm_keyboard(),
        parse_mode="HTML"
    )


@router.callback_query(F.data == "confirm", StateFilter(AdminManagementStates.CONFIRM_ADD_ADMIN))
async def confirm_add_admin(callback: CallbackQuery, state: FSMContext):
    """Подтверждение добавления администратора"""
    data = await state.get_data()

    success = await add_admin(
        user_id=data["new_admin_id"],
        username=data.get("new_admin_username"),
        first_name=data.get("new_admin_name")
    )

    if success:
        await callback.message.edit_text(
            MESSAGES["admin_added"],
            reply_markup=get_back_to_menu_keyboard()
        )
    else:
        await callback.message.edit_text(
            MESSAGES["admin_already_exists"],
            reply_markup=get_back_to_menu_keyboard()
        )

    await state.set_state(AdminManagementStates.MAIN_ADMIN_MENU)
    await callback.answer()


@router.callback_query(F.data == "remove_admin", StateFilter(AdminManagementStates.MAIN_ADMIN_MENU))
async def callback_remove_admin(callback: CallbackQuery, state: FSMContext):
    """Выбор администратора для удаления"""
    admins = await get_all_admins()
    removable_admins = [admin for admin in admins if not admin.is_main_admin]

    if not removable_admins:
        await callback.answer("Нет администраторов для удаления", show_alert=True)
        return

    await state.set_state(AdminManagementStates.CHOOSING_ADMIN_TO_REMOVE)
    await callback.message.edit_text(
        MESSAGES["choose_admin_to_remove"],
        reply_markup=get_admins_list_keyboard(removable_admins, "remove")
    )
    await callback.answer()


@router.callback_query(F.data.startswith("remove_admin_"), StateFilter(AdminManagementStates.CHOOSING_ADMIN_TO_REMOVE))
async def callback_confirm_remove_admin(callback: CallbackQuery, state: FSMContext):
    """Подтверждение удаления администратора"""
    user_id = int(callback.data.split("_")[2])

    # Получаем информацию об админе
    admins = await get_all_admins()
    admin_to_remove = next((admin for admin in admins if admin.user_id == user_id), None)

    if not admin_to_remove:
        await callback.answer("Администратор не найден", show_alert=True)
        return

    if admin_to_remove.is_main_admin:
        await callback.answer(MESSAGES["cannot_remove_main_admin"], show_alert=True)
        return

    await state.update_data(remove_admin_id=user_id)
    await state.set_state(AdminManagementStates.CONFIRM_REMOVE_ADMIN)

    admin_name = admin_to_remove.first_name or f"ID: {user_id}"
    if admin_to_remove.username:
        admin_name += f" (@{admin_to_remove.username})"

    await callback.message.edit_text(
        MESSAGES["confirm_remove_admin"].format(admin=admin_name),
        reply_markup=get_confirm_keyboard()
    )
    await callback.answer()


@router.callback_query(F.data == "confirm", StateFilter(AdminManagementStates.CONFIRM_REMOVE_ADMIN))
async def confirm_remove_admin(callback: CallbackQuery, state: FSMContext):
    """Окончательное удаление администратора"""
    data = await state.get_data()
    user_id = data["remove_admin_id"]

    success = await remove_admin(user_id)

    if success:
        await callback.message.edit_text(
            MESSAGES["admin_removed"],
            reply_markup=get_back_to_menu_keyboard()
        )
    else:
        await callback.message.edit_text(
            MESSAGES["error_occurred"],
            reply_markup=get_back_to_menu_keyboard()
        )

    await state.set_state(AdminManagementStates.MAIN_ADMIN_MENU)
    await callback.answer()


# Управление каналами
@router.callback_query(F.data == "channel_management")
async def callback_channel_management(callback: CallbackQuery, state: FSMContext):
    """Главное меню управления каналами"""
    await state.set_state(ChannelManagementStates.MAIN_CHANNEL_MENU)
    await callback.message.edit_text(
        MESSAGES["channel_management_menu"],
        reply_markup=get_channel_management_keyboard()
    )
    await callback.answer()


@router.callback_query(F.data == "view_channels", StateFilter(ChannelManagementStates.MAIN_CHANNEL_MENU))
async def callback_view_channels(callback: CallbackQuery):
    """Просмотр списка каналов"""
    channels = await get_all_channels()

    if not channels:
        await callback.answer("📺 Каналов не найдено", show_alert=True)
        return

    channel_list = []
    for channel in channels:
        # Получаем информацию об админе, который добавил канал
        admin_name = "Неизвестно"
        if channel.admin:
            admin_name = channel.admin.first_name or f"ID: {channel.added_by}"
            if channel.admin.username:
                admin_name += f" (@{channel.admin.username})"

        channel_info = ADMIN_CHANNEL_ITEM.format(
            name=channel.channel_name,
            username=f"@{channel.channel_username}" if channel.channel_username else "Без username",
            admin=admin_name
        )
        channel_list.append(channel_info)

    channel_text = MESSAGES["current_channels"].format(channels="\n\n".join(channel_list))

    await callback.message.edit_text(
        channel_text,
        reply_markup=get_channels_list_keyboard(channels, "view")
    )
    await callback.answer()


@router.callback_query(F.data == "add_channel", StateFilter(ChannelManagementStates.MAIN_CHANNEL_MENU))
async def callback_add_channel(callback: CallbackQuery, state: FSMContext):
    """Выбор способа добавления канала"""
    await callback.message.edit_text(
        MESSAGES["enter_channel_info"],
        reply_markup=get_add_channel_method_keyboard()
    )
    await callback.answer()


@router.callback_query(F.data == "add_channel_by_link", StateFilter(ChannelManagementStates.MAIN_CHANNEL_MENU))
async def callback_add_channel_by_link(callback: CallbackQuery, state: FSMContext):
    """Добавление канала по ссылке"""
    await state.set_state(ChannelManagementStates.WAITING_CHANNEL_LINK)
    logging.info(f"[FSM] Переход в WAITING_CHANNEL_LINK для user={callback.from_user.id}")
    await callback.message.edit_text(
        MESSAGES["enter_channel_link"],
        reply_markup=get_back_to_menu_keyboard()
    )
    await callback.answer()


@router.callback_query(F.data == "add_channel_by_forward", StateFilter(ChannelManagementStates.MAIN_CHANNEL_MENU))
async def callback_add_channel_by_forward(callback: CallbackQuery, state: FSMContext):
    """Добавление канала через пересылку"""
    await state.set_state(ChannelManagementStates.WAITING_CHANNEL_INFO)
    await callback.message.edit_text(
        MESSAGES["enter_channel_forward"],
        reply_markup=get_back_to_menu_keyboard()
    )
    await callback.answer()


@router.message(StateFilter(ChannelManagementStates.WAITING_CHANNEL_LINK))
async def process_channel_link(message: Message, state: FSMContext):
    """Обработка ссылки на канал"""
    current_state = await state.get_state()
    logging.info(
        f"[FSM] process_channel_link вызван. message={message.text!r}, user={message.from_user.id}, state={current_state}")
    if current_state != ChannelManagementStates.WAITING_CHANNEL_LINK.state:
        await message.answer("❌ Ошибка состояния. Попробуйте начать добавление канала заново через меню.")
        return
    channel_input = message.text.strip()

    # Добавляем канал по username/ссылке
    success, result_message = await add_channel_by_username(
        channel_username=channel_input,
        bot=message.bot,
        added_by=message.from_user.id
    )

    # Логирование
    logging.info(f"[FSM] Добавление канала по ссылке: success={success}, msg={result_message}")

    # Гарантированный ответ
    if not result_message:
        result_message = "✅ Канал добавлен!" if success else "❌ Ошибка при добавлении канала. Попробуйте ещё раз."

    await message.answer(
        result_message,
        reply_markup=get_back_to_menu_keyboard()
    )
    if success:
        await state.set_state(ChannelManagementStates.MAIN_CHANNEL_MENU)


@router.message(StateFilter(ChannelManagementStates.WAITING_CHANNEL_INFO))
async def process_channel_info(message: Message, state: FSMContext):
    """Обработка информации о канале (пересылка)"""
    if not message.forward_from_chat:
        await message.answer("❌ Пожалуйста, перешлите сообщение из канала")
        return

    channel = message.forward_from_chat

    if channel.type != "channel":
        await message.answer("❌ Это не канал!")
        return

    # Проверяем, является ли бот администратором канала
    try:
        bot_member = await message.bot.get_chat_member(channel.id, message.bot.id)
        if bot_member.status not in ["administrator", "creator"]:
            await message.answer(MESSAGES["bot_not_admin"])
            return
    except Exception as e:
        await message.answer(MESSAGES["bot_not_admin"])
        return

    # Сохраняем данные канала
    await state.update_data(
        channel_id=channel.id,
        channel_name=channel.title,
        channel_username=channel.username
    )
    await state.set_state(ChannelManagementStates.CONFIRM_ADD_CHANNEL)

    # Явный ответ
    await message.answer(
        MESSAGES["confirm_add_channel"].format(channel=channel.title),
        reply_markup=get_confirm_keyboard()
    )
    logging.info(f"[FSM] Канал через пересылку: {channel.title} ({channel.id})")


@router.callback_query(F.data == "confirm", StateFilter(ChannelManagementStates.CONFIRM_ADD_CHANNEL))
async def confirm_add_channel(callback: CallbackQuery, state: FSMContext):
    """Подтверждение добавления канала с предложением парсинга"""
    data = await state.get_data()

    success = await add_channel(
        channel_id=data["channel_id"],
        channel_name=data["channel_name"],
        channel_username=data["channel_username"],
        added_by=callback.from_user.id
    )

    if success:
        # Показываем сообщение о добавлении канала с предложением парсинга
        channel_display = f"@{data['channel_username']}" if data.get("channel_username") else data["channel_name"]
        await callback.message.edit_text(
            MESSAGES["channel_added_parsing_prompt"].format(channel=channel_display),
            reply_markup=get_start_parsing_keyboard()
        )
        # Сохраняем данные для парсинга в состояние
        await state.update_data(
            channel_id=data["channel_id"],
            channel_name=data["channel_name"],
            channel_username=data["channel_username"]
        )
        # НЕ переходим в MAIN_CHANNEL_MENU, остаемся для выбора парсинга
    else:
        await callback.message.edit_text(
            MESSAGES["channel_already_exists"],
            reply_markup=get_back_to_menu_keyboard()
        )
        await state.set_state(ChannelManagementStates.MAIN_CHANNEL_MENU)

    await callback.answer()


@router.callback_query(F.data == "remove_channel", StateFilter(ChannelManagementStates.MAIN_CHANNEL_MENU))
async def callback_remove_channel(callback: CallbackQuery, state: FSMContext):
    """Выбор канала для удаления"""
    channels = await get_all_channels()

    if not channels:
        await callback.answer("Нет каналов для удаления", show_alert=True)
        return

    await state.set_state(ChannelManagementStates.CHOOSING_CHANNEL_TO_REMOVE)
    await callback.message.edit_text(
        MESSAGES["choose_channel_to_remove"],
        reply_markup=get_channels_list_keyboard(channels, "remove")
    )
    await callback.answer()


@router.callback_query(F.data.startswith("remove_channel_"),
                       StateFilter(ChannelManagementStates.CHOOSING_CHANNEL_TO_REMOVE))
async def callback_confirm_remove_channel(callback: CallbackQuery, state: FSMContext):
    """Подтверждение удаления канала"""
    channel_id = int(callback.data.split("_")[2])

    # Получаем информацию о канале
    channels = await get_all_channels()
    channel_to_remove = next((ch for ch in channels if ch.channel_id == channel_id), None)

    if not channel_to_remove:
        await callback.answer("Канал не найден", show_alert=True)
        return

    await state.update_data(remove_channel_id=channel_id)
    await state.set_state(ChannelManagementStates.CONFIRM_REMOVE_CHANNEL)

    await callback.message.edit_text(
        MESSAGES["confirm_remove_channel"].format(channel=channel_to_remove.channel_name),
        reply_markup=get_confirm_keyboard()
    )
    await callback.answer()


@router.callback_query(F.data == "confirm", StateFilter(ChannelManagementStates.CONFIRM_REMOVE_CHANNEL))
async def confirm_remove_channel(callback: CallbackQuery, state: FSMContext):
    """Окончательное удаление канала с очисткой подписчиков"""
    data = await state.get_data()
    channel_id = data["remove_channel_id"]

    # Очищаем подписчиков канала перед удалением
    cleared_count = await clear_channel_subscribers(channel_id)
    logging.info(f"Очищено {cleared_count} подписчиков при удалении канала {channel_id}")

    success = await remove_channel(channel_id)

    if success:
        await callback.message.edit_text(
            MESSAGES["channel_removed"],
            reply_markup=get_back_to_menu_keyboard()
        )
    else:
        await callback.message.edit_text(
            MESSAGES["error_occurred"],
            reply_markup=get_back_to_menu_keyboard()
        )

    await state.set_state(ChannelManagementStates.MAIN_CHANNEL_MENU)
    await callback.answer()


# Просмотр розыгрышей
@router.callback_query(F.data == "view_giveaways")
async def callback_view_giveaways(callback: CallbackQuery, state: FSMContext):
    """Выбор типа розыгрышей для просмотра"""
    await state.set_state(ViewGiveawaysStates.CHOOSING_TYPE)
    await callback.message.edit_text(
        MESSAGES["choose_giveaway_type"],
        reply_markup=get_giveaway_types_keyboard()
    )
    await callback.answer()


# Общие callback'и для отмены и возврата
@router.callback_query(F.data == "cancel")
async def callback_cancel(callback: CallbackQuery, state: FSMContext):
    """Отмена текущей операции"""
    await state.clear()
    await callback.message.edit_text(
        MESSAGES["admin_main_menu"],
        reply_markup=get_admin_management_keyboard()
    )
    await callback.answer("❌ Операция отменена")


@router.message(
    StateFilter((ChannelManagementStates.WAITING_CHANNEL_LINK, ChannelManagementStates.MAIN_CHANNEL_MENU))
)
async def catch_channel_link_message(message: Message, state: FSMContext):
    """Универсальный перехватчик: если админ прислал ссылку/username канала — пытаемся добавить канал.
    Работает в состояниях MAIN_CHANNEL_MENU и WAITING_CHANNEL_LINK."""
    text = (message.text or "").strip()
    # Простая эвристика: распознаём @username, t.me/username, http(s)://t.me/username, bare username
    if not text:
        return
    looks_like_link = text.startswith("@") or "t.me/" in text or (text.isascii() and text.replace("_", "").isalnum())
    if not looks_like_link:
        return  # не похоже на ссылку — не перехватываем

    logging.info(f"[FSM] Перехват ссылки на канал: '{text}' от user={message.from_user.id}")
    # Убеждаемся, что состояние правильное
    await state.set_state(ChannelManagementStates.WAITING_CHANNEL_LINK)
    # Переиспользуем логику добавления по ссылке
    success, result_message = await add_channel_by_username(
        channel_username=text,
        bot=message.bot,
        added_by=message.from_user.id
    )
    if not result_message:
        result_message = "✅ Канал добавлен!" if success else "❌ Ошибка при добавлении канала. Убедитесь, что бот — админ, и это публичный канал."

    await message.answer(result_message, reply_markup=get_back_to_menu_keyboard())
    if success:
        await state.set_state(ChannelManagementStates.MAIN_CHANNEL_MENU)


# ==================== ПАРСИНГ ПОДПИСЧИКОВ КАНАЛА ====================

@router.callback_query(F.data == "start_parsing", StateFilter(ChannelManagementStates.CONFIRM_ADD_CHANNEL))
async def callback_start_parsing(callback: CallbackQuery, state: FSMContext):
    """Запуск парсинга подписчиков после добавления канала"""
    data = await state.get_data()
    channel_id = data.get("channel_id")

    if not channel_id:
        await callback.message.edit_text(
            MESSAGES["error_occurred"],
            reply_markup=get_back_to_menu_keyboard()
        )
        await callback.answer()
        return

    # Получаем канал из БД
    channel = await get_channel(channel_id)
    if not channel:
        await callback.message.edit_text(
            MESSAGES["error_occurred"],
            reply_markup=get_back_to_menu_keyboard()
        )
        await callback.answer()
        return

    # Переходим в состояние парсинга
    await state.set_state(ChannelParsingStates.PARSING_CHANNEL)
    await state.update_data(
        channel_id=channel_id,
        channel_name=channel.channel_name,
        start_time=datetime.now().isoformat()
    )

    # Запускаем парсинг
    await callback.message.edit_text(
        MESSAGES["parsing_started"].format(
            channel=channel.channel_name,
            subscriber_count="..."
        ),
        reply_markup=get_parsing_progress_keyboard()
    )

    # Запускаем асинхронную задачу парсинга
    pyro_client = get_pyrogram_client()
    asyncio.create_task(_run_parsing(callback.message, state, pyro_client))

    await callback.answer()


@router.callback_query(F.data == "skip_parsing", StateFilter(ChannelManagementStates.CONFIRM_ADD_CHANNEL))
async def callback_skip_parsing(callback: CallbackQuery, state: FSMContext):
    """Пропуск парсинга подписчиков"""
    data = await state.get_data()
    channel_name = data.get("channel_name", "Канал")

    await state.clear()
    await callback.message.edit_text(
        MESSAGES["parsing_not_started"].format(channel=channel_name),
        reply_markup=get_back_to_menu_keyboard()
    )
    await callback.answer()


async def _run_parsing(message: Message, state: FSMContext, pyro_client: PyrogramClient):
    """Фоновый процесс парсинга подписчиков"""
    try:
        data = await state.get_data()
        channel_id = data.get("channel_id")
        channel_name = data.get("channel_name")
        app = await pyro_client.start()

        # Проверяем права администратора
        has_rights = await check_pyrogram_client_admin_rights(app, channel_id)
        if not has_rights:
            await state.set_state(ChannelParsingStates.PARSING_CANCELLED)
            await message.edit_text(
                MESSAGES["parsing_error"].format(
                    channel=channel_name,
                    error="У Pyrogram клиента нет прав администратора в канале"
                ),
                reply_markup=get_parsing_result_keyboard(channel_id)
            )
            return

        # Выполняем парсинг
        subscribers, with_username_count, bots_count = await parse_channel_subscribers(
            client=app,
            channel_id=channel_id
        )

        if not subscribers:
            await state.set_state(ChannelParsingStates.PARSING_COMPLETE)
            await message.edit_text(
                MESSAGES["parsing_no_subscribers"].format(channel=channel_name),
                reply_markup=get_parsing_result_keyboard(channel_id)
            )
            return

        # Сохраняем подписчиков в БД
        added, updated = await bulk_add_channel_subscribers(channel_id, subscribers)

        # Получаем статистику
        stats = await get_channel_subscribers_stats(channel_id)

        # Формируем сообщение с результатами
        result_message = MESSAGES["parsing_complete"].format(
            channel=channel_name,
            total=stats["active"],
            with_username=stats["with_username"],
            without_username=stats["without_username"],
            added=added,
            updated=updated
        )

        await state.set_state(ChannelParsingStates.PARSING_COMPLETE)
        await message.edit_text(
            result_message,
            reply_markup=get_parsing_result_keyboard(channel_id)
        )

        logging.info(f"Парсинг канала {channel_name} ({channel_id}) завершен: добавлено={added}, обновлено={updated}")

    except Exception as e:
        logging.error(f"Ошибка при парсинге канала: {e}")
        data = await state.get_data()
        channel_name = data.get("channel_name", "Канал")

        await state.set_state(ChannelParsingStates.PARSING_CANCELLED)
        await message.edit_text(
            MESSAGES["parsing_error"].format(
                channel=channel_name,
                error=str(e)
            ),
            reply_markup=get_parsing_result_keyboard(data.get("channel_id"))
        )


@router.callback_query(F.data == "cancel_parsing", StateFilter(ChannelParsingStates.PARSING_CHANNEL))
async def callback_cancel_parsing(callback: CallbackQuery, state: FSMContext):
    """Запрос на отмену парсинга"""
    await callback.message.edit_text(
        MESSAGES["confirm_delete"].format(title="парсинг"),
        reply_markup=get_cancel_parsing_keyboard()
    )
    await callback.answer()


@router.callback_query(F.data == "confirm_cancel_parsing", StateFilter(ChannelParsingStates.PARSING_CHANNEL))
async def callback_confirm_cancel_parsing(callback: CallbackQuery, state: FSMContext):
    """Подтверждение отмены парсинга"""
    data = await state.get_data()
    channel_id = data.get("channel_id")
    channel_name = data.get("channel_name", "Канал")

    await state.set_state(ChannelParsingStates.PARSING_CANCELLED)
    await callback.message.edit_text(
        MESSAGES["parsing_cancelled"].format(
            channel=channel_name,
            processed="0"
        ),
        reply_markup=get_parsing_result_keyboard(channel_id)
    )
    await callback.answer()


@router.callback_query(F.data == "continue_parsing", StateFilter(ChannelParsingStates.PARSING_CHANNEL))
async def callback_continue_parsing(callback: CallbackQuery, state: FSMContext):
    """Продолжение парсинга после отмены"""
    data = await state.get_data()
    channel_name = data.get("channel_name", "Канал")

    await callback.message.edit_text(
        MESSAGES["parsing_in_progress"].format(
            channel=channel_name,
            processed="...",
            total="...",
            percent="0"
        ),
        reply_markup=get_parsing_progress_keyboard()
    )
    await callback.answer()


@router.callback_query(F.data.startswith("view_parsing_stats_"))
async def callback_view_parsing_stats(callback: CallbackQuery, state: FSMContext):
    """Просмотр статистики парсинга канала"""
    channel_id = int(callback.data.split("_")[-1])

    # Получаем канал
    channel = await get_channel(channel_id)
    if not channel:
        await callback.answer("Канал не найден", show_alert=True)
        return

    # Получаем статистику
    stats = await get_channel_subscribers_stats(channel_id)

    stats_text = MESSAGES["parsing_admin_notification"].format(
        channel=channel.channel_name,
        total=stats["total"],
        with_username=stats["with_username"],
        without_username=stats["without_username"],
        new=stats["active"],
        updated=0
    )

    await state.set_state(ChannelParsingStates.VIEWING_PARSING_STATS)
    await callback.message.edit_text(
        stats_text,
        reply_markup=get_channel_parsing_actions_keyboard(channel_id)
    )
    await callback.answer()


@router.callback_query(F.data.startswith("reparse_channel_"))
async def callback_reparse_channel(callback: CallbackQuery, state: FSMContext):
    """Перепарсинг канала"""
    channel_id = int(callback.data.split("_")[-1])

    # Получаем канал
    channel = await get_channel(channel_id)
    if not channel:
        await callback.answer("Канал не найден", show_alert=True)
        return

    # Переходим в состояние парсинга
    await state.set_state(ChannelParsingStates.PARSING_CHANNEL)
    await state.update_data(
        channel_id=channel_id,
        channel_name=channel.channel_name,
        start_time=datetime.now().isoformat()
    )

    # Показываем сообщение о начале парсинга
    await callback.message.edit_text(
        MESSAGES["parsing_started"].format(
            channel=channel.channel_name,
            subscriber_count="..."
        ),
        reply_markup=get_parsing_progress_keyboard()
    )

    # Запускаем парсинг
    pyro_client = get_pyrogram_client()
    asyncio.create_task(_run_parsing(callback.message, state, pyro_client))

    await callback.answer()


@router.callback_query(F.data.startswith("start_parsing_"))
async def callback_start_parsing_from_menu(callback: CallbackQuery, state: FSMContext):
    """Запуск парсинга из меню действий с каналом"""
    channel_id = int(callback.data.split("_")[-1])

    # Получаем канал
    channel = await get_channel(channel_id)
    if not channel:
        await callback.answer("Канал не найден", show_alert=True)
        return

    # Переходим в состояние парсинга
    await state.set_state(ChannelParsingStates.PARSING_CHANNEL)
    await state.update_data(
        channel_id=channel_id,
        channel_name=channel.channel_name,
        start_time=datetime.now().isoformat()
    )

    # Показываем сообщение о начале парсинга
    await callback.message.edit_text(
        MESSAGES["parsing_started"].format(
            channel=channel.channel_name,
            subscriber_count="..."
        ),
        reply_markup=get_parsing_progress_keyboard()
    )

    # Запускаем парсинг
    pyro_client = get_pyrogram_client()
    asyncio.create_task(_run_parsing(callback.message, state, pyro_client))

    await callback.answer()


# Команда для ручного запуска парсинга всех каналов
@router.message(Command(commands=["parse_all_channels"]))
async def command_parse_all_channels(message: Message, state: FSMContext, pyro: PyrogramClient):
    """Команда для ручного парсинга всех каналов (только для главного админа)"""
    from config import config

    if message.from_user.id != config.MAIN_ADMIN_ID:
        await message.answer(MESSAGES["access_denied"])
        return

    channels = await get_all_channels()
    if not channels:
        await message.answer("Нет добавленных каналов для парсинга.")
        return

    await message.answer(f"🔄 Начинаю парсинг {len(channels)} каналов...")

    results = []
    for channel in channels:
        try:
            # Проверяем права
            has_rights = await check_pyrogram_client_admin_rights(pyro, channel.channel_id)
            if not has_rights:
                results.append(f"❌ {channel.channel_name}: нет прав администратора")
                continue

            # Парсим
            subscribers, with_username_count, bots_count = await parse_channel_subscribers(
                client=app,
                channel_id=channel.channel_id
            )

            if subscribers:
                added, updated = await bulk_add_channel_subscribers(channel.channel_id, subscribers)
                results.append(f"✅ {channel.channel_name}: добавлено={added}, обновлено={updated}")
            else:
                results.append(f"⚠️ {channel.channel_name}: нет подписчиков с username")

        except Exception as e:
            results.append(f"❌ {channel.channel_name}: ошибка - {str(e)[:50]}")

    # Отправляем отчет
    report = "📊 <b>Результаты парсинга всех каналов:</b>\n\n" + "\n".join(results)
    await message.answer(report, parse_mode="HTML")


# Команда для просмотра статистики парсинга
@router.message(Command(commands=["parsing_stats"]))
async def command_parsing_stats(message: Message):
    """Команда для просмотра статистики парсинга"""
    channels = await get_all_channels()
    if not channels:
        await message.answer("Нет добавленных каналов.")
        return

    stats_lines = []
    for channel in channels:
        stats = await get_channel_subscribers_stats(channel.channel_id)
        channel_name = f"@{channel.channel_username}" if channel.channel_username else channel.channel_name
        stats_lines.append(
            f"📺 <b>{channel_name}</b>\n"
            f"   👥 Всего: {stats['total']} | Активных: {stats['active']}\n"
            f"   📝 С username: {stats['with_username']} | Без: {stats['without_username']}"
        )

    stats_text = "📊 <b>Статистика подписчиков каналов:</b>\n\n" + "\n\n".join(stats_lines)
    await message.answer(stats_text, parse_mode="HTML")


def setup_admin_handlers(dp: Dispatcher):
    """Регистрация админских хендлеров"""
    dp.include_router(router)
