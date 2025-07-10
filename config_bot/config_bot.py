import asyncio
import logging
import os
import sys
import re

import asyncio
import logging
import os
import sys
import json
import re
import aiohttp

# Добавляем родительскую папку в путь для импорта
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, InlineKeyboardButton, CallbackQuery, InaccessibleMessage
from aiogram.filters import Command
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.client.session.aiohttp import AiohttpSession
import aiohttp

from buyers.buyer_config import BuyerConfigManager, BuyerConfig, BuyingStrategy, BuyingProfile
from app.config import BUYER_SESSIONS, MANAGEMENT_BOT_TOKEN, ADMIN_USER_ID, PROXY_URL, BUYER_OWNERS, SUPER_ADMINS

# Конфигурация бота
BOT_TOKEN = MANAGEMENT_BOT_TOKEN
ADMIN_USER_ID = ADMIN_USER_ID

# Создаем сессию с прокси, если настроен
if PROXY_URL:
    connector = aiohttp.TCPConnector(limit=100, limit_per_host=30)
    session = AiohttpSession(
        connector=connector,
        timeout=aiohttp.ClientTimeout(total=60),
        proxy=PROXY_URL
    )
    bot = Bot(token=BOT_TOKEN, session=session)
else:
    bot = Bot(token=BOT_TOKEN)

storage = MemoryStorage()
dp = Dispatcher(storage=storage)

# Менеджер конфигураций
config_manager = BuyerConfigManager("data/buyer_configs.json")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Глобальные переменные для хранения контекста пользователей
user_contexts = {}

def is_admin(user_id: int) -> bool:
    """Проверяет, является ли пользователь администратором"""
    return user_id == ADMIN_USER_ID or user_id in SUPER_ADMINS

def has_access_to_session(user_id: int, session_name: str) -> bool:
    """Проверяет, имеет ли пользователь доступ к управлению сессией"""
    # Суперадмины имеют доступ ко всем сессиям
    if user_id in SUPER_ADMINS:
        return True
    
    # Проверяем права владельца
    return BUYER_OWNERS.get(session_name) == user_id

def get_user_sessions(user_id: int) -> list:
    """Возвращает список сессий, которыми может управлять пользователь"""
    if user_id in SUPER_ADMINS:
        return BUYER_SESSIONS
    
    return [session for session in BUYER_SESSIONS if BUYER_OWNERS.get(session) == user_id]

def create_main_keyboard():
    """Создает главную клавиатуру"""
    builder = InlineKeyboardBuilder()
    builder.add(InlineKeyboardButton(text="📊 Статистика", callback_data="stats"))
    builder.add(InlineKeyboardButton(text="⚙️ Настройки", callback_data="settings"))
    builder.add(InlineKeyboardButton(text="🔄 Сброс трат", callback_data="reset_spending"))
    builder.adjust(1)
    return builder.as_markup()

