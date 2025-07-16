"""Бот управления конфигурацией покупателей"""

import asyncio
import os
import sys
import logging
import aiohttp
from typing import Optional

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, InlineKeyboardButton, CallbackQuery, InaccessibleMessage
from aiogram.filters import Command
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.client.session.aiohttp import AiohttpSession

from buyers.buyer_config import BuyerConfigManager, BuyerConfig, BuyingStrategy, BuyingProfile
from app.config import BUYER_SESSIONS, MANAGEMENT_BOT_TOKEN, PROXY_URL, BUYER_OWNERS, ADMIN_USERNAMES, ALLOWED_USERS, USERNAME_ALIASES

from .keyboards import create_main_keyboard
from .callbacks import register_callbacks
from .admin_callbacks import register_strategy_callbacks, register_admin_callbacks
from .text_handlers import register_text_handlers
BOT_TOKEN = MANAGEMENT_BOT_TOKEN

# Создание бота с прокси если настроен
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

config_manager = BuyerConfigManager("data/buyer_configs.json")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def init_default_configs():
    """Создает дефолтные конфигурации"""
    for session_name in BUYER_SESSIONS:
        if not config_manager.get_config(session_name):
            logger.info(f"Создание дефолтной конфигурации для {session_name}")
            config_manager.create_default_config(session_name, owner_id=0)

init_default_configs()
user_contexts = {}

from typing import Optional

def is_admin(user_id: Optional[int] = None, username: Optional[str] = None) -> bool:
    """Проверяет, является ли пользователь администратором"""
    if username and username in ADMIN_USERNAMES:
        return True
    return False

def resolve_username_with_aliases(username: Optional[str]) -> Optional[str]:
    """Возвращает основной username пользователя с учетом aliases"""
    if not username:
        return None
    
    # Если username в основном списке - возвращаем как есть
    if username in ADMIN_USERNAMES or username in ALLOWED_USERS or username in BUYER_OWNERS.values():
        return username
    
    # Ищем среди aliases
    for main_user, aliases in USERNAME_ALIASES.items():
        if username in aliases:
            logger.info(f"🔄 Username '{username}' найден как alias для '{main_user}'")
            return main_user
    
    return username

def has_bot_access(username: Optional[str] = None) -> bool:
    """Проверяет доступ пользователя к боту с поддержкой aliases"""
    if not username:
        logger.warning("❌ Попытка проверки доступа без username")
        return False
    
    # logger.info(f"🔍 Проверка доступа для пользователя: '{username}'")
    
    # Проверяем прямой доступ
    if username in ADMIN_USERNAMES:
        # logger.info(f"✅ Пользователь '{username}' найден в ADMIN_USERNAMES")
        return True
    
    if username in ALLOWED_USERS:
        # logger.info(f"✅ Пользователь '{username}' найден в ALLOWED_USERS")
        return True
    
    if any(owner == username for owner in BUYER_OWNERS.values()):
        # logger.info(f"✅ Пользователь '{username}' найден в BUYER_OWNERS")
        return True
    
    # Проверяем через aliases
    for main_user, aliases in USERNAME_ALIASES.items():
        if username in aliases:
            # logger.info(f"🔄 Username '{username}' найден как alias для '{main_user}'")
            
            if main_user in ADMIN_USERNAMES:
                # logger.info(f"✅ Основной пользователь '{main_user}' в ADMIN_USERNAMES")
                return True
            
            if main_user in ALLOWED_USERS:
                # logger.info(f"✅ Основной пользователь '{main_user}' в ALLOWED_USERS")
                return True
            
            if any(owner == main_user for owner in BUYER_OWNERS.values()):
                # logger.info(f"✅ Основной пользователь '{main_user}' в BUYER_OWNERS")
                return True
    
    logger.warning(f"❌ Пользователь '{username}' НЕ найден ни в одном списке доступа")
    logger.debug(f"📋 ADMIN_USERNAMES: {ADMIN_USERNAMES}")
    logger.debug(f"📋 ALLOWED_USERS: {ALLOWED_USERS}")
    logger.debug(f"📋 BUYER_OWNERS: {list(BUYER_OWNERS.values())}")
    logger.debug(f"📋 USERNAME_ALIASES: {USERNAME_ALIASES}")
    
    return False

def has_access_to_session(username: Optional[str] = None, session_name: Optional[str] = None) -> bool:
    """Проверяет, имеет ли пользователь доступ к управлению сессией с поддержкой aliases"""
    if not session_name or not username:
        logger.warning(f"❌ Неполные данные для проверки доступа к сессии: username='{username}', session='{session_name}'")
        return False
    
    # logger.info(f"🔍 Проверка доступа пользователя '{username}' к сессии '{session_name}'")
        
    # Админы имеют доступ ко всем сессиям
    if username in ADMIN_USERNAMES:
        # logger.info(f"✅ Пользователь '{username}' - администратор, доступ к сессии '{session_name}' разрешен")
        return True
    
    # Проверяем прямое владение сессией
    session_owner = BUYER_OWNERS.get(session_name)
    if session_owner == username:
        # logger.info(f"✅ Пользователь '{username}' - владелец сессии '{session_name}'")
        return True
    
    # Проверяем через aliases
    for main_user, aliases in USERNAME_ALIASES.items():
        if username in aliases:
            # logger.info(f"🔄 Username '{username}' найден как alias для '{main_user}'")
            
            # Проверяем админские права основного пользователя
            if main_user in ADMIN_USERNAMES:
                # logger.info(f"✅ Основной пользователь '{main_user}' - администратор")
                return True
            
            # Проверяем владение сессией основным пользователем
            if session_owner == main_user:
                # logger.info(f"✅ Основной пользователь '{main_user}' - владелец сессии '{session_name}'")
                return True
    
    logger.warning(f"❌ Пользователь '{username}' НЕ имеет доступа к сессии '{session_name}' (владелец: '{session_owner}')")
    return False

