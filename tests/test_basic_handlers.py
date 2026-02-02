import pytest
from unittest.mock import AsyncMock, patch
from aiogram.types import CallbackQuery, Message, Update
from aiogram.fsm.context import FSMContext

from handlers.basic_handlers import router, get_participants_count, get_giveaway, update_giveaway_message_id, is_admin, \
    cmd_start, cmd_clear, cmd_admin, callback_main_menu, callback_participate, handle_unknown_message


def create_message(text: str = None, command: str = None):
    message = AsyncMock(spec=Message)
    message.text = text
    if command:
        message.text = f"/{command}"
    message.answer = AsyncMock()
    message.bot = AsyncMock()
    message.message_id = 123
    message.chat = AsyncMock()
    message.chat.id = 456
    message.from_user = AsyncMock()
    message.from_user.id = 123
    return message

def create_callback_query(data: str):
    callback = AsyncMock(spec=CallbackQuery)
    callback.data = data
    callback.message = AsyncMock()
    callback.message.edit_text = AsyncMock()
    callback.answer = AsyncMock()
    callback.from_user = AsyncMock()
    return callback

def create_state():
    state = AsyncMock(spec=FSMContext)
    state.get_state.return_value = None
    state.set_state = AsyncMock()
    state.clear = AsyncMock()
    return state


def test_router():
    """
    Тест для проверки существования роутера.
    """
    assert router is not None

@pytest.mark.asyncio
async def test_cmd_start_admin():
    """
    Тест для проверки cmd_start для администратора.
    """
    message = create_message(command="start")
    state = create_state()
    
    with patch("handlers.basic_handlers.is_admin", return_value=True):
        await cmd_start(message, state)
        
    message.answer.assert_called_once()
    assert "администратор" in message.answer.call_args[0][0]


@pytest.mark.asyncio
async def test_cmd_start_user():
    """
    Тест для проверки cmd_start для обычного пользователя.
    """
    message = create_message(command="start")
    state = create_state()
    
    with patch("handlers.basic_handlers.is_admin", return_value=False):
        await cmd_start(message, state)
        
    message.answer.assert_called_once()
    assert "Добро пожаловать!" in message.answer.call_args[0][0]


@pytest.mark.asyncio
async def test_cmd_clear():
    """
    Тест для проверки cmd_clear.
    """
    message = create_message()
    message.bot.delete_message = AsyncMock()
    
    await cmd_clear(message)
    
    # Проверяем, что попытка удалить 101 сообщение (от message_id - 100 до message_id)
    assert message.bot.delete_message.call_count == 101


@pytest.mark.asyncio
async def test_cmd_admin():
    """
    Тест для проверки cmd_admin.
    """
    message = create_message(command="admin")
    state = create_state()
    
    with patch.dict("handlers.basic_handlers.MESSAGES", {"admin_main_menu": "Menu"}):
        with patch("handlers.basic_handlers.get_main_admin_keyboard", return_value="keyboard"):
            await cmd_admin(message, state)
            
    state.clear.assert_called_once()
    message.answer.assert_called_once_with(
        "Menu",
        reply_markup="keyboard"
    )


@pytest.mark.asyncio
async def test_callback_main_menu():
    """
    Тест для проверки callback_main_menu.
    """
    callback = create_callback_query("main_menu")
    state = create_state()
    
    with patch.dict("handlers.basic_handlers.MESSAGES", {"admin_main_menu": "Menu"}):
        with patch("handlers.basic_handlers.get_main_admin_keyboard", return_value="keyboard"):
            await callback_main_menu(callback, state)
            
    state.clear.assert_called_once()
    callback.message.edit_text.assert_called_once_with(
        "Menu",
        reply_markup="keyboard"
    )
    callback.answer.assert_called_once()


