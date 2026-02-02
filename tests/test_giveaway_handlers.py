from unittest.mock import AsyncMock, patch

import pytest
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from handlers.giveaway_handlers import (
    callback_create_giveaway,
    process_giveaway_title,
    process_giveaway_description,
    callback_skip_media,
    process_giveaway_media,
    process_winner_places,
    proceed_to_channel_selection,
    callback_select_channel,
    process_end_time,
    confirm_create_giveaway,
    callback_cancel_creation,
)


def create_callback_query(data: str):
    callback = AsyncMock(spec=CallbackQuery)
    callback.data = data
    callback.message = AsyncMock()
    callback.message.edit_text = AsyncMock()
    callback.message.edit_reply_markup = AsyncMock()
    callback.answer = AsyncMock()
    callback.from_user = AsyncMock()
    callback.bot = AsyncMock()
    return callback


def create_message(
        text: str = None,
        has_photo: bool = False,
        has_video: bool = False,
        has_animation: bool = False,
        has_document: bool = False,
):
    message = AsyncMock(spec=Message)
    message.text = text
    message.html_text = text
    message.answer = AsyncMock()
    message.bot = AsyncMock()
    message.forward_from_chat = None

    if has_photo:
        photo_mock = AsyncMock()
        photo_mock.file_id = "photo_id"
        message.photo = [photo_mock]
    else:
        message.photo = None

    if has_video:
        video_mock = AsyncMock()
        video_mock.file_id = "video_id"
        message.video = video_mock
    else:
        message.video = None

    if has_animation:
        animation_mock = AsyncMock()
        animation_mock.file_id = "animation_id"
        message.animation = animation_mock
    else:
        message.animation = None

    if has_document:
        document_mock = AsyncMock()
        document_mock.file_id = "document_id"
        message.document = document_mock
    else:
        message.document = None

    return message


def create_state():
    state = AsyncMock(spec=FSMContext)
    state.get_state.return_value = None
    state.set_state = AsyncMock()
    state.update_data = AsyncMock()
    state.get_data = AsyncMock(return_value={})
    state.clear = AsyncMock()
    return state


@pytest.mark.asyncio
async def test_callback_create_giveaway():
    """
    Тест для проверки callback_create_giveaway.
    """
    callback = create_callback_query("create_giveaway")
    state = create_state()

    with patch.dict("handlers.giveaway_handlers.MESSAGES", {"create_giveaway_start": "Start"}):
        with patch("handlers.giveaway_handlers.get_back_to_menu_keyboard", return_value="keyboard"):
            await callback_create_giveaway(callback, state)  # ✅ await

    callback.message.edit_text.assert_called_once_with("Start", reply_markup="keyboard")
    state.set_state.assert_called_once()
    callback.answer.assert_called_once()


@pytest.mark.asyncio
async def test_process_giveaway_title_success():
    """
    Тест для проверки process_giveaway_title с валидным заголовком.
    """
    message = create_message("Test Title")
    state = create_state()

    await process_giveaway_title(message, state)  # ✅ await

    state.update_data.assert_called_once_with(title="Test Title")
    state.set_state.assert_called_once()


@pytest.mark.asyncio
async def test_process_giveaway_title_too_long():
    """
    Тест для проверки process_giveaway_title с слишком длинным заголовком.
    """
    message = create_message("a" * 256)
    state = create_state()

    with patch.dict("handlers.giveaway_handlers.MESSAGES", {"title_too_long": "Too long"}):
        await process_giveaway_title(message, state)  # ✅ await

    message.answer.assert_called_once_with("Too long")


@pytest.mark.asyncio
async def test_process_giveaway_description_success():
    """
    Тест для проверки process_giveaway_description с валидным описанием.
    """
    message = create_message("Test Description")
    state = create_state()

    await process_giveaway_description(message, state)  # ✅ await

    state.update_data.assert_called_once_with(description="Test Description")
    state.set_state.assert_called_once()


@pytest.mark.asyncio
async def test_process_giveaway_description_too_long():
    """
    Тест для проверки process_giveaway_description с слишком длинным описанием.
    """
    message = create_message("a" * 4001)
    state = create_state()

    with patch.dict("handlers.giveaway_handlers.MESSAGES", {"description_too_long": "Too long"}):
        await process_giveaway_description(message, state)  # ✅ await

    message.answer.assert_called_once_with("Too long")


@pytest.mark.asyncio
async def test_callback_skip_media():
    """
    Тест для проверки callback_skip_media.
    """
    callback = create_callback_query("skip_media")
    state = create_state()

    with patch("handlers.giveaway_handlers.proceed_to_winner_places") as mock_proceed:
        await callback_skip_media(callback, state)  # ✅ await

    mock_proceed.assert_called_once_with(callback.message, state)
    callback.answer.assert_called_once()


@pytest.mark.asyncio
async def test_process_giveaway_media_photo():
    """
    Тест для проверки process_giveaway_media с фото.
    """
    message = create_message(has_photo=True)
    state = create_state()

    with patch("handlers.giveaway_handlers.proceed_to_winner_places") as mock_proceed:
        await process_giveaway_media(message, state)  # ✅ await

    state.update_data.assert_called_once()
    mock_proceed.assert_called_once_with(message, state)