def get_user_sessions(username: Optional[str] = None) -> list:
    """Возвращает список сессий, которыми может управлять пользователь с поддержкой aliases"""
    if not username:
        logger.warning("❌ Попытка получения сессий без username")
        return []
    
    # logger.info(f"🔍 Получение списка сессий для пользователя '{username}'")
        
    # Админы имеют доступ ко всем сессиям
    if username in ADMIN_USERNAMES:
        # logger.info(f"✅ Пользователь '{username}' - администратор, возвращаем все сессии")
        return BUYER_SESSIONS
    
    sessions = []
    
    # Проверяем прямое владение сессиями
    for session in BUYER_SESSIONS:
        if BUYER_OWNERS.get(session) == username:
            sessions.append(session)
            # logger.info(f"✅ Добавлена сессия '{session}' (прямое владение)")
    
    # Проверяем через aliases
    for main_user, aliases in USERNAME_ALIASES.items():
        if username in aliases:
            # logger.info(f"🔄 Username '{username}' найден как alias для '{main_user}'")
            
            # Проверяем админские права основного пользователя
            if main_user in ADMIN_USERNAMES:
                # logger.info(f"✅ Основной пользователь '{main_user}' - администратор, возвращаем все сессии")
                return BUYER_SESSIONS
            
            # Добавляем сессии основного пользователя
            for session in BUYER_SESSIONS:
                if BUYER_OWNERS.get(session) == main_user and session not in sessions:
                    sessions.append(session)
                    # logger.info(f"✅ Добавлена сессия '{session}' (через alias для '{main_user}')")
    
    # logger.info(f"📋 Итого сессий для пользователя '{username}': {sessions}")
    return sessions


def check_user_access(user, session_name: Optional[str] = None) -> bool:
    """Проверяет доступ пользователя к сессии или общие права админа"""
    if session_name:
        return has_access_to_session(user.username, session_name)
    else:
        return is_admin(user_id=user.id, username=user.username)


def check_admin_access(user) -> bool:
    """Проверяет права администратора"""
    return is_admin(user_id=user.id, username=user.username)


def check_bot_access(user) -> bool:
    """Проверяет общий доступ к боту с улучшенным логированием"""
    if not user:
        logger.warning("❌ Попытка проверки доступа без объекта пользователя")
        return False
    
    # logger.info(f"🔍 Проверка доступа к боту для пользователя ID: {user.id}, username: '{user.username}', first_name: '{user.first_name}', last_name: '{user.last_name}'")
    
    result = has_bot_access(user.username)
    
    if result:
        # logger.info(f"✅ Доступ к боту РАЗРЕШЕН для пользователя '{user.username}' (ID: {user.id})")
        pass
    else:
        logger.warning(f"❌ Доступ к боту ЗАПРЕЩЕН для пользователя '{user.username}' (ID: {user.id})")
    
    return result


@dp.message(Command("start"))
async def start_command(message: Message):
    """Обработчик команды /start"""
    if not message.from_user:
        logger.error("❌ Получена команда /start без информации о пользователе")
        await message.answer("❌ У вас нет прав доступа к этому боту")
        return
    
    # logger.info(f"📨 Получена команда /start от пользователя: ID={message.from_user.id}, username='{message.from_user.username}', name='{message.from_user.first_name} {message.from_user.last_name or ''}'")
    
    if not check_bot_access(message.from_user):
        logger.warning(f"🚫 Доступ запрещен для пользователя '{message.from_user.username}' (ID: {message.from_user.id})")
        await message.answer("❌ У вас нет прав доступа к этому боту")
        return
    
    # logger.info(f"🎉 Успешный вход пользователя '{message.from_user.username}' (ID: {message.from_user.id})")
    
    await message.answer(
        "🎁 <b>Панель управления покупателями подарков</b>\n\n"
        "Добро пожаловать в систему управления автоматической покупкой подарков!\n\n"
        "Выберите действие:",
        reply_markup=create_main_keyboard(),
        parse_mode="HTML"
    )


async def main():
    """Основная функция для запуска бота"""
    logger.info("Запуск бота управления конфигурацией...")
    
    # Создаем папку data если её нет
    os.makedirs("data", exist_ok=True)
    
    # Регистрируем обработчики
    register_callbacks(dp, config_manager, user_contexts, has_access_to_session, get_user_sessions)
    register_strategy_callbacks(dp, config_manager, user_contexts, has_access_to_session)
    register_admin_callbacks(dp, config_manager, has_access_to_session)
    register_text_handlers(dp, config_manager, user_contexts, has_access_to_session)
    
    try:
        await dp.start_polling(bot)
    except KeyboardInterrupt:
        logger.info("Бот остановлен пользователем")
    except Exception as e:
        logger.error(f"Критическая ошибка: {e}")
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())

# Экспорт функции main для импорта из других модулей
__all__ = ['main']