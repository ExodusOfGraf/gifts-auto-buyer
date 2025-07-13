"""
Модуль с callback-обработчиками для редактирования стратегий и административных функций
"""

import logging
from aiogram import F
from aiogram.types import CallbackQuery, InlineKeyboardButton, InaccessibleMessage
from aiogram.utils.keyboard import InlineKeyboardBuilder

from .keyboards import create_session_menu_keyboard

logger = logging.getLogger(__name__)


def register_strategy_callbacks(dp, config_manager, user_contexts, has_access_to_session):
    """Регистрирует callback-обработчики для работы со стратегиями"""
    
    @dp.callback_query(F.data.startswith("edit_strategy|"))
    async def edit_strategy_prompt(callback: CallbackQuery):
        """Запрашивает параметры стратегии для редактирования"""
        if not callback.data or not callback.from_user:
            return
        
        # Формат: edit_strategy|{session_name}|{profile_name}|{strategy_number}
        parts = callback.data.split("|")
        if len(parts) < 4:
            return
        
        session_name = parts[1]
        profile_name = parts[2]
        strategy_index = int(parts[3]) - 1  # Индекс стратегии (0-3)
        
        # Проверяем доступ
        if not has_access_to_session(callback.from_user.username, session_name):
            await callback.answer("❌ У вас нет доступа к этой сессии")
            return
        
        config = config_manager.get_config(session_name)
        if not config or profile_name not in config.profiles:
            await callback.answer("❌ Профиль не найден")
            return
        
        profile = config.profiles[profile_name]
        if strategy_index >= len(profile.get_strategies()):
            await callback.answer("❌ Стратегия не найдена")
            return
        
        strategy = profile.get_strategies()[strategy_index]
        
        text = f"✏️ <b>Редактирование стратегии {strategy_index + 1}</b>\n\n"
        text += f"Профиль: <b>{profile_name}</b>\n"
        text += f"Сессия: <b>{session_name}</b>\n"
        text += f"Приоритет: <b>{strategy.priority}</b>\n\n"
        text += "<b>Текущие параметры:</b>\n"
        text += f"💰 Мин. цена: {strategy.min_price} ⭐\n"
        text += f"💰 Макс. цена: {strategy.max_price} ⭐\n"
        text += f"💳 Лимит трат: {strategy.max_spend} ⭐\n"
        text += f"📊 Потрачено: {strategy.current_spent} ⭐\n\n"
        text += "Выберите что редактировать:"
        
        builder = InlineKeyboardBuilder()
        builder.add(InlineKeyboardButton(text="💰 Параметры стратегии", callback_data=f"edit_strategy_params|{session_name}|{profile_name}|{strategy_index + 1}"))
        builder.add(InlineKeyboardButton(text="📬 Настройки отправки", callback_data=f"edit_strategy_send|{session_name}|{profile_name}|{strategy_index + 1}"))
        builder.add(InlineKeyboardButton(text="🔙 Отмена", callback_data=f"profile|{session_name}|{profile_name}"))
        
        if callback.message and not isinstance(callback.message, InaccessibleMessage):
            try:
                await callback.message.edit_text(
                    text,
                    reply_markup=builder.as_markup(),
                    parse_mode="HTML"
                )
            except Exception as e:
                logger.error(f"Ошибка при редактировании сообщения: {e}")

    @dp.callback_query(F.data.startswith("edit_strategy_params|"))
    async def edit_strategy_params_prompt(callback: CallbackQuery):
        """Запрашивает новые параметры стратегии"""
        if not callback.data or not callback.from_user:
            return
        
        # Формат: edit_strategy_params|{session_name}|{profile_name}|{strategy_number}
        parts = callback.data.split("|")
        if len(parts) < 4:
            return
        
        session_name = parts[1]
        profile_name = parts[2]
        strategy_index = int(parts[3]) - 1  # Индекс стратегии (0-3)
        
        # Проверяем доступ
        if not has_access_to_session(callback.from_user.username, session_name):
            await callback.answer("❌ У вас нет доступа к этой сессии")
            return
        
        # Устанавливаем контекст для ввода параметров
        user_contexts[callback.from_user.id] = {
            'waiting_for': 'strategy_params',
            'session_name': session_name,
            'profile_name': profile_name,
            'strategy_index': strategy_index
        }
        
        text = f"✏️ <b>Редактирование параметров стратегии {strategy_index + 1}</b>\n\n"
        text += f"Профиль: <b>{profile_name}</b>\n"
        text += f"Сессия: <b>{session_name}</b>\n\n"
        text += "Введите новые параметры в формате:\n"
        text += "<code>мин_цена макс_цена лимит_трат</code>\n\n"
        text += "Пример: <code>1 10 100</code>\n"
        text += "(цены в звездах, лимит трат в звездах)"
        
        builder = InlineKeyboardBuilder()
        builder.add(InlineKeyboardButton(text="🔙 Отмена", callback_data=f"profile|{session_name}|{profile_name}"))
        
        if callback.message and not isinstance(callback.message, InaccessibleMessage):
            try:
                await callback.message.edit_text(
                    text,
                    reply_markup=builder.as_markup(),
                    parse_mode="HTML"
                )
            except Exception as e:
                logger.error(f"Ошибка при запросе параметров стратегии: {e}")

    @dp.callback_query(F.data.startswith("edit_strategy_send|"))
    async def edit_strategy_send_menu(callback: CallbackQuery):
        """Показывает меню настройки отправки для конкретной стратегии."""
        if not callback.data or not callback.from_user:
            return

        # Формат: edit_strategy_send|{session_name}|{profile_name}|{strategy_number}
        try:
            _, session_name, profile_name, strategy_num_str = callback.data.split("|")
            strategy_num = int(strategy_num_str)
            strategy_index = strategy_num - 1
        except (ValueError, IndexError):
            logger.warning(f"Некорректный callback.data в edit_strategy_send_menu: {callback.data}")
            return

        if not has_access_to_session(callback.from_user.username, session_name):
            await callback.answer("❌ У вас нет доступа к этой сессии", show_alert=True)
            return

        config = config_manager.get_config(session_name)
        if not config or profile_name not in config.profiles:
            await callback.answer("❌ Профиль не найден", show_alert=True)
            return
        
        profile = config.profiles[profile_name]
        strategy = profile.get_strategies()[strategy_index]
        session_safe = session_name.replace('_', '\\_')

        text = (
            f"📤 <b>Настройка отправки для Стратегии {strategy_num}</b>\n\n"
            f"Профиль: <b>{profile_name}</b>\n"
            f"Сессия: <b>{session_safe}</b>\n\n"
        )
        
        if strategy.send_to_self:
            text += "🔸 <b>Текущая настройка:</b> Отправка себе в Избранное\n"
        else:
            text += f"🔸 <b>Текущая настройка:</b> Отправка в канал <code>{strategy.target_channel_id}</code>\n"
        
        text += "\nВыберите, куда отправлять подарки, купленные по этой стратегии:"

        builder = InlineKeyboardBuilder()
        base_data = f"{session_name}|{profile_name}|{strategy_num}"
        
        if not strategy.send_to_self:
            builder.button(text="🏠 Отправлять себе", callback_data=f"set_strat_send_self|{base_data}")
        
        if strategy.send_to_self:
            builder.button(text="📢 Отправлять в канал", callback_data=f"set_strat_send_channel|{base_data}")
        else:
            builder.button(text="📝 Изменить канал", callback_data=f"set_strat_send_channel|{base_data}")

        builder.button(text="🔙 Назад к профилю", callback_data=f"profile|{session_name}|{profile_name}")
        builder.adjust(1)

        if callback.message and not isinstance(callback.message, InaccessibleMessage):
            try:
                await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
            except Exception as e:
                logger.error(f"Ошибка при показе меню настройки отправки: {e}")

    @dp.callback_query(F.data.startswith("set_strat_send_self|"))
    async def set_strategy_send_to_self(callback: CallbackQuery):
        """Устанавливает для стратегии отправку подарков в профиль."""
        if not callback.data or not callback.from_user:
            return

        try:
            _, session_name, profile_name, strategy_num_str = callback.data.split("|")
            strategy_num = int(strategy_num_str)
        except (ValueError, IndexError):
            await callback.answer("❌ Ошибка в данных")
            return

        if not has_access_to_session(callback.from_user.username, session_name):
            await callback.answer("❌ У вас нет доступа к этой сессии")
            return

        config = config_manager.get_config(session_name)
        if not config or profile_name not in config.profiles:
            await callback.answer("❌ Профиль не найден")
            return

        profile = config.profiles[profile_name]
        strategies = profile.get_strategies()
        strategies[strategy_num - 1].send_to_self = True
        strategies[strategy_num - 1].target_channel_id = 0
        config_manager.set_config(session_name, config)

        await callback.answer(f"✅ Стратегия {strategy_num}: настроена отправка себе")

        # Обновляем меню
        new_callback_data = f"edit_strategy_send|{session_name}|{profile_name}|{strategy_num}"
        fake_callback = type(callback)(
            id=callback.id,
            from_user=callback.from_user,
            chat_instance=callback.chat_instance,
            data=new_callback_data,
            message=callback.message
        )
        await edit_strategy_send_menu(fake_callback)

    @dp.callback_query(F.data.startswith("set_strat_send_channel|"))
    async def set_strategy_send_to_channel_prompt(callback: CallbackQuery):
        """Запрашивает ID канала для отправки подарков стратегии."""
        if not callback.data or not callback.from_user:
            return

        try:
            _, session_name, profile_name, strategy_num_str = callback.data.split("|")
            strategy_num = int(strategy_num_str)
        except (ValueError, IndexError):
            await callback.answer("❌ Ошибка в данных")
            return

        if not has_access_to_session(callback.from_user.username, session_name):
            await callback.answer("❌ У вас нет доступа к этой сессии")
            return

        # Устанавливаем контекст для ввода ID канала
        user_contexts[callback.from_user.id] = {
            'waiting_for': 'strategy_channel_id',
            'session_name': session_name,
            'profile_name': profile_name,
            'strategy_num': strategy_num
        }

        text = (
            f"📢 <b>Настройка канала для Стратегии {strategy_num}</b>\n\n"
            f"Введите ID канала, куда отправлять подарки:\n\n"
            f"Формат: <code>-1234567890</code>\n"
            f"(отрицательное число для каналов и групп)"
        )

        builder = InlineKeyboardBuilder()
        builder.button(text="🔙 Отмена", callback_data=f"edit_strategy_send|{session_name}|{profile_name}|{strategy_num}")
        
        if callback.message and not isinstance(callback.message, InaccessibleMessage):
            try:
                await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
            except Exception as e:
                logger.error(f"Ошибка при запросе ID канала: {e}")

    return {
        'edit_strategy_prompt': edit_strategy_prompt,
        'edit_strategy_params_prompt': edit_strategy_params_prompt,
        'edit_strategy_send_menu': edit_strategy_send_menu,
        'set_strategy_send_to_self': set_strategy_send_to_self,
        'set_strategy_send_to_channel_prompt': set_strategy_send_to_channel_prompt
    }


