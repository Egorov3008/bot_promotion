import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from aiogram.types import CallbackQuery, Message, Update
from aiogram.fsm.context import FSMContext

from handlers.giveaway_handlers import router, parse_datetime, format_datetime, is_future_datetime, schedule_giveaway_finish, cancel_giveaway_schedule, get_all_channels, create_giveaway, update_giveaway_message_id, get_active_giveaways, get_finished_giveaways, get_giveaway, get_participants_count, delete_giveaway, get_winners, get_finished_giveaways_page, count_finished_giveaways, update_giveaway_fields

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

def create_message(text: str = None, has_photo: bool = False, has_video: bool = False, has_animation: bool = False, has_document: bool = False):
    message = AsyncMock(spec=Message)
    message.text = text
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


def test_router():
    """
    Тест для проверки существования роутера.
    """
    assert router is not None


def test_callback_create_giveaway():
    """
    Тест для проверки callback_create_giveaway.
    """
    callback = create_callback_query("create_giveaway")
    state = create_state()
    
    with patch.dict("handlers.giveaway_handlers.MESSAGES", {"create_giveaway_start": "Start"}):
        with patch("handlers.giveaway_handlers.get_back_to_menu_keyboard", return_value="keyboard"):
            callback_create_giveaway(callback, state)
            
    callback.message.edit_text.assert_called_once_with(
        "Start",
        reply_markup="keyboard"
    )
    state.set_state.assert_called_once()
    callback.answer.assert_called_once()


def test_process_giveaway_title_success():
    """
    Тест для проверки process_giveaway_title с валидным заголовком.
    """
    message = create_message("Test Title")
    state = create_state()
    
    process_giveaway_title(message, state)
    
    state.update_data.assert_called_once_with(title="Test Title")
    state.set_state.assert_called_once()


def test_process_giveaway_title_too_long():
    """
    Тест для проверки process_giveaway_title с слишком длинным заголовком.
    """
    message = create_message("a" * 256)
    state = create_state()
    
    with patch.dict("handlers.giveaway_handlers.MESSAGES", {"title_too_long": "Too long"}):
        process_giveaway_title(message, state)
        
    message.answer.assert_called_once_with("Too long")


def test_process_giveaway_description_success():
    """
    Тест для проверки process_giveaway_description с валидным описанием.
    """
    message = create_message("Test Description")
    state = create_state()
    
    process_giveaway_description(message, state)
    
    state.update_data.assert_called_once_with(description="Test Description")
    state.set_state.assert_called_once()


def test_process_giveaway_description_too_long():
    """
    Тест для проверки process_giveaway_description с слишком длинным описанием.
    """
    message = create_message("a" * 4001)
    state = create_state()
    
    with patch.dict("handlers.giveaway_handlers.MESSAGES", {"description_too_long": "Too long"}):
        process_giveaway_description(message, state)
        
    message.answer.assert_called_once_with("Too long")


def test_callback_skip_media():
    """
    Тест для проверки callback_skip_media.
    """
    callback = create_callback_query("skip_media")
    state = create_state()
    
    with patch("handlers.giveaway_handlers.proceed_to_winner_places") as mock_proceed:
        callback_skip_media(callback, state)
        
    mock_proceed.assert_called_once_with(callback.message, state)
    callback.answer.assert_called_once()


def test_process_giveaway_media_photo():
    """
    Тест для проверки process_giveaway_media с фото.
    """
    message = create_message(has_photo=True)
    state = create_state()
    
    with patch("handlers.giveaway_handlers.proceed_to_winner_places") as mock_proceed:
        process_giveaway_media(message, state)
        
    state.update_data.assert_called_once()
    mock_proceed.assert_called_once_with(message, state)


def test_process_giveaway_media_video():
    """
    Тест для проверки process_giveaway_media с видео.
    """
    message = create_message(has_video=True)
    state = create_state()
    
    with patch("handlers.giveaway_handlers.proceed_to_winner_places") as mock_proceed:
        process_giveaway_media(message, state)
        
    state.update_data.assert_called_once()
    mock_proceed.assert_called_once_with(message, state)


