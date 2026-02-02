import pytest
from unittest.mock import AsyncMock, patch
from aiogram.types import CallbackQuery, Message, Update
from aiogram.fsm.context import FSMContext

from handlers.admin_handlers import router, get_all_admins, add_admin, remove_admin, get_all_channels, add_channel, \
    remove_channel, add_channel_by_username, get_active_giveaways, get_finished_giveaways, callback_admin_management, \
    callback_view_admins, callback_add_admin, process_new_admin_id, confirm_add_admin, callback_remove_admin, \
    confirm_remove_admin, callback_channel_management, callback_view_channels, callback_add_channel, \
    process_channel_link, process_channel_info, confirm_add_channel, confirm_remove_channel, callback_view_giveaways, \
    callback_cancel, catch_channel_link_message


def create_callback_query(data: str):
    callback = AsyncMock(spec=CallbackQuery)
    callback.data = data
    callback.message = AsyncMock()
    callback.message.edit_text = AsyncMock()
    callback.answer = AsyncMock()
    callback.from_user = AsyncMock()
    callback.from_user.id = 123
    return callback

def create_message(text: str):
    message = AsyncMock(spec=Message)
    message.text = text
    message.answer = AsyncMock()
    message.bot = AsyncMock()
    message.from_user = AsyncMock()
    message.from_user.id = 123
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

@pytest.mark.asyncio
async def test_admin_management_callback():
    """
    Тест для проверки callback_admin_management.
    """
    callback = create_callback_query("admin_management")
    state = create_state()
    
    # Замокаем MESSAGES
    with patch.dict("handlers.admin_handlers.MESSAGES", {"admin_management_menu": "Menu"}):
        with patch("handlers.admin_handlers.get_admin_management_keyboard", return_value="keyboard"):
            await callback_admin_management(callback, state)
            
    callback.message.edit_text.assert_called_once_with(
        "Menu",
        reply_markup="keyboard"
    )
    state.set_state.assert_called_once()
    callback.answer.assert_called_once()

@pytest.mark.asyncio
async def test_view_admins_callback():
    """
    Тест для проверки callback_view_admins.
    """
    callback = create_callback_query("view_admins")
    
    # Замокаем get_all_admins
    mock_admin = AsyncMock()
    mock_admin.first_name = "Test"
    mock_admin.username = "test"
    mock_admin.user_id = 123
    mock_admin.is_main_admin = False
    
    with patch("handlers.admin_handlers.get_all_admins", return_value=[mock_admin]):
        with patch.dict("handlers.admin_handlers.MESSAGES", {"current_admins": "Admins: {admins}"}):
            with patch("handlers.admin_handlers.get_admins_list_keyboard", return_value="keyboard"):
              await callback_view_admins(callback)
                
    callback.message.edit_text.assert_called_once()
    callback.answer.assert_called_once()


@pytest.mark.asyncio
async def test_add_admin_callback():
    """
    Тест для проверки callback_add_admin.
    """
    callback = create_callback_query("add_admin")
    state = create_state()
    
    with patch.dict("handlers.admin_handlers.MESSAGES", {"enter_new_admin_id": "Enter ID"}):
        with patch("handlers.admin_handlers.get_back_to_menu_keyboard", return_value="keyboard"):
            await callback_add_admin(callback, state)
            
    callback.message.edit_text.assert_called_once_with(
        "Enter ID",
        reply_markup="keyboard"
    )
    state.set_state.assert_called_once()
    callback.answer.assert_called_once()


@pytest.mark.asyncio
async def test_process_new_admin_id_success():
    """
    Тест для проверки process_new_admin_id с валидным ID.
    """
    message = create_message("12345")
    state = create_state()
    
    await process_new_admin_id(message, state)
    
    state.update_data.assert_called_once_with(
        new_admin_id=12345,
        new_admin_name="ID: 12345",
        new_admin_username=None
    )
    state.set_state.assert_called_once()
    message.answer.assert_called_once()