@pytest.mark.asyncio
async def test_callback_participate_success():
    """
    Тест для проверки callback_participate при успешном участии.
    """
    callback = create_callback_query("participate_1")
    callback.from_user.id = 123
    callback.from_user.username = "test"
    callback.from_user.first_name = "Test"
    callback.message.edit_reply_markup = AsyncMock()
    
    mock_giveaway = AsyncMock()
    mock_giveaway.status = "active"
    mock_giveaway.channel_id = 100
    
    with patch("handlers.basic_handlers.get_giveaway", return_value=mock_giveaway):
        with patch("handlers.basic_handlers.check_user_subscription", return_value=True):
            with patch("handlers.basic_handlers.add_participant", return_value=True):
                with patch("handlers.basic_handlers.get_participants_count", return_value=5):
                    with patch("handlers.basic_handlers.get_participate_keyboard", return_value="keyboard"):
                        with patch.dict("handlers.basic_handlers.MESSAGES", {"participation_success": "Success"}):
                            await callback_participate(callback)
                            
    callback.answer.assert_called_once_with("Success", show_alert=True)
    callback.message.edit_reply_markup.assert_called_once_with(reply_markup="keyboard")


@pytest.mark.asyncio
async def test_callback_participate_already_participating():
    """
    Тест для проверки callback_participate при повторном участии.
    """
    callback = create_callback_query("participate_1")
    callback.from_user.id = 123
    
    mock_giveaway = AsyncMock()
    mock_giveaway.status = "active"
    mock_giveaway.channel_id = 100
    
    with patch("handlers.basic_handlers.get_giveaway", return_value=mock_giveaway):
        with patch("handlers.basic_handlers.check_user_subscription", return_value=True):
            with patch("handlers.basic_handlers.add_participant", return_value=False):
                with patch.dict("handlers.basic_handlers.MESSAGES", {"already_participating": "Already"}):
                    await callback_participate(callback)
                    
    callback.answer.assert_called_once_with("Already", show_alert=True)


@pytest.mark.asyncio
async def test_callback_participate_not_subscribed():
    """
    Тест для проверки callback_participate при отсутствии подписки.
    """
    callback = create_callback_query("participate_1")
    callback.from_user.id = 123
    
    mock_giveaway = AsyncMock()
    mock_giveaway.status = "active"
    mock_giveaway.channel_id = 100
    
    with patch("handlers.basic_handlers.get_giveaway", return_value=mock_giveaway):
        with patch("handlers.basic_handlers.check_user_subscription", return_value=False):
            with patch.dict("handlers.basic_handlers.MESSAGES", {"not_subscribed": "Not subscribed"}):
               await callback_participate(callback)
                
    callback.answer.assert_called_once_with("Not subscribed", show_alert=True)


@pytest.mark.asyncio
async def test_callback_participate_giveaway_ended():
    """
    Тест для проверки callback_participate при завершенном розыгрыше.
    """
    callback = create_callback_query("participate_1")
    
    mock_giveaway = AsyncMock()
    mock_giveaway.status = "finished"
    
    with patch("handlers.basic_handlers.get_giveaway", return_value=mock_giveaway):
        with patch.dict("handlers.basic_handlers.MESSAGES", {"giveaway_ended": "Ended"}):
            await callback_participate(callback)
            
    callback.answer.assert_called_once_with("Ended", show_alert=True)


@pytest.mark.asyncio
async def test_handle_unknown_message_admin():
    """
    Тест для проверки handle_unknown_message для администратора.
    """
    message = create_message("test")
    state = create_state()
    state.get_state.return_value = None
    
    with patch("handlers.basic_handlers.is_admin", return_value=True):
        with patch.dict("handlers.basic_handlers.MESSAGES", {"unknown_command": "Unknown"}):
            await handle_unknown_message(message, state)
            
    message.answer.assert_called_once_with("Unknown")


@pytest.mark.asyncio
async def test_handle_unknown_message_user():
    """
    Тест для проверки handle_unknown_message для пользователя.
    """
    message = create_message("test")
    state = create_state()
    state.get_state.return_value = None
    
    with patch("handlers.basic_handlers.is_admin", return_value=False):
        await handle_unknown_message(message, state)
        
    message.answer.assert_not_called()


@pytest.mark.asyncio
async def test_handle_unknown_message_in_state():
    """
    Тест для проверки handle_unknown_message при наличии состояния.
    """
    message = create_message("test")
    state = create_state()
    state.get_state.return_value = "some_state"
    
    await handle_unknown_message(message, state)
    
    message.answer.assert_not_called()