def test_process_giveaway_media_animation():
    """
    Тест для проверки process_giveaway_media с анимацией.
    """
    message = create_message(has_animation=True)
    state = create_state()
    
    with patch("handlers.giveaway_handlers.proceed_to_winner_places") as mock_proceed:
        process_giveaway_media(message, state)
        
    state.update_data.assert_called_once()
    mock_proceed.assert_called_once_with(message, state)


def test_process_giveaway_media_document():
    """
    Тест для проверки process_giveaway_media с документом.
    """
    message = create_message(has_document=True)
    state = create_state()
    
    with patch("handlers.giveaway_handlers.proceed_to_winner_places") as mock_proceed:
        process_giveaway_media(message, state)
        
    state.update_data.assert_called_once()
    mock_proceed.assert_called_once_with(message, state)


def test_process_giveaway_media_invalid():
    """
    Тест для проверки process_giveaway_media с неподдерживаемым медиа.
    """
    message = create_message()
    message.answer = AsyncMock()
    
    process_giveaway_media(message, None)
    
    message.answer.assert_called_once_with("❌ Поддерживаются только фото, видео, GIF и документы")


def test_process_winner_places_success():
    """
    Тест для проверки process_winner_places с валидным количеством.
    """
    message = create_message("5")
    state = create_state()
    
    with patch("handlers.giveaway_handlers.proceed_to_channel_selection") as mock_proceed:
        process_winner_places(message, state)
        
    state.update_data.assert_called_once_with(winner_places=5)
    state.set_state.assert_called_once()
    mock_proceed.assert_called_once_with(message, state)


def test_process_winner_places_invalid():
    """
    Тест для проверки process_winner_places с невалидным количеством.
    """
    message = create_message("abc")
    state = create_state()
    
    with patch.dict("handlers.giveaway_handlers.MESSAGES", {"invalid_winner_places": "Invalid"}):
        process_winner_places(message, state)
        
    message.answer.assert_called_once_with("Invalid")


def test_process_winner_places_out_of_range():
    """
    Тест для проверки process_winner_places с количеством вне диапазона.
    """
    message = create_message("0")
    state = create_state()
    
    with patch.dict("handlers.giveaway_handlers.MESSAGES", {"invalid_winner_places": "Invalid"}):
        process_winner_places(message, state)
        
    message.answer.assert_called_once_with("Invalid")


def test_proceed_to_channel_selection_no_channels():
    """
    Тест для проверки proceed_to_channel_selection без каналов.
    """
    message = create_message()
    state = create_state()
    
    with patch("handlers.giveaway_handlers.get_all_channels", return_value=[]):
        with patch.dict("handlers.giveaway_handlers.MESSAGES", {"no_channels": "No channels"}):
            with patch("handlers.giveaway_handlers.get_back_to_menu_keyboard", return_value="keyboard"):
                proceed_to_channel_selection(message, state)
                
    message.answer.assert_called_once_with(
        "No channels",
        reply_markup="keyboard"
    )
    state.clear.assert_called_once()


def test_callback_select_channel():
    """
    Тест для проверки callback_select_channel.
    """
    callback = create_callback_query("select_channel_123")
    state = create_state()
    
    callback_select_channel(callback, state)
    
    state.update_data.assert_called_once_with(channel_id=123)
    state.set_state.assert_called_once()
    callback.message.edit_text.assert_called_once()
    callback.answer.assert_called_once()


def test_process_end_time_success():
    """
    Тест для проверки process_end_time с валидным временем.
    """
    message = create_message("2025-12-31 23:59")
    state = create_state()
    
    with patch("handlers.giveaway_handlers.parse_datetime", return_value="2025-12-31 23:59"):
        with patch("handlers.giveaway_handlers.is_future_datetime", return_value=True):
            with patch("handlers.giveaway_handlers.get_all_channels", return_value=[AsyncMock(channel_id=123, channel_name="Test")]):
                with patch("handlers.giveaway_handlers.get_confirm_keyboard", return_value="keyboard"):
                    with patch.dict("handlers.giveaway_handlers.MESSAGES", {"confirm_giveaway": "Confirm {title}"}):
                        process_end_time(message, state)
                        
    state.update_data.assert_called()
    state.set_state.assert_called_once()
    message.answer.assert_called_once()