@pytest.mark.asyncio
async def test_process_new_admin_id_invalid():
    """
    Тест для проверки process_new_admin_id с невалидным ID.
    """
    message = create_message("abc")
    state = create_state()
    
    with patch.dict("handlers.admin_handlers.MESSAGES", {"invalid_user_id": "Invalid ID"}):
        await process_new_admin_id(message, state)
        
    message.answer.assert_called_once_with("Invalid ID")


@pytest.mark.asyncio
async def test_confirm_add_admin_success():
    """
    Тест для проверки confirm_add_admin при успешном добавлении.
    """
    callback = create_callback_query("confirm")
    state = create_state()
    state.get_data.return_value = {
        "new_admin_id": 12345,
        "new_admin_name": "Test",
        "new_admin_username": "test"
    }
    
    with patch("handlers.admin_handlers.add_admin", return_value=True):
        with patch.dict("handlers.admin_handlers.MESSAGES", {"admin_added": "Added"}):
            with patch("handlers.admin_handlers.get_back_to_menu_keyboard", return_value="keyboard"):
                await confirm_add_admin(callback, state)
                
    callback.message.edit_text.assert_called_once_with(
        "Added",
        reply_markup="keyboard"
    )
    callback.answer.assert_called_once()


@pytest.mark.asyncio
async def test_confirm_add_admin_failure():
    """
    Тест для проверки confirm_add_admin при неудачном добавлении.
    """
    callback = create_callback_query("confirm")
    state = create_state()
    state.get_data.return_value = {
        "new_admin_id": 12345,
        "new_admin_name": "Test",
        "new_admin_username": "test"
    }
    
    with patch("handlers.admin_handlers.add_admin", return_value=False):
        with patch.dict("handlers.admin_handlers.MESSAGES", {"admin_already_exists": "Exists"}):
            with patch("handlers.admin_handlers.get_back_to_menu_keyboard", return_value="keyboard"):
                await confirm_add_admin(callback, state)
                
    callback.message.edit_text.assert_called_once_with(
        "Exists",
        reply_markup="keyboard"
    )
    callback.answer.assert_called_once()


@pytest.mark.asyncio
async def test_remove_admin_callback():
    """
    Тест для проверки callback_remove_admin.
    """
    callback = create_callback_query("remove_admin")
    state = create_state()
    
    mock_admin = AsyncMock()
    mock_admin.is_main_admin = False
    
    with patch("handlers.admin_handlers.get_all_admins", return_value=[mock_admin]):
        with patch.dict("handlers.admin_handlers.MESSAGES", {"choose_admin_to_remove": "Choose"}):
            with patch("handlers.admin_handlers.get_admins_list_keyboard", return_value="keyboard"):
                await callback_remove_admin(callback, state)
                
    callback.message.edit_text.assert_called_once_with(
        "Choose",
        reply_markup="keyboard"
    )
    state.set_state.assert_called_once()
    callback.answer.assert_called_once()


@pytest.mark.asyncio
async def test_confirm_remove_admin_success():
    """
    Тест для проверки confirm_remove_admin при успешном удалении.
    """
    callback = create_callback_query("confirm")
    state = create_state()
    state.get_data.return_value = {"remove_admin_id": 12345}
    
    with patch("handlers.admin_handlers.remove_admin", return_value=True):
        with patch.dict("handlers.admin_handlers.MESSAGES", {"admin_removed": "Removed"}):
            with patch("handlers.admin_handlers.get_back_to_menu_keyboard", return_value="keyboard"):
                await confirm_remove_admin(callback, state)
                
    callback.message.edit_text.assert_called_once_with(
        "Removed",
        reply_markup="keyboard"
    )
    callback.answer.assert_called_once()