@pytest.mark.asyncio
async def test_process_giveaway_media_invalid():
    """
    Тест для проверки process_giveaway_media с неподдерживаемым медиа.
    """
    message = create_message()
    message.answer = AsyncMock()

    await process_giveaway_media(message, state=None)  # ✅ await

    message.answer.assert_called_once_with("❌ Поддерживаются только фото, видео, GIF и документы")


@pytest.mark.asyncio
async def test_process_winner_places_success():
    """
    Тест для проверки process_winner_places с валидным количеством.
    """
    message = create_message("5")
    state = create_state()

    with patch("handlers.giveaway_handlers.proceed_to_winner_places") as mock_proceed:
        await process_winner_places(message, state)  # ✅ await

    state.update_data.assert_called_once_with(winner_places=5)
    state.set_state.assert_called_once()
    mock_proceed.assert_called_once_with(message, state)


@pytest.mark.asyncio
async def test_process_winner_places_invalid():
    """
    Тест для проверки process_winner_places с невалидным количеством.
    """
    message = create_message("abc")
    state = create_state()

    with patch.dict("handlers.giveaway_handlers.MESSAGES", {"invalid_winner_places": "Invalid"}):
        await process_winner_places(message, state)  # ✅ await

    message.answer.assert_called_once_with("Invalid")


@pytest.mark.asyncio
async def test_proceed_to_channel_selection_no_channels():
    """
    Тест для проверки proceed_to_channel_selection без каналов.
    """
    message = create_message()
    state = create_state()

    with patch("handlers.giveaway_handlers.get_all_channels", return_value=[]):
        with patch.dict("handlers.giveaway_handlers.MESSAGES", {"no_channels": "No channels"}):
            with patch("handlers.giveaway_handlers.get_back_to_menu_keyboard", return_value="keyboard"):
                await proceed_to_channel_selection(message, state)  # ✅ await

    message.answer.assert_called_once_with(
        "No channels",
        reply_markup="keyboard"
    )
    state.clear.assert_called_once()


@pytest.mark.asyncio
async def test_callback_select_channel():
    """
    Тест для проверки callback_select_channel.
    """
    callback = create_callback_query("select_channel_123")
    state = create_state()

    await callback_select_channel(callback, state)  # ✅ await

    state.update_data.assert_called_once_with(channel_id=123)
    state.set_state.assert_called_once()
    callback.message.edit_text.assert_called_once()
    callback.answer.assert_called_once()


@pytest.mark.asyncio
async def test_process_end_time_success():
    """
    Тест для проверки process_end_time с валидным временем.
    """
    message = create_message("2025-12-31 23:59")
    state = create_state()

    end_time = "2025-12-31 23:59"

    with patch("handlers.giveaway_handlers.parse_datetime", return_value=end_time):
        with patch("handlers.giveaway_handlers.is_future_datetime", return_value=True):
            with patch("handlers.giveaway_handlers.get_all_channels",
                       return_value=[AsyncMock(channel_id=123, channel_name="Test")]):
                with patch("handlers.giveaway_handlers.get_confirm_keyboard", return_value="keyboard"):
                    with patch.dict("handlers.giveaway_handlers.MESSAGES", {"confirm_giveaway": "Confirm {title}"}):
                        await process_end_time(message, state)  # ✅ await

    state.update_data.assert_called()
    state.set_state.assert_called_once()
    message.answer.assert_called_once()


@pytest.mark.asyncio
async def test_confirm_create_giveaway_success():
    """
    Тест для проверки confirm_create_giveaway при успешном создании.
    """
    callback = create_callback_query("confirm")
    state = create_state()
    state.get_data.return_value = {
        "title": "Test",
        "description": "Desc",
        "end_time": "2025-12-31 23:59",
        "channel_id": 123,
        "created_by": 999,
        "winner_places": 1,
        "media_type": None,
        "media_file_id": None
    }

    mock_giveaway = AsyncMock()
    mock_giveaway.id = 1
    mock_giveaway.status = "active"
    mock_giveaway.channel_id = 123
    mock_giveaway.message_id = 999

    with patch("handlers.giveaway_handlers.create_giveaway", return_value=mock_giveaway):
        with patch("handlers.giveaway_handlers.get_participants_count", return_value=0):
            with patch("handlers.giveaway_handlers.get_participate_keyboard", return_value="keyboard"):
                with patch("handlers.giveaway_handlers.update_giveaway_message_id"):
                    with patch("handlers.giveaway_handlers.schedule_giveaway_finish"):
                        with patch.dict("handlers.giveaway_handlers.MESSAGES", {"giveaway_created": "Created"}):
                            with patch("handlers.giveaway_handlers.get_back_to_menu_keyboard", return_value="keyboard"):
                                await confirm_create_giveaway(callback, state)  # ✅ await

    callback.message.edit_text.assert_called_once_with("Created", reply_markup="keyboard")
    state.clear.assert_called_once()
    callback.answer.assert_called_once()


@pytest.mark.asyncio
async def test_callback_cancel_creation():
    """
    Тест для проверки callback_cancel_creation.
    """
    callback = create_callback_query("cancel_creation")
    state = create_state()

    with patch.dict("handlers.giveaway_handlers.MESSAGES", {"giveaway_creation_cancelled": "Cancelled"}):
        with patch("handlers.giveaway_handlers.get_back_to_menu_keyboard", return_value="keyboard"):
            await callback_cancel_creation(callback, state)  # ✅ await

    callback.message.edit_text.assert_called_once_with("Cancelled", reply_markup="keyboard")
    state.clear.assert_called_once()
    callback.answer.assert_called_once()