def test_process_end_time_invalid_datetime():
    """
    Тест для проверки process_end_time с невалидным временем.
    """
    message = create_message("invalid")
    state = create_state()
    
    with patch("handlers.giveaway_handlers.parse_datetime", side_effect=ValueError):
        with patch.dict("handlers.giveaway_handlers.MESSAGES", {"invalid_datetime": "Invalid"}):
            process_end_time(message, state)
            
    message.answer.assert_called_once_with("Invalid")


def test_process_end_time_datetime_in_past():
    """
    Тест для проверки process_end_time с временем в прошлом.
    """
    message = create_message("2020-01-01 00:00")
    state = create_state()
    
    with patch("handlers.giveaway_handlers.parse_datetime", return_value="2020-01-01 00:00"):
        with patch("handlers.giveaway_handlers.is_future_datetime", return_value=False):
            with patch.dict("handlers.giveaway_handlers.MESSAGES", {"datetime_in_past": "In past"}):
                process_end_time(message, state)
                
    message.answer.assert_called_once_with("In past")


def test_confirm_create_giveaway_success():
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
    
    with patch("handlers.giveaway_handlers.create_giveaway", return_value=mock_giveaway):
        with patch("handlers.giveaway_handlers.get_participants_count", return_value=0):
            with patch("handlers.giveaway_handlers.get_participate_keyboard", return_value="keyboard"):
                with patch("handlers.giveaway_handlers.update_giveaway_message_id"):
                    with patch("handlers.giveaway_handlers.schedule_giveaway_finish"):
                        with patch.dict("handlers.giveaway_handlers.MESSAGES", {"giveaway_created": "Created"}):
                            with patch("handlers.giveaway_handlers.get_back_to_menu_keyboard", return_value="keyboard"):
                                confirm_create_giveaway(callback, state)
                                
    callback.message.edit_text.assert_called_once_with(
        "Created",
        reply_markup="keyboard"
    )
    state.clear.assert_called_once()
    callback.answer.assert_called_once()


def test_confirm_create_giveaway_failure():
    """
    Тест для проверки confirm_create_giveaway при неудачном создании.
    """
    callback = create_callback_query("confirm")
    state = create_state()
    
    with patch("handlers.giveaway_handlers.create_giveaway", return_value=None):
        with patch.dict("handlers.giveaway_handlers.MESSAGES", {"error_occurred": "Error"}):
            with patch("handlers.giveaway_handlers.get_back_to_menu_keyboard", return_value="keyboard"):
                confirm_create_giveaway(callback, state)
                
    callback.message.edit_text.assert_called_once_with(
        "Error",
        reply_markup="keyboard"
    )
    state.clear.assert_called_once()
    callback.answer.assert_called_once()


def test_callback_cancel_creation():
    """
    Тест для проверки callback_cancel_creation.
    """
    callback = create_callback_query("cancel_creation")
    state = create_state()
    
    with patch.dict("handlers.giveaway_handlers.MESSAGES", {"giveaway_creation_cancelled": "Cancelled"}):
        with patch("handlers.giveaway_handlers.get_back_to_menu_keyboard", return_value="keyboard"):
            callback_cancel_creation(callback, state)
            
    callback.message.edit_text.assert_called_once_with(
        "Cancelled",
        reply_markup="keyboard"
    )
    state.clear.assert_called_once()
    callback.answer.assert_called_once()


