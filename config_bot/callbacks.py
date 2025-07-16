"""
Модуль с callback-обработчиками для бота управления конфигурацией
"""

import re
import logging
from aiogram import F
from aiogram.types import CallbackQuery, InlineKeyboardButton, InaccessibleMessage
from aiogram.utils.keyboard import InlineKeyboardBuilder

from .keyboards import (
    create_main_keyboard, 
    create_sessions_keyboard, 
    create_session_menu_keyboard,
    create_profiles_keyboard,
    create_profile_menu_keyboard
)

logger = logging.getLogger(__name__)


async def safe_edit_message(callback: CallbackQuery, text: str, reply_markup=None, parse_mode="HTML"):
    """Безопасно редактирует сообщение, избегая ошибки 'message is not modified'"""
    if not callback.message or isinstance(callback.message, InaccessibleMessage):
        logger.error("callback.message отсутствует или недоступно")
        return False
    
    try:
        # Проверяем, изменился ли текст или клавиатура
        current_text = callback.message.text or callback.message.caption or ""
        if current_text != text or callback.message.reply_markup != reply_markup:
            await callback.message.edit_text(text, reply_markup=reply_markup, parse_mode=parse_mode)
            return True
        else:
            logger.debug("Содержимое сообщения не изменилось, пропускаем редактирование")
            return True
    except Exception as e:
        if "message is not modified" in str(e):
            logger.debug("Сообщение уже актуально")
            return True
        else:
            logger.error(f"Ошибка при редактировании сообщения: {e}")
            try:
                # Попробуем отправить новое сообщение
                await callback.message.answer(text, reply_markup=reply_markup, parse_mode=parse_mode)
                return True
            except Exception as e2:
                logger.error(f"Не удалось отправить новое сообщение: {e2}")
                return False


