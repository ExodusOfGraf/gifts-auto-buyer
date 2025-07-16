"""
Модуль с функциями создания клавиатур для бота управления конфигурацией
"""

from aiogram.types import InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder


def create_main_keyboard():
    """Создает главную клавиатуру"""
    builder = InlineKeyboardBuilder()
    builder.add(InlineKeyboardButton(text="📊 Статистика", callback_data="stats"))
    builder.add(InlineKeyboardButton(text="⚙️ Настройки", callback_data="settings"))
    builder.adjust(1)
    return builder.as_markup()


def create_sessions_keyboard(user, get_user_sessions_func):
    """Создает клавиатуру с сессиями доступными пользователю"""
    builder = InlineKeyboardBuilder()
    user_sessions = get_user_sessions_func(user.username)
    
    for session in user_sessions:
        builder.add(InlineKeyboardButton(text=session, callback_data=f"session_{session}"))
    builder.add(InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main"))
    builder.adjust(2)
    return builder.as_markup()


def create_session_menu_keyboard(session_name: str, config_manager):
    """Создает меню для конкретной сессии"""
    builder = InlineKeyboardBuilder()
    builder.add(InlineKeyboardButton(text="🎯 Профили закупки", callback_data=f"profiles|{session_name}"))
    
    config = config_manager.get_config(session_name)
    if config:
        status_text = "✅ Включен" if config.enabled else "❌ Выключен"
        toggle_action = "disable" if config.enabled else "enable"
        builder.add(InlineKeyboardButton(text=status_text, callback_data=f"toggle_{toggle_action}_{session_name}"))
    
    builder.add(InlineKeyboardButton(text="🔄 Сброс трат", callback_data=f"reset_{session_name}"))
    builder.add(InlineKeyboardButton(text="🔙 Назад", callback_data="settings"))
    builder.adjust(1)
    return builder.as_markup()


def create_profiles_keyboard(session_name: str, config_manager):
    """Создает клавиатуру управления профилями"""
    builder = InlineKeyboardBuilder()
    
    config = config_manager.get_config(session_name)
    if config:
        for profile_name in config.profiles.keys():
            status = "🔸" if config.active_profile == profile_name else "⚪"
            builder.add(InlineKeyboardButton(
                text=f"{status} {profile_name}", 
                callback_data=f"profile|{session_name}|{profile_name}"
            ))
        
        if len(config.profiles) < 4:
            builder.add(InlineKeyboardButton(text="➕ Добавить профиль", callback_data=f"add_profile|{session_name}"))
    
    builder.add(InlineKeyboardButton(text="🔙 Назад", callback_data=f"session_{session_name}"))
    builder.adjust(1)
    return builder.as_markup()


def create_profile_menu_keyboard(session_name: str, profile_name: str, config_manager):
    """Создает меню для конкретного профиля"""
    builder = InlineKeyboardBuilder()
    
    config = config_manager.get_config(session_name)
    if config:
        # Кнопки для редактирования параметров и отправки для каждой стратегии
        for i in range(4):
            builder.row(
                InlineKeyboardButton(text=f"⚙️ Параметры {i+1}", callback_data=f"edit_strategy_params|{session_name}|{profile_name}|{i+1}"),
                InlineKeyboardButton(text=f"📤 Отправка {i+1}", callback_data=f"edit_strategy_send|{session_name}|{profile_name}|{i+1}")
            )

        # Кнопки управления профилем
        if config.active_profile != profile_name:
            builder.row(InlineKeyboardButton(text="✅ Сделать активным", callback_data=f"activate_profile|{session_name}|{profile_name}"))
        
        if profile_name != "default":
            builder.row(InlineKeyboardButton(text="🗑️ Удалить профиль", callback_data=f"delete_profile_confirm|{session_name}|{profile_name}"))
    
    builder.row(InlineKeyboardButton(text="🔙 Назад", callback_data=f"profiles|{session_name}"))
    
    return builder.as_markup()