def test_callback_view_active_giveaways():
    """
    Тест для проверки callback_view_active_giveaways.
    """
    callback = create_callback_query("view_active")
    state = create_state()
    
    mock_giveaway = AsyncMock()
    
    with patch("handlers.giveaway_handlers.get_active_giveaways", return_value=[mock_giveaway]):
        with patch.dict("handlers.giveaway_handlers.MESSAGES", {"active_giveaways": "Active"}):
            with patch("handlers.giveaway_handlers.get_giveaways_list_keyboard", return_value="keyboard"):
                callback_view_active_giveaways(callback, state)
                
    callback.message.edit_text.assert_called_once_with(
        "Active",
        reply_markup="keyboard"
    )
    state.set_state.assert_called_once()
    state.update_data.assert_called_once()
    callback.answer.assert_called_once()


def test_callback_view_finished_giveaways_no_finished():
    """
    Тест для проверки callback_view_finished_giveaways без завершенных розыгрышей.
    """
    callback = create_callback_query("view_finished")
    
    with patch("handlers.giveaway_handlers.count_finished_giveaways", return_value=0):
        with patch.dict("handlers.giveaway_handlers.MESSAGES", {"no_giveaways": "No giveaways"}):
            callback_view_finished_giveaways(callback, None)
            
    callback.answer.assert_called_once_with("No giveaways", show_alert=True)


def test_callback_view_finished_giveaways_with_finished():
    """
    Тест для проверки callback_view_finished_giveaways с завершенными розыгрышами.
    """
    callback = create_callback_query("view_finished")
    state = create_state()
    
    mock_giveaway = AsyncMock()
    
    with patch("handlers.giveaway_handlers.count_finished_giveaways", return_value=5):
        with patch("handlers.giveaway_handlers.get_finished_giveaways_page", return_value=[mock_giveaway]):
            with patch("handlers.giveaway_handlers.get_finished_list_with_pagination_keyboard", return_value="keyboard"):
                with patch.dict("handlers.giveaway_handlers.MESSAGES", {"finished_giveaways": "Finished"}):
                    callback_view_finished_giveaways(callback, state)
                    
    callback.message.edit_text.assert_called_once_with("Finished")
    callback.message.edit_reply_markup.assert_called_once_with(reply_markup="keyboard")
    state.set_state.assert_called_once()
    state.update_data.assert_called()
    callback.answer.assert_called_once()


def test_callback_finished_page():
    """
    Тест для проверки callback_finished_page.
    """
    callback = create_callback_query("finished_page_2")
    state = create_state()
    
    mock_giveaway = AsyncMock()
    
    with patch("handlers.giveaway_handlers.count_finished_giveaways", return_value=20):
        with patch("handlers.giveaway_handlers.get_finished_giveaways_page", return_value=[mock_giveaway]):
            with patch("handlers.giveaway_handlers.get_finished_list_with_pagination_keyboard", return_value="keyboard"):
                callback_finished_page(callback, state)
                
    callback.message.edit_reply_markup.assert_called_once_with(reply_markup="keyboard")
    state.update_data.assert_called_once_with(finished_page=2)
    callback.answer.assert_called_once()


def test_callback_giveaway_details_success():
    """
    Тест для проверки callback_giveaway_details при успешном получении.
    """
    callback = create_callback_query("giveaway_details_1")
    state = create_state()
    
    mock_giveaway = AsyncMock()
    mock_giveaway.id = 1
    mock_giveaway.title = "Test"
    mock_giveaway.description = "Desc"
    mock_giveaway.status = "active"
    mock_giveaway.created_at = "2025-01-01 00:00"
    mock_giveaway.end_time = "2025-12-31 23:59"
    mock_giveaway.channel = AsyncMock()
    mock_giveaway.channel.channel_name = "Test Channel"
    
    with patch("handlers.giveaway_handlers.get_giveaway", return_value=mock_giveaway):
        with patch("handlers.giveaway_handlers.get_participants_count", return_value=10):
            with patch("handlers.giveaway_handlers.get_giveaway_details_keyboard", return_value="keyboard"):
                with patch.dict("handlers.giveaway_handlers.MESSAGES", {"giveaway_details": "Details: {title}"}):
                    callback_giveaway_details(callback, state)
                    
    callback.message.edit_text.assert_called_once()
    state.set_state.assert_called_once()
    state.update_data.assert_called_once()
    callback.answer.assert_called_once()


