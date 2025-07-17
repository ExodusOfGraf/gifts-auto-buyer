"""
Модуль с обработчиками текстового ввода для бота управления конфигурацией
"""

import re
import logging
from aiogram import F
from aiogram.types import Message, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from buyers.buyer_config import BuyingStrategy

logger = logging.getLogger(__name__)


def register_text_handlers(dp, config_manager, user_contexts, has_access_to_session):
    """Регистрирует обработчики текстового ввода"""
    
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
            await handle_profile_name_input(message, context, config_manager, user_contexts, has_access_to_session)
        elif context.get('waiting_for') == 'strategy_params':
            await handle_strategy_params_input(message, context, config_manager, user_contexts, has_access_to_session)
        elif context.get('waiting_for') == 'strategy_channel_id':
            await handle_strategy_channel_id_input(message, context, config_manager, user_contexts, has_access_to_session)


async def handle_profile_name_input(message: Message, context: dict, config_manager, user_contexts, has_access_to_session):
    """Обработка ввода имени профиля"""
    if not message.text or not message.from_user:
        return
    
    profile_name = message.text.strip()
    session_name = context['session_name']
    user_id = message.from_user.id
    
    # Проверяем доступ
    if not has_access_to_session(message.from_user.username, session_name):
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


async def handle_strategy_params_input(message: Message, context: dict, config_manager, user_contexts, has_access_to_session):
    """Обработка ввода параметров стратегии"""
    if not message.text or not message.from_user:
        return
    
    user_id = message.from_user.id
    session_name = context['session_name']
    profile_name = context['profile_name']
    strategy_index = context['strategy_index']
    
    # Проверяем доступ
    if not has_access_to_session(message.from_user.username, session_name):
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
        
        if max_price > 100000 or max_spend > 100000:
            raise ValueError("Слишком большие значения")
        
    except ValueError as e:
        await message.answer(f"❌ Ошибка в параметрах: {e}\n\nФормат: мин_цена макс_цена лимит_трат\nПример: 1 10 100")
        return
    
    # Обновляем стратегию, сохраняя настройки отправки
    config = config_manager.get_config(session_name)
    if not config or profile_name not in config.profiles:
        await message.answer("❌ Профиль не найден")
        return
    
    current_strategy = config.profiles[profile_name].get_strategies()[strategy_index]
    
    new_strategy = BuyingStrategy(
        min_price=min_price,
        max_price=max_price,
        max_spend=max_spend,
        priority=strategy_index + 1,  # Приоритет = индекс + 1
        current_spent=current_strategy.current_spent,  # Сохраняем текущие траты
        send_to_self=current_strategy.send_to_self,  # Сохраняем настройки отправки
        target_channel_id=current_strategy.target_channel_id  # Сохраняем настройки отправки
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
                await message.answer(f"❌ Ошибка: конфигурация для сессии '{session_name}' не найдена")
            elif profile_name not in config.profiles:
                await message.answer(f"❌ Ошибка: профиль '{profile_name}' не найден")
            elif strategy_index < 0 or strategy_index >= 4:
                await message.answer(f"❌ Ошибка: неверный индекс стратегии {strategy_index}")
            elif not config_manager.has_access(session_name, user_id):
                await message.answer(f"❌ Ошибка: нет доступа к сессии '{session_name}' для пользователя {user_id}")
            else:
                await message.answer(f"❌ Неизвестная ошибка при обновлении стратегии {strategy_index + 1}")
    
    except Exception as e:
        logger.error(f"Ошибка при обновлении стратегии: {e}")
        error_msg = str(e)[:100] + "..." if len(str(e)) > 100 else str(e)
        await message.answer(f"❌ Ошибка: {error_msg}")
    
    # Очищаем контекст
    if user_id in user_contexts:
        del user_contexts[user_id]


async def handle_strategy_channel_id_input(message: Message, context: dict, config_manager, user_contexts, has_access_to_session):
    """Обрабатывает ввод ID канала для стратегии."""
    if not message.text or not message.from_user:
        return

    channel_id_str = message.text.strip()
    session_name = context['session_name']
    profile_name = context['profile_name']
    strategy_num = context['strategy_num']
    user_id = message.from_user.id

    try:
        channel_id = int(channel_id_str)
    except ValueError:
        await message.answer("❌ ID канала должен быть числом. Пример: -1234567890")
        return

    # Проверяем формат ID канала
    if channel_id > 0:
        await message.answer(
            "❌ ID канала должен быть отрицательным числом!\n\n"
            "• Для приватных каналов: начинается с -100 (например: -1001234567890)\n"
            "• Для групп: начинается с - (например: -1234567890)\n\n"
            "💡 Узнать правильный ID можно отправив сообщение из канала в бота @userinfobot"
        )
        return


    config = config_manager.get_config(session_name)
    if not config or profile_name not in config.profiles:
        await message.answer("❌ Профиль не найден")
        return

    profile = config.profiles[profile_name]
    strategies = profile.get_strategies()
    strategies[strategy_num - 1].send_to_self = False
    strategies[strategy_num - 1].target_channel_id = channel_id
    config_manager.set_config(session_name, config)

    await message.answer(
        f"✅ Стратегия {strategy_num}: канал установлен на <code>{channel_id}</code>.\n\n"
        f"⚠️ <b>Важно:</b> Убедитесь, что аккаунт покупателя добавлен в этот канал и может отправлять сообщения!",
        parse_mode="HTML"
    )

    if user_id in user_contexts:
        del user_contexts[user_id]

    # Создаем клавиатуру для возврата в меню настроек стратегии
    builder = InlineKeyboardBuilder()
    builder.button(text="📤 Настройки отправки", callback_data=f"edit_strategy_send|{session_name}|{profile_name}|{strategy_num}")
    builder.button(text="🎯 К профилю", callback_data=f"profile|{session_name}|{profile_name}")
    builder.adjust(1)
    
    await message.answer(
        f"Канал для Стратегии {strategy_num} успешно настроен.",
        reply_markup=builder.as_markup()
    )