@pytest.mark.asyncio
async def test_confirm_remove_admin_failure():
    """
    Тест для проверки confirm_remove_admin при неудачном удалении.
    """
    callback = create_callback_query("confirm")
    state = create_state()
    state.get_data.return_value = {"remove_admin_id": 12345}
    
    with patch("handlers.admin_handlers.remove_admin", return_value=False):
        with patch.dict("handlers.admin_handlers.MESSAGES", {"error_occurred": "Error"}):
            with patch("handlers.admin_handlers.get_back_to_menu_keyboard", return_value="keyboard"):
                await confirm_remove_admin(callback, state)
                
    callback.message.edit_text.assert_called_once_with(
        "Error",
        reply_markup="keyboard"
    )
    callback.answer.assert_called_once()


@pytest.mark.asyncio
async def test_channel_management_callback():
    """
    Тест для проверки callback_channel_management.
    """
    callback = create_callback_query("channel_management")
    state = create_state()
    
    with patch.dict("handlers.admin_handlers.MESSAGES", {"channel_management_menu": "Menu"}):
        with patch("handlers.admin_handlers.get_channel_management_keyboard", return_value="keyboard"):
            await callback_channel_management(callback, state)
            
    callback.message.edit_text.assert_called_once_with(
        "Menu",
        reply_markup="keyboard"
    )
    state.set_state.assert_called_once()
    callback.answer.assert_called_once()


@pytest.mark.asyncio
async def test_view_channels_callback():
    """
    Тест для проверки callback_view_channels.
    """
    callback = create_callback_query("view_channels")
    
    mock_channel = AsyncMock()
    mock_channel.channel_name = "Test Channel"
    mock_channel.channel_username = "test_channel"
    mock_channel.admin = AsyncMock()
    mock_channel.admin.first_name = "Admin"
    mock_channel.admin.username = "admin"
    mock_channel.added_by = 123
    
    with patch("handlers.admin_handlers.get_all_channels", return_value=[mock_channel]):
        with patch.dict("handlers.admin_handlers.MESSAGES", {"current_channels": "Channels: {channels}"}):
            with patch("handlers.admin_handlers.get_channels_list_keyboard", return_value="keyboard"):
                await callback_view_channels(callback)
                
    callback.message.edit_text.assert_called_once()
    callback.answer.assert_called_once()


@pytest.mark.asyncio
async def test_add_channel_callback():
    """
    Тест для проверки callback_add_channel.
    """
    callback = create_callback_query("add_channel")
    state = create_state()
    
    with patch.dict("handlers.admin_handlers.MESSAGES", {"enter_channel_info": "Info"}):
        with patch("handlers.admin_handlers.get_add_channel_method_keyboard", return_value="keyboard"):
            await callback_add_channel(callback, state)
            
    callback.message.edit_text.assert_called_once_with(
        "Info",
        reply_markup="keyboard"
    )
    callback.answer.assert_called_once()


@pytest.mark.asyncio
async def test_process_channel_link_success():
    """
    Тест для проверки process_channel_link при успешном добавлении.
    """
    message = create_message("@test_channel")
    state = create_state()
    state.get_state.return_value = "ChannelManagementStates:WAITING_CHANNEL_LINK"
    
    with patch("handlers.admin_handlers.add_channel_by_username", return_value=(True, "Success")):
        with patch("handlers.admin_handlers.get_back_to_menu_keyboard", return_value="keyboard"):
            await process_channel_link(message, state)
            
    message.answer.assert_called_once_with("Success", reply_markup="keyboard")
    state.set_state.assert_called_with("ChannelManagementStates:MAIN_CHANNEL_MENU")


@pytest.mark.asyncio
async def test_process_channel_link_failure():
    """
    Тест для проверки process_channel_link при неудачном добавлении.
    """
    message = create_message("@test_channel")
    state = create_state()
    state.get_state.return_value = "ChannelManagementStates:WAITING_CHANNEL_LINK"
    
    with patch("handlers.admin_handlers.add_channel_by_username", return_value=(False, "Error")):
        with patch("handlers.admin_handlers.get_back_to_menu_keyboard", return_value="keyboard"):
            await process_channel_link(message, state)
            
    message.answer.assert_called_once_with("Error", reply_markup="keyboard")