def test_callback_giveaway_details_not_found():
    """
    Тест для проверки callback_giveaway_details при отсутствии розыгрыша.
    """
    callback = create_callback_query("giveaway_details_999")
    
    with patch("handlers.giveaway_handlers.get_giveaway", return_value=None):
        with patch.dict("handlers.giveaway_handlers.MESSAGES", {"error_occurred": "Error"}):
            callback_giveaway_details(callback, None)
            
    callback.answer.assert_called_once_with("❌ Розыгрыш не найден", show_alert=True)


def test_callback_delete_giveaway_success():
    """
    Тест для проверки callback_delete_giveaway при успешном удалении.
    """
    callback = create_callback_query("delete_giveaway_1")
    state = create_state()
    
    mock_giveaway = AsyncMock()
    mock_giveaway.title = "Test"
    
    with patch("handlers.giveaway_handlers.get_giveaway", return_value=mock_giveaway):
        with patch("handlers.giveaway_handlers.get_delete_confirmation_keyboard", return_value="keyboard"):
            with patch.dict("handlers.giveaway_handlers.MESSAGES", {"confirm_delete": "Confirm {title}"}):
                callback_delete_giveaway(callback, state)
                
    callback.message.edit_text.assert_called_once()
    state.update_data.assert_called_once()
    callback.answer.assert_called_once()


def test_callback_delete_giveaway_not_found():
    """
    Тест для проверки callback_delete_giveaway при отсутствии розыгрыша.
    """
    callback = create_callback_query("delete_giveaway_999")
    
    with patch("handlers.giveaway_handlers.get_giveaway", return_value=None):
        with patch.dict("handlers.giveaway_handlers.MESSAGES", {"error_occurred": "Error"}):
            callback_delete_giveaway(callback, None)
            
    callback.answer.assert_called_once_with("❌ Розыгрыш не найден", show_alert=True)


def test_callback_confirm_delete_giveaway_success():
    """
    Тест для проверки callback_confirm_delete_giveaway при успешном удалении.
    """
    callback = create_callback_query("confirm_delete_1")
    state = create_state()
    
    mock_giveaway = AsyncMock()
    mock_giveaway.status = "active"
    mock_giveaway.message_id = 999
    mock_giveaway.channel_id = 123
    
    with patch("handlers.giveaway_handlers.get_giveaway", return_value=mock_giveaway):
        with patch("handlers.giveaway_handlers.cancel_giveaway_schedule"):
            with patch("handlers.giveaway_handlers.delete_giveaway", return_value=True):
                with patch.dict("handlers.giveaway_handlers.MESSAGES", {"giveaway_deleted": "Deleted"}):
                    with patch("handlers.giveaway_handlers.get_back_to_menu_keyboard", return_value="keyboard"):
                        callback_confirm_delete_giveaway(callback, state)
                        
    callback.bot.delete_message.assert_called_once_with(chat_id=123, message_id=999)
    callback.message.edit_text.assert_called_once_with(
        "Deleted",
        reply_markup="keyboard"
    )
    state.clear.assert_called_once()
    callback.answer.assert_called_once()


def test_callback_confirm_delete_giveaway_failure():
    """
    Тест для проверки callback_confirm_delete_giveaway при неудачном удалении.
    """
    callback = create_callback_query("confirm_delete_1")
    state = create_state()
    
    mock_giveaway = AsyncMock()
    mock_giveaway.status = "active"
    mock_giveaway.message_id = 999
    mock_giveaway.channel_id = 123
    
    with patch("handlers.giveaway_handlers.get_giveaway", return_value=mock_giveaway):
        with patch("handlers.giveaway_handlers.cancel_giveaway_schedule"):
            with patch("handlers.giveaway_handlers.delete_giveaway", return_value=False):
                with patch.dict("handlers.giveaway_handlers.MESSAGES", {"error_occurred": "Error"}):
                    with patch("handlers.giveaway_handlers.get_back_to_menu_keyboard", return_value="keyboard"):
                        callback_confirm_delete_giveaway(callback, state)
                        
    callback.bot.delete_message.assert_called_once_with(chat_id=123, message_id=999)
    callback.message.edit_text.assert_called_once_with(
        "Error",
        reply_markup="keyboard"
    )
    state.clear.assert_called_once()
    callback.answer.assert_called_once()


