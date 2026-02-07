from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch, MagicMock

import pytest
from apscheduler.triggers.date import DateTrigger

from utils.scheduler import (
    setup_scheduler, schedule_giveaway_finish, schedule_reminders,
    send_reminder, disable_all_reminders, check_user_subscription,
    cancel_giveaway_schedule, finish_giveaway_task, cleanup_old_finished,
    get_scheduler_status, scheduler, REMINDER_SETTINGS
)


def create_mock_giveaway(**kwargs):
    """Создание мок-объекта розыгрыша"""
    giveaway = MagicMock()
    giveaway.id = kwargs.get('id', 1)
    giveaway.status = kwargs.get('status', 'active')
    giveaway.channel_id = kwargs.get('channel_id', -100123456789)
    giveaway.message_id = kwargs.get('message_id', 999)
    giveaway.title = kwargs.get('title', 'Test Giveaway')
    giveaway.description = kwargs.get('description', 'Test description')
    giveaway.winner_places = kwargs.get('winner_places', 1)
    end_time = kwargs.get('end_time')
    if end_time is None:
        end_time = datetime.now(timezone.utc) + timedelta(days=7)
    giveaway.end_time = end_time.replace(microsecond=0)
    return giveaway


def create_mock_participant(**kwargs):
    """Создание мок-объекта участника"""
    participant = MagicMock()
    participant.user_id = kwargs.get('user_id', 123)
    participant.username = kwargs.get('username', 'testuser')
    participant.first_name = kwargs.get('first_name', 'Test')
    return participant


def create_bot_mock():
    """Создание мок-объекта бота"""
    bot = AsyncMock()
    bot.send_message = AsyncMock()
    bot.get_chat_member = AsyncMock()
    return bot


