import asyncio
import logging
import os
import sys

# Добавляем родительскую папку в путь для импорта
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, InlineKeyboardButton, CallbackQuery, InaccessibleMessage
from aiogram.filters import Command
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.client.session.aiohttp import AiohttpSession
import aiohttp

from buyers.buyer_config import BuyerConfigManager, BuyerConfig, BuyingStrategy
from app.config import BUYER_SESSIONS, MANAGEMENT_BOT_TOKEN, ADMIN_USER_ID, PROXY_URL

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

def is_admin(user_id: int) -> bool:
    """Проверяет, является ли пользователь администратором"""
    return user_id == ADMIN_USER_ID

def create_main_keyboard():
    """Создает главную клавиатуру"""
    builder = InlineKeyboardBuilder()
    builder.add(InlineKeyboardButton(text="📊 Статистика", callback_data="stats"))
    builder.add(InlineKeyboardButton(text="⚙️ Настройки", callback_data="settings"))
    builder.add(InlineKeyboardButton(text="🔄 Сброс трат", callback_data="reset_spending"))
    builder.adjust(1)
    return builder.as_markup()

def create_sessions_keyboard():
    """Создает клавиатуру с сессиями"""
    builder = InlineKeyboardBuilder()
    for session in BUYER_SESSIONS:
        builder.add(InlineKeyboardButton(text=session, callback_data=f"session_{session}"))
    builder.add(InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main"))
    builder.adjust(2)
    return builder.as_markup()

def create_session_menu_keyboard(session_name: str):
    """Создает меню для конкретной сессии"""
    builder = InlineKeyboardBuilder()
    builder.add(InlineKeyboardButton(text="📈 Статистика", callback_data=f"session_stats_{session_name}"))
    builder.add(InlineKeyboardButton(text="🔄 Сбросить траты", callback_data=f"reset_{session_name}"))
    
    config = config_manager.get_config(session_name)
    if config:
        status_text = "✅ Включен" if config.enabled else "❌ Выключен"
        toggle_action = "disable" if config.enabled else "enable"
        builder.add(InlineKeyboardButton(text=status_text, callback_data=f"toggle_{toggle_action}_{session_name}"))
    
    builder.add(InlineKeyboardButton(text="🔙 Назад", callback_data="settings"))
    builder.adjust(2)
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
    text = "📊 <b>Общая статистика по всем покупателям:</b>\n\n"
    
    for session in BUYER_SESSIONS:
        stats = config_manager.get_spending_stats(session)
        if not stats:
            config_manager.create_default_config(session)
            stats = config_manager.get_spending_stats(session)
        
        status = "✅" if stats['enabled'] else "❌"
        # Экранируем специальные символы для HTML
        session_safe = session.replace('_', '\\_').replace('<', '&lt;').replace('>', '&gt;')
        text += f"{status} <b>{session_safe}</b>\n"
        
        total_spent = sum(s['current_spent'] for s in stats['strategies'])
        total_limit = sum(s['max_spend'] for s in stats['strategies'])
        
        text += f"  💰 Потрачено: {total_spent}/{total_limit} ⭐\n\n"
    
    builder = InlineKeyboardBuilder()
    builder.add(InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main"))
    
    if callback.message and not isinstance(callback.message, InaccessibleMessage):
        try:
            await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
        except Exception as e:
            logger.error(f"Ошибка при редактировании сообщения: {e}")
            # Попробуем без форматирования
            try:
                text_plain = text.replace('<b>', '').replace('</b>', '').replace('\\_', '_')
                await callback.message.edit_text(text_plain, reply_markup=builder.as_markup())
            except Exception:
                pass

@dp.callback_query(F.data == "settings")
async def show_settings(callback: CallbackQuery):
    """Показывает настройки"""
    if callback.message and not isinstance(callback.message, InaccessibleMessage):
        try:
            await callback.message.edit_text(
                "⚙️ <b>Настройки покупателей</b>\n\n"
                "Выберите покупателя для настройки:",
                reply_markup=create_sessions_keyboard(),
                parse_mode="HTML"
            )
        except Exception as e:
            logger.error(f"Ошибка при редактировании сообщения: {e}")
            # Попробуем без форматирования
            try:
                await callback.message.edit_text(
                    "⚙️ Настройки покупателей\n\n"
                    "Выберите покупателя для настройки:",
                    reply_markup=create_sessions_keyboard()
                )
            except Exception:
                pass

@dp.callback_query(F.data.startswith("session_"))
async def session_menu(callback: CallbackQuery):
    """Меню для конкретной сессии"""
    if not callback.data:
        return
    
    session_name = callback.data.split("_", 1)[1]
    
    # Создаем конфигурацию по умолчанию, если её нет
    config = config_manager.get_config(session_name)
    if not config:
        config = config_manager.create_default_config(session_name)
    
    status = "✅ Включен" if config.enabled else "❌ Выключен"
    
    # Экранируем специальные символы
    session_safe = session_name.replace('_', '\\_').replace('<', '&lt;').replace('>', '&gt;')
    
    text = f"⚙️ <b>Настройки для {session_safe}</b>\n\n"
    text += f"Статус: {status}\n\n"
    text += "Выберите действие:"
    
    if callback.message and not isinstance(callback.message, InaccessibleMessage):
        try:
            await callback.message.edit_text(
                text,
                reply_markup=create_session_menu_keyboard(session_name),
                parse_mode="HTML"
            )
        except Exception as e:
            logger.error(f"Ошибка при редактировании сообщения: {e}")
            # Попробуем без форматирования
            try:
                text_plain = f"⚙️ Настройки для {session_name}\n\nСтатус: {status}\n\nВыберите действие:"
                await callback.message.edit_text(
                    text_plain,
                    reply_markup=create_session_menu_keyboard(session_name)
                )
            except Exception:
                pass

@dp.callback_query(F.data.startswith("session_stats_"))
async def session_stats(callback: CallbackQuery):
    """Показывает статистику для конкретной сессии"""
    if not callback.data:
        return
    
    session_name = callback.data.split("_", 2)[2]
    stats = config_manager.get_spending_stats(session_name)
    
    if not stats:
        await callback.answer("❌ Конфигурация не найдена")
        return
    
    # Экранируем специальные символы
    session_safe = session_name.replace('_', '\\_').replace('<', '&lt;').replace('>', '&gt;')
    
    text = f"📊 <b>Статистика для {session_safe}</b>\n\n"
    text += f"Статус: {'✅ Включен' if stats['enabled'] else '❌ Выключен'}\n\n"
    
    for i, strategy in enumerate(stats['strategies']):
        strategy_obj = BuyingStrategy(
            min_price=int(strategy['price_range'].split('-')[0]),
            max_price=int(strategy['price_range'].split('-')[1]),
            max_spend=strategy['max_spend'],
            priority=strategy['priority'],
            current_spent=strategy['current_spent']
        )
        remaining = strategy_obj.max_spend - strategy_obj.current_spent
        text += f"<b>Стратегия {i + 1}</b> (Приоритет: {strategy_obj.priority})\n"
        text += f"💰 Диапазон цен: {strategy_obj.min_price}-{strategy_obj.max_price} ⭐\n"
        text += f"💳 Лимит трат: {strategy_obj.max_spend} ⭐\n"
        text += f"📊 Потрачено: {strategy_obj.current_spent} ⭐\n"
        text += f"🔋 Остается: {remaining} ⭐\n\n"
    
    builder = InlineKeyboardBuilder()
    builder.add(InlineKeyboardButton(text="🔙 Назад", callback_data=f"session_{session_name}"))
    
    if callback.message and not isinstance(callback.message, InaccessibleMessage):
        try:
            await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
        except Exception as e:
            logger.error(f"Ошибка при редактировании сообщения: {e}")
            # Попробуем без форматирования
            try:
                text_plain = text.replace('<b>', '').replace('</b>', '').replace('\\_', '_')
                await callback.message.edit_text(text_plain, reply_markup=builder.as_markup())
            except Exception:
                pass

@dp.callback_query(F.data.startswith("toggle_"))
async def toggle_session(callback: CallbackQuery):
    """Включает/выключает сессию"""
    if not callback.data:
        return
    
    parts = callback.data.split("_")
    if len(parts) < 3:
        return
    
    action = parts[1]  # enable или disable
    session_name = parts[2]
    
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
    if not callback.data:
        return
    
    session_name = callback.data.split("_", 1)[1]
    config = config_manager.get_config(session_name)
    
    if not config:
        await callback.answer("❌ Конфигурация не найдена")
        return
    
    config.reset_daily_spending()
    config_manager.set_config(session_name, config)
    
    await callback.answer(f"✅ Траты для {session_name} сброшены")
    
    # Перенаправляем на статистику сессии
    if callback.message and not isinstance(callback.message, InaccessibleMessage):
        try:
            # Имитируем callback с нужными данными
            callback.data = f"session_stats_{session_name}"
            await session_stats(callback)
        except Exception as e:
            logger.error(f"Ошибка при показе статистики: {e}")

@dp.callback_query(F.data == "reset_spending")
async def reset_all_spending(callback: CallbackQuery):
    """Сбрасывает траты для всех сессий"""
    for session_name in BUYER_SESSIONS:
        config = config_manager.get_config(session_name)
        if config:
            config.reset_daily_spending()
            config_manager.set_config(session_name, config)
    
    await callback.answer("✅ Траты для всех сессий сброшены")
    await show_stats(callback)

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
                logger.error("🔧 Возможные решения:")
                logger.error("   1. Проверьте интернет-соединение")
                logger.error("   2. Используйте VPN")
                logger.error("   3. Настройте PROXY_URL в app/config.py")
                logger.error("   4. Попробуйте позже - возможны временные проблемы")
                logger.error("")
                logger.error("📝 Система управления конфигурацией недоступна без интернета")
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