def test_callback_cancel_delete_with_giveaway():
    """
    Тест для проверки callback_cancel_delete при наличии розыгрыша.
    """
    callback = create_callback_query("cancel_delete")
    state = create_state()
    state.get_data.return_value = {"current_giveaway_id": 1}
    
    mock_giveaway = AsyncMock()
    
    with patch("handlers.giveaway_handlers.get_giveaway", return_value=mock_giveaway):
        with patch("handlers.giveaway_handlers.get_giveaway_details_keyboard", return_value="keyboard"):
            callback_cancel_delete(callback, state)
            
    callback.message.edit_text.assert_called_once_with(
        "Удаление отменено",
        reply_markup="keyboard"
    )
    callback.answer.assert_called_once()


def test_callback_cancel_delete_no_giveaway():
    """
    Тест для проверки callback_cancel_delete без розыгрыша.
    """
    callback = create_callback_query("cancel_delete")
    state = create_state()
    state.get_data.return_value = {}
    
    with patch.dict("handlers.giveaway_handlers.MESSAGES", {"deletion_cancelled": "Cancelled"}):
        with patch("handlers.giveaway_handlers.get_back_to_menu_keyboard", return_value="keyboard"):
            callback_cancel_delete(callback, state)
            
    callback.message.edit_text.assert_called_once_with(
        "Cancelled",
        reply_markup="keyboard"
    )
    callback.answer.assert_called_once()


def test_callback_edit_giveaway_success():
    """
    Тест для проверки callback_edit_giveaway при успешном редактировании.
    """
    callback = create_callback_query("edit_giveaway_1")
    state = create_state()
    
    mock_giveaway = AsyncMock()
    mock_giveaway.status = "active"
    
    with patch("handlers.giveaway_handlers.get_giveaway", return_value=mock_giveaway):
        with patch.dict("handlers.giveaway_handlers.MESSAGES", {"choose_field_to_edit": "Choose"}):
            with patch("handlers.giveaway_handlers.get_edit_fields_keyboard", return_value="keyboard"):
                callback_edit_giveaway(callback, state)
                
    state.set_state.assert_called_once()
    state.update_data.assert_called_once()
    callback.message.edit_text.assert_called_once_with(
        "Choose",
        reply_markup="keyboard"
    )
    callback.answer.assert_called_once()


def test_callback_edit_giveaway_not_found():
    """
    Тест для проверки callback_edit_giveaway при отсутствии розыгрыша.
    """
    callback = create_callback_query("edit_giveaway_999")
    
    with patch("handlers.giveaway_handlers.get_giveaway", return_value=None):
        with patch.dict("handlers.giveaway_handlers.MESSAGES", {"error_occurred": "Error"}):
            callback_edit_giveaway(callback, None)
            
    callback.answer.assert_called_once_with("❌ Редактирование недоступно", show_alert=True)


def test_callback_edit_giveaway_not_active():
    """
    Тест для проверки callback_edit_giveaway для неактивного розыгрыша.
    """
    callback = create_callback_query("edit_giveaway_1")
    
    mock_giveaway = AsyncMock()
    mock_giveaway.status = "finished"
    
    with patch("handlers.giveaway_handlers.get_giveaway", return_value=mock_giveaway):
        with patch.dict("handlers.giveaway_handlers.MESSAGES", {"error_occurred": "Error"}):
            callback_edit_giveaway(callback, None)
            
    callback.answer.assert_called_once_with("❌ Редактирование недоступно", show_alert=True)