@pytest.mark.asyncio
async def test_process_channel_info_success():
    """
    Тест для проверки process_channel_info при успешной пересылке.
    """
    message = create_message("")
    message.forward_from_chat = AsyncMock()
    message.forward_from_chat.type = "channel"
    message.forward_from_chat.id = 123
    message.forward_from_chat.title = "Test Channel"
    message.forward_from_chat.username = "test_channel"
    message.bot = AsyncMock()
    
    mock_member = AsyncMock()
    mock_member.status = "administrator"
    message.bot.get_chat_member = AsyncMock(return_value=mock_member)
    
    state = create_state()
    
    with patch.dict("handlers.admin_handlers.MESSAGES", {"confirm_add_channel": "Confirm {channel}"}):
        with patch("handlers.admin_handlers.get_confirm_keyboard", return_value="keyboard"):
            await process_channel_info(message, state)
            
    state.update_data.assert_called_once()
    state.set_state.assert_called_once()
    message.answer.assert_called_once()


@pytest.mark.asyncio
async def test_process_channel_info_no_forward():
    """
    Тест для проверки process_channel_info без пересылки.
    """
    message = create_message("")
    message.forward_from_chat = None
    message.answer = AsyncMock()
    
    await process_channel_info(message, None)
    
    message.answer.assert_called_once_with("❌ Пожалуйста, перешлите сообщение из канала")


@pytest.mark.asyncio
async def test_process_channel_info_not_channel():
    """
    Тест для проверки process_channel_info с неправильным типом чата.
    """
    message = create_message("")
    message.forward_from_chat = AsyncMock()
    message.forward_from_chat.type = "group"
    message.answer = AsyncMock()
    
    await process_channel_info(message, None)
    
    message.answer.assert_called_once_with("❌ Это не канал!")


@pytest.mark.asyncio
async def test_confirm_add_channel_success():
    """
    Тест для проверки confirm_add_channel при успешном добавлении.
    """
    callback = create_callback_query("confirm")
    state = create_state()
    state.get_data.return_value = {
        "channel_id": 123,
        "channel_name": "Test Channel",
        "channel_username": "test_channel"
    }
    
    with patch("handlers.admin_handlers.add_channel", return_value=True):
        with patch.dict("handlers.admin_handlers.MESSAGES", {"channel_added": "Added"}):
            with patch("handlers.admin_handlers.get_back_to_menu_keyboard", return_value="keyboard"):
                await confirm_add_channel(callback, state)
                
    callback.message.edit_text.assert_called_once_with(
        "Added",
        reply_markup="keyboard"
    )
    callback.answer.assert_called_once()


@pytest.mark.asyncio
async def test_confirm_add_channel_failure():
    """
    Тест для проверки confirm_add_channel при неудачном добавлении.
    """
    callback = create_callback_query("confirm")
    state = create_state()
    state.get_data.return_value = {
        "channel_id": 123,
        "channel_name": "Test Channel",
        "channel_username": "test_channel"
    }
    
    with patch("handlers.admin_handlers.add_channel", return_value=False):
        with patch.dict("handlers.admin_handlers.MESSAGES", {"channel_already_exists": "Exists"}):
            with patch("handlers.admin_handlers.get_back_to_menu_keyboard", return_value="keyboard"):
                await confirm_add_channel(callback, state)
                
    callback.message.edit_text.assert_called_once_with(
        "Exists",
        reply_markup="keyboard"
    )
    callback.answer.assert_called_once()


