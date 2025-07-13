"""
Основной модуль бота управления конфигурацией покупателей подарков
"""

import asyncio
import os
import sys
import logging
import aiohttp

# Добавляем родительскую папку в путь для импорта
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, InlineKeyboardButton, CallbackQuery, InaccessibleMessage
from aiogram.filters import Command
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.client.session.aiohttp import AiohttpSession

from buyers.buyer_config import BuyerConfigManager, BuyerConfig, BuyingStrategy, BuyingProfile
from app.config import BUYER_SESSIONS, MANAGEMENT_BOT_TOKEN, ADMIN_USER_ID, PROXY_URL, BUYER_OWNERS, SUPER_ADMINS, ADMIN_USERNAMES

# Импорты модулей бота
from .keyboards import create_main_keyboard
from .callbacks import register_callbacks
from .admin_callbacks import register_strategy_callbacks, register_admin_callbacks
from .text_handlers import register_text_handlers

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

from typing import Optional

def is_admin(user_id: Optional[int] = None, username: Optional[str] = None) -> bool:
    """Проверяет, является ли пользователь администратором"""
    # Проверяем по username (новая система)
    if username and username in ADMIN_USERNAMES:
        return True
    
    # Проверяем по user_id (совместимость)
    if user_id and (user_id == ADMIN_USER_ID or user_id in SUPER_ADMINS):
        return True
    
    return False

def has_access_to_session(username: Optional[str] = None, session_name: Optional[str] = None) -> bool:
    """Проверяет, имеет ли пользователь доступ к управлению сессией"""
    if not session_name or not username:
        return False
        
    # Суперадмины имеют доступ ко всем сессиям
    if username in SUPER_ADMINS:
        return True
    
    # Админы из вайтлиста имеют доступ ко всем сессиям
    if username in ADMIN_USERNAMES:
        return True
    
    # Проверяем права владельца по username
    if BUYER_OWNERS.get(session_name) == username:
        return True
    
    return False

def get_user_sessions(username: Optional[str] = None) -> list:
    """Возвращает список сессий, которыми может управлять пользователь"""
    if not username:
        return []
        
    # Суперадмины и админы из вайтлиста имеют доступ ко всем сессиям
    if username in SUPER_ADMINS or username in ADMIN_USERNAMES:
        return BUYER_SESSIONS
    
    # Проверяем права по username
    return [session for session in BUYER_SESSIONS if BUYER_OWNERS.get(session) == username]


def check_user_access(user, session_name: Optional[str] = None) -> bool:
    """Проверяет доступ пользователя к сессии или общие права админа"""
    if session_name:
        return has_access_to_session(user.username, session_name)
    else:
        return is_admin(user_id=user.id, username=user.username)


def check_admin_access(user) -> bool:
    """Проверяет права администратора"""
    return is_admin(user_id=user.id, username=user.username)


@dp.message(Command("start"))
async def start_command(message: Message):
    """Обработчик команды /start"""
    if not message.from_user or not check_admin_access(message.from_user):
        await message.answer("❌ У вас нет прав доступа к этому боту")
        return
    
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