def register_admin_callbacks(dp, config_manager, has_access_to_session):
    """Регистрирует административные callback-обработчики"""
    
    @dp.callback_query(F.data.startswith("session_stats_"))
    async def session_stats(callback: CallbackQuery):
        """Показывает статистику для конкретной сессии"""
        await callback.answer()  # Отвечаем на callback сразу
        
        if not callback.data or not callback.from_user:
            return
        
        session_name = callback.data.split("_", 2)[2]
        
        # Проверяем доступ
        if not has_access_to_session(callback.from_user.username, session_name):
            if callback.message and not isinstance(callback.message, InaccessibleMessage):
                await callback.message.answer("❌ У вас нет доступа к этой сессии")
            return
        
        config = config_manager.get_config(session_name)
        if not config:
            await callback.answer("❌ Конфигурация не найдена")
            return
        
        session_safe = session_name.replace('_', '\\_').replace('<', '&lt;').replace('>', '&gt;')
        
        text = f"📊 <b>Статистика для {session_safe}</b>\n\n"
        text += f"Статус: {'✅ Включен' if config.enabled else '❌ Выключен'}\n"
        text += f"Активный профиль: <b>{config.active_profile}</b>\n\n"
        
        active_profile = config.profiles.get(config.active_profile)
        if active_profile:
            text += "<b>Стратегии активного профиля:</b>\n"
            for i, strategy in enumerate(active_profile.get_strategies()):
                remaining = strategy.max_spend - strategy.current_spent
                text += f"<b>Стратегия {i + 1}</b> (Приоритет: {strategy.priority})\n"
                text += f"  💰 Диапазон: {strategy.min_price}-{strategy.max_price} ⭐\n"
                text += f"  💳 Лимит: {strategy.max_spend} ⭐\n"
                text += f"  📊 Потрачено: {strategy.current_spent} ⭐\n"
                text += f"  🔋 Остается: {remaining} ⭐\n\n"
        
        builder = InlineKeyboardBuilder()
        builder.add(InlineKeyboardButton(text="🔙 Назад", callback_data=f"session_{session_name}"))
        
        if callback.message and not isinstance(callback.message, InaccessibleMessage):
            try:
                await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
            except Exception as e:
                logger.error(f"Ошибка при редактировании сообщения: {e}")

    @dp.callback_query(F.data.startswith("toggle_"))
    async def toggle_session(callback: CallbackQuery):
        """Включает/выключает сессию"""
        await callback.answer()  # Отвечаем на callback сразу
        
        if not callback.data or not callback.from_user:
            return
        
        # Формат: toggle_{action}_{session_name}
        parts = callback.data.split("_", 2)
        if len(parts) < 3:
            return
        
        action = parts[1]  # enable или disable
        session_name = parts[2]
        
        # Проверяем доступ
        if not has_access_to_session(callback.from_user.username, session_name):
            await callback.answer("❌ У вас нет доступа к этой сессии")
            return
        
        config = config_manager.get_config(session_name)
        if not config:
            await callback.answer("❌ Конфигурация не найдена")
            return
        
        config.enabled = (action == "enable")
        config_manager.set_config(session_name, config)
        
        status_text = "включена" if config.enabled else "выключена"
        await callback.answer(f"✅ Сессия {session_name} {status_text}")
        
        # Обновляем меню с новым статусом
        if callback.message and not isinstance(callback.message, InaccessibleMessage):
            status = "✅ Включен" if config.enabled else "❌ Выключен"
            session_safe = session_name.replace('_', '\\_').replace('<', '&lt;').replace('>', '&gt;')
            
            text = f"⚙️ <b>Настройки для {session_safe}</b>\n\n"
            text += f"Статус: {status}\n"
            text += f"Активный профиль: <b>{config.active_profile}</b>\n\n"
            text += "Выберите действие:"
            
            try:
                await callback.message.edit_text(
                    text,
                    reply_markup=create_session_menu_keyboard(session_name, config_manager),
                    parse_mode="HTML"
                )
            except Exception as e:
                logger.error(f"Ошибка при обновлении меню после изменения статуса: {e}")

    @dp.callback_query(F.data.startswith("reset_"))
    async def reset_session_spending(callback: CallbackQuery):
        """Сбрасывает траты для сессии"""
        await callback.answer()  # Отвечаем на callback сразу
        
        if not callback.data or not callback.from_user:
            return
        
        session_name = callback.data.split("_", 1)[1]
        
        # Проверяем доступ
        if not has_access_to_session(callback.from_user.username, session_name):
            if callback.message and not isinstance(callback.message, InaccessibleMessage):
                await callback.message.answer("❌ У вас нет доступа к этой сессии")
            return
        
        config = config_manager.get_config(session_name)
        if not config:
            if callback.message and not isinstance(callback.message, InaccessibleMessage):
                await callback.message.answer("❌ Конфигурация не найдена. Создайте конфигурацию через настройки профилей.")
            return
        
        config.reset_daily_spending()
        config_manager.set_config(session_name, config)
        
        await callback.answer(f"✅ Траты для {session_name} сброшены")
        
        # Обновляем меню сессии с новыми данными
        if callback.message and not isinstance(callback.message, InaccessibleMessage):
            status = "✅ Включен" if config.enabled else "❌ Выключен"
            session_safe = session_name.replace('_', '\\_').replace('<', '&lt;').replace('>', '&gt;')
            
            text = f"⚙️ <b>Настройки для {session_safe}</b>\n\n"
            text += f"Статус: {status}\n"
            text += f"Активный профиль: <b>{config.active_profile}</b>\n\n"
            text += f"✅ Траты сброшены!\n\n"
            text += "Выберите действие:"
            
            try:
                await callback.message.edit_text(
                    text,
                    reply_markup=create_session_menu_keyboard(session_name, config_manager),
                    parse_mode="HTML"
                )
            except Exception as e:
                logger.error(f"Ошибка при обновлении меню после сброса трат: {e}")

    return {
        'session_stats': session_stats,
        'toggle_session': toggle_session,
        'reset_session_spending': reset_session_spending
    }