@pytest.mark.asyncio
async def test_confirm_remove_channel_success():
    """
    Тест для проверки confirm_remove_channel при успешном удалении.
    """
    callback = create_callback_query("confirm")
    state = create_state()
    state.get_data.return_value = {"remove_channel_id": 123}
    
    with patch("handlers.admin_handlers.remove_channel", return_value=True):
        with patch.dict("handlers.admin_handlers.MESSAGES", {"channel_removed": "Removed"}):
            with patch("handlers.admin_handlers.get_back_to_menu_keyboard", return_value="keyboard"):
                await confirm_remove_channel(callback, state)
                
    callback.message.edit_text.assert_called_once_with(
        "Removed",
        reply_markup="keyboard"
    )
    callback.answer.assert_called_once()


@pytest.mark.asyncio
async def test_confirm_remove_channel_failure():
    """
    Тест для проверки confirm_remove_channel при неудачном удалении.
    """
    callback = create_callback_query("confirm")
    state = create_state()
    state.get_data.return_value = {"remove_channel_id": 123}
    
    with patch("handlers.admin_handlers.remove_channel", return_value=False):
        with patch.dict("handlers.admin_handlers.MESSAGES", {"error_occurred": "Error"}):
            with patch("handlers.admin_handlers.get_back_to_menu_keyboard", return_value="keyboard"):
                await confirm_remove_channel(callback, state)
                
    callback.message.edit_text.assert_called_once_with(
        "Error",
        reply_markup="keyboard"
    )
    callback.answer.assert_called_once()


@pytest.mark.asyncio
async def test_view_giveaways_callback():
    """
    Тест для проверки callback_view_giveaways.
    """
    callback = create_callback_query("view_giveaways")
    state = create_state()
    
    with patch.dict("handlers.admin_handlers.MESSAGES", {"choose_giveaway_type": "Choose"}):
        with patch("handlers.admin_handlers.get_giveaway_types_keyboard", return_value="keyboard"):
            await callback_view_giveaways(callback, state)
            
    callback.message.edit_text.assert_called_once_with(
        "Choose",
        reply_markup="keyboard"
    )
    state.set_state.assert_called_once()
    callback.answer.assert_called_once()


@pytest.mark.asyncio
async def test_cancel_callback():
    """
    Тест для проверки callback_cancel.
    """
    callback = create_callback_query("cancel")
    state = create_state()
    
    with patch.dict("handlers.admin_handlers.MESSAGES", {"admin_main_menu": "Main Menu"}):
        with patch("handlers.admin_handlers.get_admin_management_keyboard", return_value="keyboard"):
            await callback_cancel(callback, state)
            
    callback.message.edit_text.assert_called_once_with(
        "Main Menu",
        reply_markup="keyboard"
    )
    state.clear.assert_called_once()
    callback.answer.assert_called_once_with("❌ Операция отменена")


@pytest.mark.asyncio
async def test_catch_channel_link_message_valid():
    """
    Тест для проверки catch_channel_link_message с валидной ссылкой.
    """
    message = create_message("@test_channel")
    state = create_state()
    
    with patch("handlers.admin_handlers.add_channel_by_username", return_value=(True, "Success")):
        with patch("handlers.admin_handlers.get_back_to_menu_keyboard", return_value="keyboard"):
            await catch_channel_link_message(message, state)
            
    state.set_state.assert_called_with("ChannelManagementStates:WAITING_CHANNEL_LINK")
    state.set_state.assert_called_with("ChannelManagementStates:MAIN_CHANNEL_MENU")
    state.set_state.assert_called_once()
    message.answer.assert_called_once_with("Success", reply_markup="keyboard")


def test_catch_channel_link_message_invalid():
    """
    Тест для проверки catch_channel_link_message с невалидной ссылкой.
    """
    message = create_message("invalid")
    state = create_state()
    
    catch_channel_link_message(message, state)
    
    # Не должно быть вызовов
    state.set_state.assert_not_called()
    message.answer.assert_not_called()