def register_callbacks(dp, config_manager, user_contexts, has_access_to_session, get_user_sessions):
    """Регистрирует все callback-обработчики"""
    
    @dp.callback_query(F.data == "back_to_main")
    async def back_to_main(callback: CallbackQuery):
        """Возврат к главному меню"""
        # logger.info(f"🔍 back_to_main: получен callback от пользователя {callback.from_user.username if callback.from_user else 'None'}")
        await callback.answer()  # Отвечаем на callback сразу
        
        text = ("🎁 <b>Панель управления покупателями подарков</b>\n\n"
                "Добро пожаловать в систему управления автоматической покупкой подарков!\n\n"
                "Выберите действие:")
        
        success = await safe_edit_message(callback, text, create_main_keyboard())
        if not success:
            logger.error("Не удалось вернуться к главному меню")

    @dp.callback_query(F.data == "stats")
    async def show_stats(callback: CallbackQuery):
        """Показывает общую статистику"""
        # logger.info(f"🔍 show_stats: получен callback от пользователя {callback.from_user.username if callback.from_user else 'None'}")
        await callback.answer()  # Отвечаем на callback сразу
        
        if not callback.from_user:
            return
        
        user_sessions = get_user_sessions(callback.from_user.username)
        
        if not user_sessions:
            await callback.answer("❌ У вас нет доступных сессий")
            return
        
        text = "📊 <b>Статистика ваших покупателей:</b>\n\n"
        
        for session in user_sessions:
            config = config_manager.get_config(session)
            if config:
                status = "✅ Включен" if config.enabled else "❌ Выключен"
                text += f"<b>{session}</b>\n"
                text += f"  Статус: {status}\n"
                text += f"  Активный профиль: {config.active_profile}\n\n"
        
        builder = InlineKeyboardBuilder()
        builder.add(InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main"))
        
        success = await safe_edit_message(callback, text, builder.as_markup())
        if not success:
            logger.error("Не удалось показать статистику")

    @dp.callback_query(F.data == "settings")
    async def show_settings(callback: CallbackQuery):
        """Показывает настройки"""
        #logger.info(f"🔍 show_settings: получен callback от пользователя {callback.from_user.username if callback.from_user else 'None'}")
        await callback.answer()  # Отвечаем на callback сразу
        
        if not callback.from_user:
            return
        
        user_sessions = get_user_sessions(callback.from_user.username)
        
        if not user_sessions:
            await callback.answer("❌ У вас нет доступных сессий")
            return
        
        text = "⚙️ <b>Настройки</b>\n\nВыберите сессию для настройки:"
        markup = create_sessions_keyboard(callback.from_user, get_user_sessions)
        
        success = await safe_edit_message(callback, text, markup)
        if not success:
            logger.error("Не удалось показать настройки")

    @dp.callback_query(F.data.startswith("session_"))
    async def session_menu(callback: CallbackQuery):
        """Меню для конкретной сессии"""
        # logger.info(f"🔍 session_menu: получен callback: data='{callback.data}', user='{callback.from_user.username if callback.from_user else 'None'}'")
        
        await callback.answer()  # Отвечаем на callback сразу
        
        # logger.info(f"session_menu вызван: data={callback.data}, user={callback.from_user.username if callback.from_user else 'None'}")
        
        if not callback.data or not callback.from_user:
            logger.error("Отсутствуют callback.data или callback.from_user")
            return
        
        session_name = callback.data.split("_", 1)[1]
        # logger.info(f"Извлечено имя сессии: {session_name}")
        
        # Проверяем доступ
        has_access = has_access_to_session(callback.from_user.username, session_name)
        # logger.info(f"Проверка доступа для {callback.from_user.username} к сессии {session_name}: {has_access}")
        
        if not has_access:
            logger.warning(f"Пользователь {callback.from_user.username} не имеет доступа к сессии {session_name}")
            await callback.answer("❌ У вас нет доступа к этой сессии")
            return
        
        # НЕ создаем конфигурацию, просто получаем существующую
        config = config_manager.get_config(session_name)
        # logger.info(f"Конфигурация для сессии {session_name}: {'найдена' if config else 'не найдена'}")
        
        if not config:
            logger.warning(f"Конфигурация для сессии {session_name} не найдена")
            await callback.answer("❌ Конфигурация не найдена. Создайте конфигурацию через настройки профилей.")
            return
        
        status = "✅ Включен" if config.enabled else "❌ Выключен"
        session_safe = session_name.replace('_', '\\_').replace('<', '&lt;').replace('>', '&gt;')
        
        text = f"⚙️ <b>Настройки для {session_safe}</b>\n\n"
        text += f"Статус: {status}\n"
        text += f"Активный профиль: <b>{config.active_profile}</b>\n\n"
        text += "Выберите действие:"
        
        # logger.info(f"Попытка отправить сообщение с текстом: {text[:50]}...")
        
        success = await safe_edit_message(
            callback, 
            text, 
            create_session_menu_keyboard(session_name, config_manager)
        )
        
        if not success:
            logger.error(f"Не удалось показать меню для сессии {session_name}")

    @dp.callback_query(F.data.startswith("profiles|"))
    async def show_profiles(callback: CallbackQuery):
        """Показывает профили для сессии"""
        await callback.answer()  # Отвечаем на callback сразу
        
        if not callback.data or not callback.from_user:
            return
        
        # Очищаем контекст пользователя
        if callback.from_user.id in user_contexts:
            del user_contexts[callback.from_user.id]
        
        # Формат: profiles|{session_name}
        session_name = callback.data.split("|")[1]
        
        # Проверяем доступ
        if not has_access_to_session(callback.from_user.username, session_name):
            await callback.answer("❌ У вас нет доступа к этой сессии")
            return
        
        config = config_manager.get_config(session_name)
        if not config:
            await callback.answer("❌ Конфигурация не найдена")
            return
        
        session_safe = session_name.replace('_', '\\_').replace('<', '&lt;').replace('>', '&gt;')
        
        text = f"🎯 <b>Профили закупки для {session_safe}</b>\n\n"
        text += f"Активный профиль: <b>{config.active_profile}</b>\n\n"
        text += "Выберите профиль для настройки:"
        
        success = await safe_edit_message(
            callback, 
            text, 
            create_profiles_keyboard(session_name, config_manager)
        )
        if not success:
            logger.error(f"Не удалось показать профили для сессии {session_name}")

    @dp.callback_query(F.data.startswith("profile|"))
    async def show_profile_menu(callback: CallbackQuery):
        """Показывает меню для конкретного профиля"""
        await callback.answer()  # Отвечаем на callback сразу
        
        if not callback.data or not callback.from_user:
            return
        
        # Очищаем контекст пользователя
        if callback.from_user.id in user_contexts:
            del user_contexts[callback.from_user.id]
        
        # Формат: profile|{session_name}|{profile_name}
        parts = callback.data.split("|")
        if len(parts) < 3:
            return
        
        session_name = parts[1]
        profile_name = parts[2]
        
        # Проверяем доступ
        if not has_access_to_session(callback.from_user.username, session_name):
            await callback.answer("❌ У вас нет доступа к этой сессии")
            return
        
        config = config_manager.get_config(session_name)
        if not config or profile_name not in config.profiles:
            await callback.answer("❌ Профиль не найден")
            return
        
        profile = config.profiles[profile_name]
        session_safe = session_name.replace('_', '\\_').replace('<', '&lt;').replace('>', '&gt;')
        
        text = f"🎯 <b>Профиль \"{profile_name}\" для {session_safe}</b>\n\n"
        text += f"Статус: {'🔸 Активен' if config.active_profile == profile_name else '⚪ Не активен'}\n\n"
        text += "<b>Стратегии:</b>\n"
        
        for i, strategy in enumerate(profile.get_strategies()):
            remaining = strategy.max_spend - strategy.current_spent
            send_status = "🏠 Себе" if strategy.send_to_self else f"📢 {strategy.target_channel_id}"
            text += f"<b>Стратегия {i + 1}</b> (Приоритет: {strategy.priority})\n"
            text += f"  💰 Диапазон: {strategy.min_price}-{strategy.max_price} ⭐\n"
            text += f"  💳 Лимит: {strategy.max_spend} ⭐\n"
            text += f"  📊 Потрачено: {strategy.current_spent} ⭐\n"
            text += f"  🔋 Остается: {remaining} ⭐\n"
            text += f"  📤 Отправка: {send_status}\n\n"
        
        # Убираем лишний перенос строки в конце, если он есть
        text = text.strip()
        
        success = await safe_edit_message(
            callback,
            text,
            create_profile_menu_keyboard(session_name, profile_name, config_manager)
        )
        if not success:
            logger.error(f"Не удалось показать меню профиля {profile_name} для сессии {session_name}")

    @dp.callback_query(F.data.startswith("activate_profile|"))
    async def activate_profile(callback: CallbackQuery):
        """Активирует профиль"""
        if not callback.data or not callback.from_user:
            return
        
        # Формат: activate_profile|{session_name}|{profile_name}
        parts = callback.data.split("|")
        if len(parts) < 3:
            return
        
        session_name = parts[1]
        profile_name = parts[2]
        
        # Проверяем доступ
        if not has_access_to_session(callback.from_user.username, session_name):
            await callback.answer("❌ У вас нет доступа к этой сессии")
            return
        
        try:
            success = config_manager.set_active_profile(session_name, profile_name, callback.from_user.id)
            
            if success:
                await callback.answer(f"✅ Профиль '{profile_name}' активирован")
                
                # Обновляем меню профиля
                if callback.message and not isinstance(callback.message, InaccessibleMessage):
                    # Создаем новый CallbackQuery для обновления меню
                    new_callback_data = f"profile|{session_name}|{profile_name}"
                    fake_callback = type(callback)(
                        id=callback.id,
                        from_user=callback.from_user,
                        chat_instance=callback.chat_instance,
                        data=new_callback_data,
                        message=callback.message
                    )
                    await show_profile_menu(fake_callback)
            else:
                await callback.answer(f"❌ Не удалось активировать профиль '{profile_name}'")
        
        except Exception as e:
            logger.error(f"Ошибка при активации профиля: {e}")
            error_msg = str(e)[:50] + "..." if len(str(e)) > 50 else str(e)
            await callback.answer(f"❌ Ошибка: {error_msg}")

    @dp.callback_query(F.data.startswith("add_profile|"))
    async def add_profile_prompt(callback: CallbackQuery):
        """Запрашивает имя нового профиля"""
        if not callback.data or not callback.from_user:
            return
        
        # Формат: add_profile|{session_name}
        session_name = callback.data.split("|")[1]
        
        # Проверяем доступ
        if not has_access_to_session(callback.from_user.username, session_name):
            await callback.answer("❌ У вас нет доступа к этой сессии")
            return
        
        # Устанавливаем контекст
        user_contexts[callback.from_user.id] = {
            'waiting_for': 'profile_name',
            'session_name': session_name
        }
        
        text = f"📝 <b>Создание нового профиля</b>\n\n"
        text += f"Введите имя нового профиля для сессии {session_name}:\n\n"
        text += "ℹ️ Имя должно быть уникальным и содержать только буквы, цифры и символы '_', '-'"
        
        builder = InlineKeyboardBuilder()
        builder.add(InlineKeyboardButton(text="🔙 Отмена", callback_data=f"profiles|{session_name}"))
        
        success = await safe_edit_message(callback, text, builder.as_markup())
        if not success:
            logger.error(f"Не удалось показать запрос имени профиля для сессии {session_name}")

    @dp.callback_query(F.data.startswith("delete_profile_confirm|"))
    async def delete_profile_confirm(callback: CallbackQuery):
        """Подтверждение удаления профиля"""
        if not callback.data or not callback.from_user:
            return
        
        # Формат: delete_profile_confirm|{session_name}|{profile_name}
        parts = callback.data.split("|")
        if len(parts) < 3:
            return
        
        session_name = parts[1]
        profile_name = parts[2]
        
        # Проверяем доступ
        if not has_access_to_session(callback.from_user.username, session_name):
            await callback.answer("❌ У вас нет доступа к этой сессии")
            return
        
        text = f"⚠️ <b>Подтверждение удаления</b>\n\n"
        text += f"Вы действительно хотите удалить профиль '<b>{profile_name}</b>'?\n\n"
        text += "❗ Это действие нельзя отменить!"
        
        builder = InlineKeyboardBuilder()
        builder.add(InlineKeyboardButton(text="✅ Да, удалить", callback_data=f"confirm_delete|{session_name}|{profile_name}"))
        builder.add(InlineKeyboardButton(text="🔙 Отмена", callback_data=f"profile|{session_name}|{profile_name}"))
        
        success = await safe_edit_message(callback, text, builder.as_markup())
        if not success:
            logger.error(f"Не удалось показать подтверждение удаления профиля {profile_name}")

    @dp.callback_query(F.data.startswith("confirm_delete|"))
    async def confirm_delete_profile(callback: CallbackQuery):
        """Подтверждает удаление профиля"""
        if not callback.data or not callback.from_user:
            return
        
        # Формат: confirm_delete|{session_name}|{profile_name}
        parts = callback.data.split("|")
        if len(parts) < 3:
            return
        
        session_name = parts[1]
        profile_name = parts[2]
        
        # Проверяем доступ
        if not has_access_to_session(callback.from_user.username, session_name):
            await callback.answer("❌ У вас нет доступа к этой сессии")
            return
        
        try:
            success = config_manager.delete_profile(session_name, profile_name, callback.from_user.id)
            
            if success:
                await callback.answer(f"✅ Профиль '{profile_name}' удален")
                
                # Создаем новый CallbackQuery для перехода к списку профилей
                if callback.message and not isinstance(callback.message, InaccessibleMessage):
                    new_callback_data = f"profiles|{session_name}"
                    fake_callback = type(callback)(
                        id=callback.id,
                        from_user=callback.from_user,
                        chat_instance=callback.chat_instance,
                        data=new_callback_data,
                        message=callback.message
                    )
                    await show_profiles(fake_callback)
            else:
                await callback.answer(f"❌ Не удалось удалить профиль '{profile_name}'")
        
        except Exception as e:
            logger.error(f"Ошибка при удалении профиля: {e}")
            error_msg = str(e)[:50] + "..." if len(str(e)) > 50 else str(e)
            await callback.answer(f"❌ Ошибка: {error_msg}")

    return {
        'back_to_main': back_to_main,
        'show_stats': show_stats,
        'show_settings': show_settings,
        'session_menu': session_menu,
        'show_profiles': show_profiles,
        'show_profile_menu': show_profile_menu,
        'activate_profile': activate_profile,
        'add_profile_prompt': add_profile_prompt,
        'delete_profile_confirm': delete_profile_confirm,
        'confirm_delete_profile': confirm_delete_profile
    }