def test_process_new_title_success():
    """
    Тест для проверки process_new_title с валидным заголовком.
    """
    message = create_message("New Title")
    state = create_state()
    state.get_data.return_value = {"edit_giveaway_id": 1}
    
    mock_giveaway = AsyncMock()
    
    with patch("handlers.giveaway_handlers.update_giveaway_fields"):
        with patch("handlers.giveaway_handlers.get_giveaway", return_value=mock_giveaway):
            with patch("handlers.giveaway_handlers.update_channel_giveaway_post"):
                with patch.dict("handlers.giveaway_handlers.MESSAGES", {"giveaway_updated": "Updated"}):
                    with patch("handlers.giveaway_handlers.get_back_to_menu_keyboard", return_value="keyboard"):
                        process_new_title(message, state)
                        
    message.answer.assert_called_once_with("Updated", reply_markup="keyboard")
    state.set_state.assert_called_once()


def test_process_new_title_too_long():
    """
    Тест для проверки process_new_title с слишком длинным заголовком.
    """
    message = create_message("a" * 256)
    state = create_state()
    
    with patch.dict("handlers.giveaway_handlers.MESSAGES", {"title_too_long": "Too long"}):
        process_new_title(message, state)
        
    message.answer.assert_called_once_with("Too long")


def test_process_new_description_success():
    """
    Тест для проверки process_new_description с валидным описанием.
    """
    message = create_message("New Description")
    state = create_state()
    state.get_data.return_value = {"edit_giveaway_id": 1}
    
    mock_giveaway = AsyncMock()
    
    with patch("handlers.giveaway_handlers.update_giveaway_fields"):
        with patch("handlers.giveaway_handlers.get_giveaway", return_value=mock_giveaway):
            with patch("handlers.giveaway_handlers.update_channel_giveaway_post"):
                with patch.dict("handlers.giveaway_handlers.MESSAGES", {"giveaway_updated": "Updated"}):
                    with patch("handlers.giveaway_handlers.get_back_to_menu_keyboard", return_value="keyboard"):
                        process_new_description(message, state)
                        
    message.answer.assert_called_once_with("Updated", reply_markup="keyboard")
    state.set_state.assert_called_once()


def test_process_new_description_too_long():
    """
    Тест для проверки process_new_description с слишком длинным описанием.
    """
    message = create_message("a" * 4001)
    state = create_state()
    
    with patch.dict("handlers.giveaway_handlers.MESSAGES", {"description_too_long": "Too long"}):
        process_new_description(message, state)
        
    message.answer.assert_called_once_with("Too long")


def test_process_new_media_success():
    """
    Тест для проверки process_new_media с валидным медиа.
    """
    message = create_message(has_photo=True)
    state = create_state()
    state.get_data.return_value = {"edit_giveaway_id": 1}
    
    mock_giveaway = AsyncMock()
    
    with patch("handlers.giveaway_handlers.update_giveaway_fields", return_value=mock_giveaway):
        with patch("handlers.giveaway_handlers.get_giveaway", return_value=mock_giveaway):
            with patch("handlers.giveaway_handlers.update_channel_giveaway_post"):
                with patch.dict("handlers.giveaway_handlers.MESSAGES", {"giveaway_updated": "Updated"}):
                    with patch("handlers.giveaway_handlers.get_back_to_menu_keyboard", return_value="keyboard"):
                        process_new_media(message, state)
                        
    message.answer.assert_called_once_with("Updated", reply_markup="keyboard")
    state.set_state.assert_called_once()


def test_process_new_media_invalid():
    """
    Тест для проверки process_new_media с неподдерживаемым медиа.
    """
    message = create_message()
    state = create_state()
    
    with patch.dict("handlers.giveaway_handlers.MESSAGES", {"invalid_media": "Invalid"}):
        process_new_media(message, state)
        
    message.answer.assert_called_once_with("❌ Поддерживаются только фото, видео, GIF и документы")


def test_process_new_end_time_success():
    """
    Тест для проверки process_new_end_time с валидным временем.
    """
    message = create_message("2025-12-31 23:59")
    state = create_state()
    state.get_data