class TestScheduler:
    """Тесты для модуля scheduler"""

    def setup_method(self):
        """Сброс состояния планировщика перед каждым тестом"""
        # Мокаем методы планировщика, чтобы избежать проблем с event loop
        with patch.object(scheduler, 'add_job'), \
                patch.object(scheduler, 'remove_job'), \
                patch.object(scheduler, 'get_job', return_value=None), \
                patch.object(scheduler, 'shutdown'), \
                patch.object(scheduler, 'get_jobs', return_value=[]):
            if scheduler.running:
                try:
                    scheduler.shutdown()
                except RuntimeError:
                    pass
        scheduler.remove_all_jobs()
        REMINDER_SETTINGS.clear()

    @pytest.mark.asyncio
    async def test_setup_scheduler(self):
        """Тест инициализации планировщика"""
        bot = create_bot_mock()
        giveaway1 = create_mock_giveaway(id=1)
        giveaway2 = create_mock_giveaway(id=2)

        with patch('utils.scheduler.get_active_giveaways', return_value=[giveaway1, giveaway2]):
            with patch('utils.scheduler.schedule_giveaway_finish') as mock_finish:
                with patch('utils.scheduler.schedule_reminders') as mock_remind:
                    with patch.object(scheduler, 'start') as mock_start:
                        await setup_scheduler(bot)
                        mock_start.assert_called_once()
                        assert mock_finish.call_count == 2
                        assert mock_remind.call_count == 2
                        assert 1 in REMINDER_SETTINGS
                        assert 2 in REMINDER_SETTINGS
                        # Проверяем, что планируется очистка старых розыгрышей
                        assert scheduler.get_job("cleanup_finished") is not None

    def test_schedule_giveaway_finish(self):
        """Тест планирования завершения розыгрыша"""
        bot = create_bot_mock()
        giveaway_id = 123
        end_time = (datetime.now(timezone.utc) + timedelta(days=7)).replace(microsecond=0)

        with patch.object(scheduler, 'get_job', return_value=None):
            with patch.object(scheduler, 'add_job') as mock_add:
                schedule_giveaway_finish(bot, giveaway_id, end_time)

                mock_add.assert_called_once()
                args = mock_add.call_args[0]
                kwargs = mock_add.call_args[1]

                assert args[0] == finish_giveaway_task
                assert isinstance(args[1], DateTrigger)
                assert kwargs['args'] == [bot, giveaway_id]
                assert kwargs['id'] == f"finish_giveaway_{giveaway_id}"
                assert kwargs['name'] == f"Завершение розыгрыша #{giveaway_id}"

    def test_schedule_reminders(self):
        """Тест планирования напоминаний"""
        bot = create_bot_mock()
        end_time = datetime.now(timezone.utc) + timedelta(days=10)
        giveaway = create_mock_giveaway(id=1, end_time=end_time)

        with patch.object(scheduler, 'get_job', return_value=None):
            with patch.object(scheduler, 'add_job') as mock_add:
                schedule_reminders(bot, giveaway)

                assert mock_add.call_count >= 3  # 3d, 1d, 3h

    @pytest.mark.asyncio
    async def test_send_reminder(self):
        """Тест отправки напоминания"""
        bot = create_bot_mock()
        REMINDER_SETTINGS[1] = {
            "enabled": True,
            "reminded_3d": False,
            "reminded_1d": False,
            "reminded_3h": False
        }

        giveaway = create_mock_giveaway(id=1)

        # ✅ Мокаем по реальному пути, откуда импортируется
        with patch('utils.scheduler.get_giveaway', new_callable=AsyncMock, return_value=giveaway):
            with patch('utils.scheduler.get_participants_count', new_callable=AsyncMock, return_value=10):
                with patch('utils.scheduler.get_participate_keyboard', return_value='keyboard'):
                    await send_reminder(bot, 1, "3d")

                    bot.send_message.assert_called_once()
                    call_args = bot.send_message.call_args[1]
                    assert "Test Giveaway" in call_args["text"]
                    assert "через 3 дня" in call_args["text"]
                    assert REMINDER_SETTINGS[1]["reminded_3d"] is True

    def test_disable_all_reminders(self):
        """Тест отключения всех напоминаний"""
        REMINDER_SETTINGS[1] = {
            "enabled": True,
            "reminded_3d": False,
            "reminded_1d": False,
            "reminded_3h": False
        }

        with patch.object(scheduler, 'get_job', return_value=True):
            with patch.object(scheduler, 'remove_job') as mock_remove:
                disable_all_reminders(1)
                assert mock_remove.call_count == 3
                assert REMINDER_SETTINGS[1]["enabled"] is False

    @pytest.mark.asyncio
    async def test_check_user_subscription(self):
        """Тест проверки подписки пользователя"""
        bot = create_bot_mock()
        chat_member = MagicMock()
        bot.get_chat_member.return_value = chat_member

        for status in ["member", "administrator", "creator"]:
            chat_member.status = status
            assert await check_user_subscription(bot, 123, -100123456789) is True

        for status in ["left", "kicked", "restricted"]:
            chat_member.status = status
            assert await check_user_subscription(bot, 123, -100123456789) is False

        bot.get_chat_member.side_effect = Exception("API Error")
        assert await check_user_subscription(bot, 123, -100123456789) is False

    def test_cancel_giveaway_schedule(self):
        """Тест отмены планирования завершения розыгрыша"""
        giveaway_id = 123
        job_id = f"finish_giveaway_{giveaway_id}"

        with patch.object(scheduler, 'get_job', return_value=True):
            with patch.object(scheduler, 'remove_job') as mock_remove:
                cancel_giveaway_schedule(giveaway_id)
                mock_remove.assert_called_with(job_id)

    @pytest.mark.asyncio
    async def test_finish_giveaway_task_with_participants(self):
        """Тест завершения розыгрыша с участниками"""
        bot = create_bot_mock()
        giveaway = create_mock_giveaway(id=1, winner_places=2, message_winner="Специальное сообщение для победителей")
        participant1 = create_mock_participant(user_id=1, username="user1", first_name="Alice")
        participant2 = create_mock_participant(user_id=2, username="user2", first_name="Bob")

        # Мокаем клиента Pyrogram
        with patch('utils.scheduler.get_pyrogram_client') as mock_get_client:
            mock_client = AsyncMock()
            mock_client.is_running = True
            mock_client.send_message = AsyncMock(return_value=MagicMock(id=123))
            mock_get_client.return_value = mock_client

            # ✅ Мокаем по реальному пути
            with patch('utils.scheduler.get_giveaway', new_callable=AsyncMock, return_value=giveaway):
                with patch('utils.scheduler.get_participants', new_callable=AsyncMock,
                           return_value=[participant1, participant2]):
                    with patch('utils.scheduler.check_user_subscription', new_callable=AsyncMock, return_value=True):
                        with patch('utils.scheduler.get_channel', new_callable=AsyncMock) as mock_get_channel:
                            with patch('utils.scheduler.finish_giveaway', new_callable=AsyncMock) as mock_finish:
                                # Мокаем результат get_channel
                                channel_mock = MagicMock()
                                channel_mock.admin = 987654321
                                mock_get_channel.return_value = channel_mock

                                await finish_giveaway_task(bot, 1)

                                mock_finish.assert_called_once()
                                assert bot.send_message.call_count == 2
                                # Первое сообщение - в канал
                                channel_call = bot.send_message.call_args_list[0][1]
                                assert "@user1" in channel_call["text"]
                                assert "🥇 <b>1 место:</b> @user1" in channel_call["text"]
                                assert channel_call["parse_mode"] == "HTML"
                                # Проверка отправки сообщения победителю через Pyrogram
                                mock_client.send_message.assert_called_once_with(1, "Специальное сообщение для победителей")
                                # Второе сообщение - администратору
                                admin_call = bot.send_message.call_args_list[1][1]
                                assert admin_call["chat_id"] == 987654321
                                assert "✅ Успешно" in admin_call["text"]

    @pytest.mark.asyncio
    async def test_finish_giveaway_task_without_participants(self):
        """Тест завершения розыгрыша без участников"""
        bot = create_bot_mock()
        giveaway = create_mock_giveaway(id=1)

        # Мокаем клиента Pyrogram
        with patch('utils.scheduler.get_pyrogram_client') as mock_get_client:
            mock_client = AsyncMock()
            mock_client.is_running = True
            mock_get_client.return_value = mock_client

            # ✅ Мокаем по реальному пути
            with patch('utils.scheduler.get_giveaway', new_callable=AsyncMock, return_value=giveaway):
                with patch('utils.scheduler.get_participants', new_callable=AsyncMock, return_value=[]):
                    with patch('utils.scheduler.finish_giveaway', new_callable=AsyncMock) as mock_finish:
                        await finish_giveaway_task(bot, 1)

                        bot.send_message.assert_called_once()
                        call_args = bot.send_message.call_args[1]
                        assert "К сожалению" in call_args["text"]
                        # Проверяем, что Pyrogram не использовался
                        mock_client.send_message.assert_not_called()

    @pytest.mark.asyncio
    async def test_cleanup_old_finished(self):
        """Тест очистки старых завершенных розыгрышей"""
        with patch('utils.scheduler.delete_finished_older_than', new_callable=AsyncMock, return_value=5):
            with patch('utils.scheduler.logging.info') as mock_info:
                await cleanup_old_finished(15)
                mock_info.assert_called_with("Очищено 5 завершённых розыгрышей (старше 15 дней)")

    def test_get_scheduler_status(self):
        """Тест получения статуса планировщика"""
        current_time = datetime.now(timezone.utc)
        job_mock = MagicMock()
        job_mock.id = "cleanup"
        job_mock.name = "Очистка завершенных розыгрышей старше 15 дней"
        job_mock.next_run_time = current_time

        # Мокаем scheduler.get_jobs() и используем настоящий running
        with patch.object(scheduler, 'get_jobs', return_value=[job_mock]):
            status = get_scheduler_status()

            assert status["running"] is scheduler.running  # не мокаем, читаем реальное значение
            assert status["jobs_count"] == 1
            assert status["jobs"][0]["id"] == "cleanup"
            assert status["jobs"][0]["name"] == "Очистка завершенных розыгрышей старше 15 дней"
            assert status["jobs"][0]["next_run_time"] == current_time