def create_sessions_keyboard(user_id: int):
    """Создает клавиатуру с сессиями доступными пользователю"""
    builder = InlineKeyboardBuilder()
    user_sessions = get_user_sessions(user_id)
    
    for session in user_sessions:
        builder.add(InlineKeyboardButton(text=session, callback_data=f"session_{session}"))
    builder.add(InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main"))
    builder.adjust(2)
    return builder.as_markup()

def create_session_menu_keyboard(session_name: str):
    """Создает меню для конкретной сессии"""
    builder = InlineKeyboardBuilder()
    builder.add(InlineKeyboardButton(text="📈 Статистика", callback_data=f"session_stats_{session_name}"))
    builder.add(InlineKeyboardButton(text="🎯 Профили закупки", callback_data=f"profiles|{session_name}"))
    builder.add(InlineKeyboardButton(text="🔄 Сбросить траты", callback_data=f"reset_{session_name}"))
    
    config = config_manager.get_config(session_name)
    if config:
        status_text = "✅ Включен" if config.enabled else "❌ Выключен"
        toggle_action = "disable" if config.enabled else "enable"
        builder.add(InlineKeyboardButton(text=status_text, callback_data=f"toggle_{toggle_action}_{session_name}"))
    
    builder.add(InlineKeyboardButton(text="🔙 Назад", callback_data="settings"))
    builder.adjust(2)
    return builder.as_markup()

def create_profiles_keyboard(session_name: str):
    """Создает клавиатуру управления профилями"""
    builder = InlineKeyboardBuilder()
    
    config = config_manager.get_config(session_name)
    if config:
        for profile_name in config.profiles.keys():
            status = "🔸" if config.active_profile == profile_name else "⚪"
            # Используем специальный разделитель |
            builder.add(InlineKeyboardButton(
                text=f"{status} {profile_name}", 
                callback_data=f"profile|{session_name}|{profile_name}"
            ))
        
        if len(config.profiles) < 4:
            builder.add(InlineKeyboardButton(text="➕ Добавить профиль", callback_data=f"add_profile|{session_name}"))
    
    builder.add(InlineKeyboardButton(text="🔙 Назад", callback_data=f"session_{session_name}"))
    builder.adjust(1)
    return builder.as_markup()

def create_profile_menu_keyboard(session_name: str, profile_name: str):
    """Создает меню для конкретного профиля"""
    builder = InlineKeyboardBuilder()
    
    config = config_manager.get_config(session_name)
    if config:
        # Кнопка активации профиля
        if config.active_profile != profile_name:
            builder.add(InlineKeyboardButton(
                text="🔸 Активировать", 
                callback_data=f"activate_profile|{session_name}|{profile_name}"
            ))
        
        # Кнопки редактирования стратегий
        builder.add(InlineKeyboardButton(text="1️⃣ Стратегия 1 (Приоритет 1)", callback_data=f"edit_strategy|{session_name}|{profile_name}|1"))
        builder.add(InlineKeyboardButton(text="2️⃣ Стратегия 2 (Приоритет 2)", callback_data=f"edit_strategy|{session_name}|{profile_name}|2"))
        builder.add(InlineKeyboardButton(text="3️⃣ Стратегия 3 (Приоритет 3)", callback_data=f"edit_strategy|{session_name}|{profile_name}|3"))
        builder.add(InlineKeyboardButton(text="4️⃣ Стратегия 4 (Приоритет 4)", callback_data=f"edit_strategy|{session_name}|{profile_name}|4"))
        
        # Кнопка настройки места отправки
        send_text = "📱 Отправка в профиль" if config.profiles[profile_name].send_to_self else "📤 Отправка в канал"
        builder.add(InlineKeyboardButton(text=send_text, callback_data=f"send_settings|{session_name}|{profile_name}"))
        
        # Кнопка удаления (только для не-дефолтных профилей)
        if profile_name != "default":
            builder.add(InlineKeyboardButton(text="🗑 Удалить профиль", callback_data=f"delete_profile|{session_name}|{profile_name}"))
    
    builder.add(InlineKeyboardButton(text="🔙 Назад", callback_data=f"profiles|{session_name}"))
    builder.adjust(1)
    return builder.as_markup()

@dp.message(Command("start"))
async def start_command(message: Message):
    """Обработчик команды /start"""
    if not message.from_user or not is_admin(message.from_user.id):
        await message.answer("❌ У вас нет прав доступа к этому боту")
        return
    
    await message.answer(
        "🎁 <b>Панель управления покупателями подарков</b>\n\n"
        "Добро пожаловать в систему управления автоматической покупкой подарков!\n\n"
        "Выберите действие:",
        reply_markup=create_main_keyboard(),
        parse_mode="HTML"
    )

@dp.callback_query(F.data == "back_to_main")
async def back_to_main(callback: CallbackQuery):
    """Возврат к главному меню"""
    if callback.message and not isinstance(callback.message, InaccessibleMessage):
        try:
            await callback.message.edit_text(
                "🎁 <b>Панель управления покупателями подарков</b>\n\n"
                "Добро пожаловать в систему управления автоматической покупкой подарков!\n\n"
                "Выберите действие:",
                reply_markup=create_main_keyboard(),
                parse_mode="HTML"
            )
        except Exception as e:
            logger.error(f"Ошибка при редактировании сообщения: {e}")
            # Попробуем без форматирования
            try:
                await callback.message.edit_text(
                    "🎁 Панель управления покупателями подарков\n\n"
                    "Добро пожаловать в систему управления автоматической покупкой подарков!\n\n"
                    "Выберите действие:",
                    reply_markup=create_main_keyboard()
                )
            except Exception:
                pass

@dp.callback_query(F.data == "stats")
async def show_stats(callback: CallbackQuery):
    """Показывает общую статистику"""
    if not callback.from_user:
        return
    
    user_sessions = get_user_sessions(callback.from_user.id)
    
    if not user_sessions:
        await callback.answer("❌ У вас нет доступа к сессиям")
        return
    
    text = "📊 <b>Статистика ваших покупателей:</b>\n\n"
    
    for session in user_sessions:
        config = config_manager.get_config(session)
        if not config:
            config = config_manager.create_default_config(session)
        
        status = "✅" if config.enabled else "❌"
        session_safe = session.replace('_', '\\_').replace('<', '&lt;').replace('>', '&gt;')
        text += f"{status} <b>{session_safe}</b>\n"
        
        # Получаем активный профиль
        active_profile = config.profiles.get(config.active_profile)
        if active_profile:
            total_spent = sum(s.current_spent for s in active_profile.get_strategies())
            total_limit = sum(s.max_spend for s in active_profile.get_strategies())
            text += f"  💰 Потрачено: {total_spent}/{total_limit} ⭐\n"
            text += f"  🎯 Профиль: {config.active_profile}\n\n"
    
    builder = InlineKeyboardBuilder()
    builder.add(InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main"))
    
    if callback.message and not isinstance(callback.message, InaccessibleMessage):
        try:
            await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
        except Exception as e:
            logger.error(f"Ошибка при редактировании сообщения: {e}")

@dp.callback_query(F.data == "settings")
async def show_settings(callback: CallbackQuery):
    """Показывает настройки"""
    if not callback.from_user:
        return
    
    user_sessions = get_user_sessions(callback.from_user.id)
    
    if not user_sessions:
        await callback.answer("❌ У вас нет доступа к сессиям")
        return
    
    if callback.message and not isinstance(callback.message, InaccessibleMessage):
        try:
            await callback.message.edit_text(
                "⚙️ <b>Настройки покупателей</b>\n\n"
                "Выберите покупателя для настройки:",
                reply_markup=create_sessions_keyboard(callback.from_user.id),
                parse_mode="HTML"
            )
        except Exception as e:
            logger.error(f"Ошибка при редактировании сообщения: {e}")

@dp.callback_query(F.data.startswith("session_"))
async def session_menu(callback: CallbackQuery):
    """Меню для конкретной сессии"""
    if not callback.data or not callback.from_user:
        return
    
    session_name = callback.data.split("_", 1)[1]
    
    # Проверяем доступ
    if not has_access_to_session(callback.from_user.id, session_name):
        await callback.answer("❌ У вас нет доступа к этой сессии")
        return
    
    # Создаем конфигурацию по умолчанию, если её нет
    config = config_manager.get_config(session_name)
    if not config:
        config = config_manager.create_default_config(session_name, callback.from_user.id)
    
    status = "✅ Включен" if config.enabled else "❌ Выключен"
    session_safe = session_name.replace('_', '\\_').replace('<', '&lt;').replace('>', '&gt;')
    
    text = f"⚙️ <b>Настройки для {session_safe}</b>\n\n"
    text += f"Статус: {status}\n"
    text += f"Активный профиль: <b>{config.active_profile}</b>\n\n"
    text += "Выберите действие:"
    
    if callback.message and not isinstance(callback.message, InaccessibleMessage):
        try:
            await callback.message.edit_text(
                text,
                reply_markup=create_session_menu_keyboard(session_name),
                parse_mode="HTML"
            )
        except Exception as e:
            logger.error(f"Ошибка при редактировании сообщения session_menu: {e}")
            logger.error(f"Ошибка при редактировании сообщения: {e}")

@dp.callback_query(F.data.startswith("profiles|"))
async def show_profiles(callback: CallbackQuery):
    """Показывает профили для сессии"""
    if not callback.data or not callback.from_user:
        return
    
    # Очищаем контекст пользователя
    if callback.from_user.id in user_contexts:
        del user_contexts[callback.from_user.id]
    
    # Формат: profiles|{session_name}
    session_name = callback.data.split("|")[1]
    
    # Проверяем доступ
    if not has_access_to_session(callback.from_user.id, session_name):
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
    
    if callback.message and not isinstance(callback.message, InaccessibleMessage):
        try:
            await callback.message.edit_text(
                text,
                reply_markup=create_profiles_keyboard(session_name),
                parse_mode="HTML"
            )
        except Exception as e:
            logger.error(f"Ошибка при редактировании сообщения: {e}")

@dp.callback_query(F.data.startswith("profile|"))
async def show_profile_menu(callback: CallbackQuery):
    """Показывает меню для конкретного профиля"""
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
    if not has_access_to_session(callback.from_user.id, session_name):
        await callback.answer("❌ У вас нет доступа к этой сессии")
        return
    
    config = config_manager.get_config(session_name)
    if not config or profile_name not in config.profiles:
        await callback.answer("❌ Профиль не найден")
        return
    
    profile = config.profiles[profile_name]
    session_safe = session_name.replace('_', '\\_').replace('<', '&lt;').replace('>', '&gt;')
    
    text = f"🎯 <b>Профиль \"{profile_name}\" для {session_safe}</b>\n\n"
    text += f"Статус: {'🔸 Активен' if config.active_profile == profile_name else '⚪ Не активен'}\n"
    text += f"Отправка: {'📱 В профиль' if profile.send_to_self else f'📤 В канал {profile.target_channel_id}'}\n\n"
    text += "<b>Стратегии:</b>\n"
    
    for i, strategy in enumerate(profile.get_strategies()):
        remaining = strategy.max_spend - strategy.current_spent
        text += f"<b>Стратегия {i + 1}</b> (Приоритет: {strategy.priority})\n"
        text += f"  💰 Диапазон: {strategy.min_price}-{strategy.max_price} ⭐\n"
        text += f"  💳 Лимит: {strategy.max_spend} ⭐\n"
        text += f"  📊 Потрачено: {strategy.current_spent} ⭐\n"
        text += f"  🔋 Остается: {remaining} ⭐\n\n"
    
    if callback.message and not isinstance(callback.message, InaccessibleMessage):
        try:
            await callback.message.edit_text(
                text,
                reply_markup=create_profile_menu_keyboard(session_name, profile_name),
                parse_mode="HTML"
            )
        except Exception as e:
            logger.error(f"Ошибка при редактировании сообщения: {e}")

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
    if not has_access_to_session(callback.from_user.id, session_name):
        await callback.answer("❌ У вас нет доступа к этой сессии")
        return
    
    try:
        success = config_manager.set_active_profile(session_name, profile_name, callback.from_user.id)
        
        if success:
            await callback.answer(f"✅ Профиль '{profile_name}' активирован")
            
            # Обновляем меню профиля напрямую
            if callback.message and not isinstance(callback.message, InaccessibleMessage):
                try:
                    config = config_manager.get_config(session_name)
                    if config and profile_name in config.profiles:
                        profile = config.profiles[profile_name]
                        session_safe = session_name.replace('_', '\\_').replace('<', '&lt;').replace('>', '&gt;')
                        
                        text = f"🎯 <b>Профиль \"{profile_name}\" для {session_safe}</b>\n\n"
                        text += f"Статус: {'🔸 Активен' if config.active_profile == profile_name else '⚪ Не активен'}\n"
                        text += f"Отправка: {'📱 В профиль' if profile.send_to_self else f'📤 В канал {profile.target_channel_id}'}\n\n"
                        text += "<b>Стратегии:</b>\n"
                        
                        for i, strategy in enumerate(profile.get_strategies()):
                            remaining = strategy.max_spend - strategy.current_spent
                            text += f"<b>Стратегия {i + 1}</b> (Приоритет: {strategy.priority})\n"
                            text += f"  💰 Диапазон: {strategy.min_price}-{strategy.max_price} ⭐\n"
                            text += f"  💳 Лимит: {strategy.max_spend} ⭐\n"
                            text += f"  📊 Потрачено: {strategy.current_spent} ⭐\n"
                            text += f"  🔋 Остается: {remaining} ⭐\n\n"
                        
                        await callback.message.edit_text(
                            text, 
                            reply_markup=create_profile_menu_keyboard(session_name, profile_name), 
                            parse_mode="HTML"
                        )
                except Exception as edit_error:
                    logger.error(f"Ошибка при обновлении меню профиля: {edit_error}")
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
    if not has_access_to_session(callback.from_user.id, session_name):
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
    
    if callback.message and not isinstance(callback.message, InaccessibleMessage):
        try:
            await callback.message.edit_text(
                text,
                reply_markup=builder.as_markup(),
                parse_mode="HTML"
            )
        except Exception as e:
            logger.error(f"Ошибка при редактировании сообщения: {e}")

@dp.callback_query(F.data.startswith("delete_profile|"))
async def delete_profile_confirm(callback: CallbackQuery):
    """Подтверждение удаления профиля"""
    if not callback.data or not callback.from_user:
        return
    
    # Формат: delete_profile|{session_name}|{profile_name}
    parts = callback.data.split("|")
    if len(parts) < 3:
        return
    
    session_name = parts[1]
    profile_name = parts[2]
    
    # Проверяем доступ
    if not has_access_to_session(callback.from_user.id, session_name):
        await callback.answer("❌ У вас нет доступа к этой сессии")
        return
    
    text = f"⚠️ <b>Подтверждение удаления</b>\n\n"
    text += f"Вы действительно хотите удалить профиль '<b>{profile_name}</b>'?\n\n"
    text += "❗ Это действие нельзя отменить!"
    
    builder = InlineKeyboardBuilder()
    builder.add(InlineKeyboardButton(text="✅ Да, удалить", callback_data=f"confirm_delete|{session_name}|{profile_name}"))
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
    if not has_access_to_session(callback.from_user.id, session_name):
        await callback.answer("❌ У вас нет доступа к этой сессии")
        return
    
    try:
        success = config_manager.delete_profile(session_name, profile_name, callback.from_user.id)
        
        if success:
            await callback.answer(f"✅ Профиль '{profile_name}' удален")
            
            # Создаем новый CallbackQuery для перехода к списку профилей
            if callback.message and not isinstance(callback.message, InaccessibleMessage):
                try:
                    await callback.message.edit_text(
                        f"🎯 <b>Профили закупки для {session_name}</b>\n\nВыберите профиль для настройки:",
                        reply_markup=create_profiles_keyboard(session_name),
                        parse_mode="HTML"
                    )
                except Exception as edit_error:
                    logger.error(f"Ошибка при обновлении сообщения: {edit_error}")
        else:
            await callback.answer(f"❌ Не удалось удалить профиль '{profile_name}'")
    
    except Exception as e:
        logger.error(f"Ошибка при удалении профиля: {e}")
        error_msg = str(e)[:50] + "..." if len(str(e)) > 50 else str(e)
        await callback.answer(f"❌ Ошибка: {error_msg}")

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
    if not has_access_to_session(callback.from_user.id, session_name):
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
    
    # Устанавливаем контекст
    user_contexts[callback.from_user.id] = {
        'waiting_for': 'strategy_params',
        'session_name': session_name,
        'profile_name': profile_name,
        'strategy_index': strategy_index
    }
    
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
    text += "📝 Введите новые параметры в формате:\n"
    text += "<code>мин_цена макс_цена лимит_трат</code>\n\n"
    text += "Например: <code>1 10 100</code>"
    
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
            logger.error(f"Ошибка при редактировании сообщения: {e}")

@dp.callback_query(F.data.startswith("session_stats_"))
async def session_stats(callback: CallbackQuery):
    """Показывает статистику для конкретной сессии"""
    if not callback.data or not callback.from_user:
        return
    
    session_name = callback.data.split("_", 2)[2]
    
    # Проверяем доступ
    if not has_access_to_session(callback.from_user.id, session_name):
        await callback.answer("❌ У вас нет доступа к этой сессии")
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
    if not callback.data or not callback.from_user:
        return
    
    # Формат: toggle_{action}_{session_name}
    parts = callback.data.split("_", 2)
    if len(parts) < 3:
        return
    
    action = parts[1]  # enable или disable
    session_name = parts[2]
    
    # Проверяем доступ
    if not has_access_to_session(callback.from_user.id, session_name):
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
    
    # Обновляем меню
    await session_menu(callback)

@dp.callback_query(F.data.startswith("reset_"))
async def reset_session_spending(callback: CallbackQuery):
    """Сбрасывает траты для сессии"""
    if not callback.data or not callback.from_user:
        return
    
    session_name = callback.data.split("_", 1)[1]
    
    # Проверяем доступ
    if not has_access_to_session(callback.from_user.id, session_name):
        await callback.answer("❌ У вас нет доступа к этой сессии")
        return
    
    config = config_manager.get_config(session_name)
    if not config:
        await callback.answer("❌ Конфигурация не найдена")
        return
    
    config.reset_daily_spending()
    config_manager.set_config(session_name, config)
    
    await callback.answer(f"✅ Траты для {session_name} сброшены")
    
    # Показываем статистику сессии напрямую
    if callback.message and not isinstance(callback.message, InaccessibleMessage):
        try:
            session_safe = session_name.replace('_', '\\_').replace('<', '&lt;').replace('>', '&gt;')
            
            text = f"📊 <b>Статистика для {session_safe}</b>\n\n"
            text += f"Статус: {'✅ Включен' if config.enabled else '❌ Выключен'}\n"
            text += f"Активный профиль: <b>{config.active_profile}</b>\n\n"
            
            active_profile = config.profiles.get(config.active_profile)
            if active_profile:
                text += "<b>Стратегии активного профиля:</b>\n"
                for i, strategy in enumerate(active_profile.get_strategies()):
                    remaining = strategy.max_spend - strategy.current_spent
                    text += f"<b>Стратегия {i + 1}</b>\n"
                    text += f"  💰 {strategy.min_price}-{strategy.max_price} ⭐\n"
                    text += f"  📊 {strategy.current_spent}/{strategy.max_spend} ⭐\n"
                    text += f"  🔋 Остается: {remaining} ⭐\n\n"
            
            builder = InlineKeyboardBuilder()
            builder.add(InlineKeyboardButton(text="🔙 Назад", callback_data=f"session_{session_name}"))
            
            await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
        except Exception as edit_error:
            logger.error(f"Ошибка при обновлении статистики: {edit_error}")

@dp.callback_query(F.data == "reset_spending")
async def reset_all_spending(callback: CallbackQuery):
    """Сбрасывает траты для всех сессий"""
    if not callback.from_user:
        return
    
    user_sessions = get_user_sessions(callback.from_user.id)
    
    for session_name in user_sessions:
        config = config_manager.get_config(session_name)
        if config:
            config.reset_daily_spending()
            config_manager.set_config(session_name, config)
    
    await callback.answer("✅ Траты для всех ваших сессий сброшены")
    await show_stats(callback)

@dp.message()
async def handle_text_input(message: Message):
    """Обработка текстового ввода"""
    if not message.from_user or not message.text:
        return
    
    user_id = message.from_user.id
    
    # Проверяем, ждем ли мы ввод от этого пользователя
    if user_id not in user_contexts:
        return
    
    context = user_contexts[user_id]
    
    if context.get('waiting_for') == 'profile_name':
        await handle_profile_name_input(message, context)
    elif context.get('waiting_for') == 'strategy_params':
        await handle_strategy_params_input(message, context)
    elif context.get('waiting_for') == 'channel_id':
        await handle_channel_id_input(message, context)

async def handle_profile_name_input(message: Message, context: dict):
    """Обработка ввода имени профиля"""
    if not message.text or not message.from_user:
        return
    
    profile_name = message.text.strip()
    session_name = context['session_name']
    user_id = message.from_user.id
    
    # Проверяем доступ
    if not has_access_to_session(user_id, session_name):
        await message.answer("❌ У вас нет доступа к этой сессии")
        return
    
    # Валидация имени
    if not profile_name or len(profile_name) > 50:
        await message.answer("❌ Имя профиля должно содержать от 1 до 50 символов")
        return
    
    # Проверяем допустимые символы
    if not re.match(r'^[a-zA-Z0-9_-]+$', profile_name):
        await message.answer("❌ Имя профиля может содержать только буквы, цифры, '_' и '-'")
        return
    
    # Создаем профиль
    try:
        success = config_manager.create_profile(session_name, profile_name, user_id)
        
        if success:
            await message.answer(f"✅ Профиль '{profile_name}' создан")
            
            # Создаем клавиатуру для перехода к профилю
            builder = InlineKeyboardBuilder()
            builder.add(InlineKeyboardButton(text="🎯 Перейти к профилю", callback_data=f"profile|{session_name}|{profile_name}"))
            builder.add(InlineKeyboardButton(text="🔙 К списку профилей", callback_data=f"profiles|{session_name}"))
            
            await message.answer(
                f"Профиль '{profile_name}' успешно создан с настройками по умолчанию.",
                reply_markup=builder.as_markup()
            )
        else:
            # Дополнительная диагностика
            config = config_manager.get_config(session_name)
            if not config:
                await message.answer(f"❌ Ошибка: конфигурация для сессии '{session_name}' не найдена")
            elif len(config.profiles) >= 4:
                await message.answer(f"❌ Ошибка: достигнут лимит профилей (максимум 4). Текущие профили: {list(config.profiles.keys())}")
            elif profile_name in config.profiles:
                await message.answer(f"❌ Ошибка: профиль с именем '{profile_name}' уже существует")
            elif not config_manager.has_access(session_name, user_id):
                await message.answer(f"❌ Ошибка: нет доступа к сессии '{session_name}' для пользователя {user_id}")
            else:
                await message.answer(f"❌ Неизвестная ошибка при создании профиля '{profile_name}' для сессии '{session_name}'")
    
    except Exception as e:
        logger.error(f"Ошибка при создании профиля: {e}")
        error_msg = str(e)[:50] + "..." if len(str(e)) > 50 else str(e)
        await message.answer(f"❌ Ошибка: {error_msg}")
    
    # Очищаем контекст
    if user_id in user_contexts:
        del user_contexts[user_id]

async def handle_strategy_params_input(message: Message, context: dict):
    """Обработка ввода параметров стратегии"""
    if not message.text or not message.from_user:
        return
    
    user_id = message.from_user.id
    session_name = context['session_name']
    profile_name = context['profile_name']
    strategy_index = context['strategy_index']
    
    # Проверяем доступ
    if not has_access_to_session(user_id, session_name):
        await message.answer("❌ У вас нет доступа к этой сессии")
        return
    
    # Парсим параметры
    try:
        params = message.text.strip().split()
        if len(params) != 3:
            raise ValueError("Неверное количество параметров")
        
        min_price = int(params[0])
        max_price = int(params[1])
        max_spend = int(params[2])
        
        # Валидация
        if min_price < 1 or max_price < 1 or max_spend < 1:
            raise ValueError("Все параметры должны быть положительными")
        
        if min_price > max_price:
            raise ValueError("Минимальная цена не может быть больше максимальной")
        
        if max_price > 10000 or max_spend > 100000:
            raise ValueError("Слишком большие значения")
        
    except ValueError as e:
        await message.answer(f"❌ Ошибка в параметрах: {e}\n\nФормат: мин_цена макс_цена лимит_трат\nПример: 1 10 100")
        return
    
    # Обновляем стратегию
    from buyers.buyer_config import BuyingStrategy
    
    new_strategy = BuyingStrategy(
        min_price=min_price,
        max_price=max_price,
        max_spend=max_spend,
        priority=strategy_index + 1,  # Приоритет = индекс + 1
        current_spent=0
    )
    
    try:
        success = config_manager.update_profile_strategy(
            session_name, profile_name, strategy_index + 1, new_strategy, user_id
        )
        
        if success:
            await message.answer(f"✅ Стратегия {strategy_index + 1} обновлена")
            
            # Создаем клавиатуру для перехода к профилю
            builder = InlineKeyboardBuilder()
            builder.add(InlineKeyboardButton(text="🎯 Вернуться к профилю", callback_data=f"profile|{session_name}|{profile_name}"))
            
            await message.answer(
                f"Стратегия {strategy_index + 1} успешно обновлена:\n"
                f"💰 Диапазон цен: {min_price}-{max_price} ⭐\n"
                f"💳 Лимит трат: {max_spend} ⭐",
                reply_markup=builder.as_markup()
            )
        else:
            # Дополнительная диагностика
            config = config_manager.get_config(session_name)
            if not config:
                await message.answer(f"❌ Конфигурация для сессии '{session_name}' не найдена")
            elif profile_name not in config.profiles:
                await message.answer(f"❌ Профиль '{profile_name}' не найден")
            elif strategy_index < 0 or strategy_index >= 4:
                await message.answer(f"❌ Неверный индекс стратегии: {strategy_index + 1}")
            elif not config_manager.has_access(session_name, user_id):
                await message.answer(f"❌ Нет доступа к сессии '{session_name}'")
            else:
                await message.answer(f"❌ Неизвестная ошибка при обновлении стратегии {strategy_index + 1}")
    
    except Exception as e:
        logger.error(f"Ошибка при обновлении стратегии: {e}")
        error_msg = str(e)[:100] + "..." if len(str(e)) > 100 else str(e)
        await message.answer(f"❌ Ошибка: {error_msg}")
    
    # Очищаем контекст
    if user_id in user_contexts:
        del user_contexts[user_id]

@dp.callback_query(F.data.startswith("send_settings|"))
async def send_settings_menu(callback: CallbackQuery):
    """Показывает меню настроек отправки подарков"""
    if not callback.data or not callback.from_user:
        return
    
    # Формат: send_settings|{session_name}|{profile_name}
    parts = callback.data.split("|")
    if len(parts) < 3:
        return
    
    session_name = parts[1]
    profile_name = parts[2]
    
    # Проверяем доступ
    if not has_access_to_session(callback.from_user.id, session_name):
        await callback.answer("❌ У вас нет доступа к этой сессии")
        return
    
    config = config_manager.get_config(session_name)
    if not config or profile_name not in config.profiles:
        await callback.answer("❌ Профиль не найден")
        return
    
    profile = config.profiles[profile_name]
    session_safe = session_name.replace('_', '\\_').replace('<', '&lt;').replace('>', '&gt;')
    
    text = f"📤 <b>Настройки отправки подарков</b>\n\n"
    text += f"Профиль: <b>{profile_name}</b>\n"
    text += f"Сессия: <b>{session_safe}</b>\n\n"
    
    if profile.send_to_self:
        text += "📱 <b>Текущий режим:</b> Отправка в собственный профиль\n"
        text += "Подарки будут отправляться вам самому\n\n"
    else:
        text += f"📤 <b>Текущий режим:</b> Отправка в канал\n"
        text += f"ID канала: <code>{profile.target_channel_id}</code>\n\n"
    
    text += "Выберите режим отправки:"
    
    builder = InlineKeyboardBuilder()
    
    # Кнопка переключения в профиль
    if not profile.send_to_self:
        builder.add(InlineKeyboardButton(text="📱 Отправлять в профиль", callback_data=f"set_send_self|{session_name}|{profile_name}"))
    
    # Кнопка переключения в канал
    if profile.send_to_self:
        builder.add(InlineKeyboardButton(text="📤 Отправлять в канал", callback_data=f"set_send_channel|{session_name}|{profile_name}"))
    else:
        builder.add(InlineKeyboardButton(text="✏️ Изменить канал", callback_data=f"set_send_channel|{session_name}|{profile_name}"))
    
    builder.add(InlineKeyboardButton(text="🔙 Назад", callback_data=f"profile|{session_name}|{profile_name}"))
    builder.adjust(1)
    
    if callback.message and not isinstance(callback.message, InaccessibleMessage):
        try:
            await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
        except Exception as e:
            logger.error(f"Ошибка при редактировании сообщения: {e}")

@dp.callback_query(F.data.startswith("set_send_self|"))
async def set_send_to_self(callback: CallbackQuery):
    """Устанавливает отправку подарков в профиль"""
    if not callback.data or not callback.from_user:
        return
    
    # Формат: set_send_self|{session_name}|{profile_name}
    parts = callback.data.split("|")
    if len(parts) < 3:
        return
    
    session_name = parts[1]
    profile_name = parts[2]
    
    # Проверяем доступ
    if not has_access_to_session(callback.from_user.id, session_name):
        await callback.answer("❌ У вас нет доступа к этой сессии")
        return
    
    config = config_manager.get_config(session_name)
    if not config or profile_name not in config.profiles:
        await callback.answer("❌ Профиль не найден")
        return
    
    # Обновляем настройки
    config.profiles[profile_name].send_to_self = True
    config.profiles[profile_name].target_channel_id = 0
    config_manager.set_config(session_name, config)
    
    await callback.answer("✅ Режим изменен: подарки будут отправляться в ваш профиль")
    
    # Возвращаемся к меню профиля напрямую
    if callback.message and not isinstance(callback.message, InaccessibleMessage):
        try:
            profile = config.profiles[profile_name]
            session_safe = session_name.replace('_', '\\_').replace('<', '&lt;').replace('>', '&gt;')
            
            text = f"🎯 <b>Профиль \"{profile_name}\" для {session_safe}</b>\n\n"
            text += f"Статус: {'🔸 Активен' if config.active_profile == profile_name else '⚪ Не активен'}\n"
            text += f"Отправка: {'📱 В профиль' if profile.send_to_self else f'📤 В канал {profile.target_channel_id}'}\n\n"
            text += "<b>Стратегии:</b>\n"
            
            for i, strategy in enumerate(profile.get_strategies()):
                remaining = strategy.max_spend - strategy.current_spent
                text += f"<b>Стратегия {i + 1}</b> (Приоритет: {strategy.priority})\n"
                text += f"  💰 Диапазон: {strategy.min_price}-{strategy.max_price} ⭐\n"
                text += f"  💳 Лимит: {strategy.max_spend} ⭐\n"
                text += f"  📊 Потрачено: {strategy.current_spent} ⭐\n"
                text += f"  🔋 Остается: {remaining} ⭐\n\n"
            
            await callback.message.edit_text(
                text, 
                reply_markup=create_profile_menu_keyboard(session_name, profile_name), 
                parse_mode="HTML"
            )
        except Exception as edit_error:
            logger.error(f"Ошибка при обновлении меню профиля: {edit_error}")

@dp.callback_query(F.data.startswith("set_send_channel|"))
async def set_send_to_channel_prompt(callback: CallbackQuery):
    """Запрашивает ID канала для отправки подарков"""
    if not callback.data or not callback.from_user:
        return
    
    # Формат: set_send_channel|{session_name}|{profile_name}
    parts = callback.data.split("|")
    if len(parts) < 3:
        return
    
    session_name = parts[1]
    profile_name = parts[2]
    
    # Проверяем доступ
    if not has_access_to_session(callback.from_user.id, session_name):
        await callback.answer("❌ У вас нет доступа к этой сессии")
        return
    
    config = config_manager.get_config(session_name)
    if not config or profile_name not in config.profiles:
        await callback.answer("❌ Профиль не найден")
        return
    
    # Устанавливаем контекст
    user_contexts[callback.from_user.id] = {
        'waiting_for': 'channel_id',
        'session_name': session_name,
        'profile_name': profile_name
    }
    
    text = f"📤 <b>Настройка отправки в канал</b>\n\n"
    text += f"Профиль: <b>{profile_name}</b>\n"
    text += f"Сессия: <b>{session_name}</b>\n\n"
    text += "📝 Введите ID канала для отправки подарков:\n\n"
    text += "ℹ️ <b>Как узнать ID канала:</b>\n"
    text += "1. Перешлите любое сообщение из канала боту @userinfobot\n"
    text += "2. Он покажет 'Chat ID' - это и есть нужный ID\n"
    text += "3. ID канала всегда начинается с -100...\n\n"
    text += "Например: <code>-1001234567890</code>"
    
    builder = InlineKeyboardBuilder()
    builder.add(InlineKeyboardButton(text="🔙 Отмена", callback_data=f"send_settings|{session_name}|{profile_name}"))
    
    if callback.message and not isinstance(callback.message, InaccessibleMessage):
        try:
            await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
        except Exception as e:
            logger.error(f"Ошибка при редактировании сообщения: {e}")

async def handle_channel_id_input(message: Message, context: dict):
    """Обработка ввода ID канала"""
    if not message.text or not message.from_user:
        return
    
    channel_id_str = message.text.strip()
    session_name = context['session_name']
    profile_name = context['profile_name']
    user_id = message.from_user.id
    
    # Проверяем доступ
    if not has_access_to_session(user_id, session_name):
        await message.answer("❌ У вас нет доступа к этой сессии")
        return
    
    # Валидация ID канала
    try:
        channel_id = int(channel_id_str)
        
        # Проверяем, что это похоже на ID канала
        if not str(channel_id).startswith('-100'):
            raise ValueError("ID канала должен начинаться с -100")
        
        if len(str(channel_id)) < 10:
            raise ValueError("ID канала слишком короткий")
        
    except ValueError as e:
        await message.answer(f"❌ Неверный формат ID канала: {e}\n\nПример правильного ID: <code>-1001234567890</code>", parse_mode="HTML")
        return
    
    # Обновляем настройки профиля
    try:
        config = config_manager.get_config(session_name)
        if not config or profile_name not in config.profiles:
            await message.answer("❌ Профиль не найден")
            return
        
        config.profiles[profile_name].send_to_self = False
        config.profiles[profile_name].target_channel_id = channel_id
        config_manager.set_config(session_name, config)
        
        await message.answer(f"✅ Канал для отправки подарков установлен: <code>{channel_id}</code>", parse_mode="HTML")
        
        # Создаем клавиатуру для перехода к профилю
        builder = InlineKeyboardBuilder()
        builder.add(InlineKeyboardButton(text="🎯 Перейти к профилю", callback_data=f"profile|{session_name}|{profile_name}"))
        builder.add(InlineKeyboardButton(text="📤 Настройки отправки", callback_data=f"send_settings|{session_name}|{profile_name}"))
        
        await message.answer(
            f"Теперь подарки в профиле '{profile_name}' будут отправляться в канал {channel_id}",
            reply_markup=builder.as_markup()
        )
        
    except Exception as e:
        logger.error(f"Ошибка при установке канала: {e}")
        error_msg = str(e)[:50] + "..." if len(str(e)) > 50 else str(e)
        await message.answer(f"❌ Ошибка: {error_msg}")
    
    # Очищаем контекст
    if user_id in user_contexts:
        del user_contexts[user_id]

# ...existing code...

async def main():
    """Основная функция для запуска бота"""
    logger.info("Запуск бота управления конфигурацией...")
    
    # Создаем папку data если её нет
    os.makedirs("data", exist_ok=True)
    
    try:
        logger.info("Проверка подключения к Telegram API...")
        
        # Пробуем подключиться с таймаутом
        try:
            me = await asyncio.wait_for(bot.get_me(), timeout=10.0)
            logger.info(f"Бот успешно подключен: @{me.username}")
        except asyncio.TimeoutError:
            logger.error("Таймаут при подключении к Telegram API")
            raise
        except Exception as e:
            if "Cannot connect to host api.telegram.org" in str(e) or "Connection reset by peer" in str(e):
                logger.error("❌ Не удается подключиться к Telegram API")
            raise
        
        await dp.start_polling(bot)
    except KeyboardInterrupt:
        logger.info("Бот остановлен пользователем")
    except Exception as e:
        logger.error(f"Критическая ошибка: {e}")
        raise
    finally:
        await bot.session.close()

if __name__ == "__main__":
    asyncio.run(main())
