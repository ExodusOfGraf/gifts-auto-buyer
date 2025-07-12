import asyncio
import logging
import os
import sys
from typing import Optional

# Добавляем родительскую папку в путь для импорта
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pyrogram import Client, filters
from pyrogram.handlers import MessageHandler
from pyrogram.errors import FloodWait, RPCError
from app.config import (
    API_ID, API_HASH, BUYER_SESSIONS, TARGET_CHANNEL_ID,
    SLEEP_AFTER_BUY_SECONDS
)
from .buyer_config import BuyerConfig, BuyerConfigManager, BuyingStrategy

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - [%(name)s] - %(levelname)s - %(message)s'
)

# Глобальный менеджер конфигураций
config_manager: Optional[BuyerConfigManager] = None

def parse_gift_data(text: str) -> dict | None:
    try:
        # Ищем начало блока с данными для бота
        if "NEW_GIFT" not in text:
            return None
        
        # Берем только ту часть текста, что идет после NEW_GIFT
        data_block = text.split("NEW_GIFT")[1]
        lines = data_block.strip().split('\n')
        
        data = {} 
        for line in lines:
            if ':' not in line: continue
            key, value = line.split(':', 1)
            data[key.strip()] = value.strip()
        
        data['GIFT_ID'] = int(data['GIFT_ID'])
        data['PRICE'] = int(data['PRICE'])
        
        return data
    except (ValueError, IndexError, KeyError):
        return None

async def get_purchase_parameters(
    client: Client, 
    price: int, 
    manager: BuyerConfigManager
) -> tuple[Optional[BuyerConfig], Optional[BuyingStrategy]]:
    """
    Проверяет конфиг, статус бота, сбрасывает дневные лимиты и выбирает стратегию.
    Возвращает кортеж (конфигурация, стратегия) или (None, None) если покупка невозможна.
    """
    log = logging.getLogger(client.name)
    
    config = manager.get_config(client.name)
    if not config:
        log.warning(f"⚠️ Конфигурация для {client.name} не найдена. Создаем дефолтную.")
        config = manager.create_default_config(client.name, 0)

    if not config.enabled:
        log.info(f"⏸️ Покупатель {client.name} отключен. Пропускаем покупку.")
        return None, None

    if config.should_reset_daily():
        log.info(f"🔄 Сбрасываем ежедневные траты для {client.name}")
        config.reset_daily_spending()
        manager.set_config(client.name, config)

    strategy = config.get_best_strategy(price)
    if not strategy:
        log.info(f"❌ Нет подходящей стратегии для подарка ценой {price} ⭐. Пропускаем.")
        return None, None
    
    log.info(f"✅ Выбрана стратегия: {strategy.min_price}-{strategy.max_price} ⭐ (приоритет {strategy.priority})")
    log.info(f"💳 Лимит стратегии: {strategy.max_spend} ⭐, потрачено: {strategy.current_spent} ⭐")
        
    return config, strategy

async def execute_purchase_loop(
    client: Client, 
    gift_id: int, 
    price: int, 
    strategy: BuyingStrategy, 
    manager: BuyerConfigManager
):
    """
    Выполняет цикл покупки подарков на основе выбранной стратегии.
    """
    log = logging.getLogger(client.name)
    
    try:
        balance = await client.get_stars_balance()
        if balance < price:
            log.warning(f"Недостаточно средств. Баланс: {balance} ⭐, Цена: {price} ⭐")
            return

        # Определяем куда отправлять подарки на основе настроек стратегии
        if strategy.send_to_self:
            chat_id = "me"
            destination_info = "профиль"
        else:
            chat_id = strategy.target_channel_id
            destination_info = f"канал {chat_id}"

        # Вычисляем, сколько подарков можем купить по стратегии
        if price <= 0:
            log.warning(f"Цена подарка некорректна ({price} ⭐). Покупка отменена.")
            return

        max_by_strategy = (strategy.max_spend - strategy.current_spent) // price
        max_by_balance = balance // price
        quantity_to_buy = min(max_by_strategy, max_by_balance)
        
        if quantity_to_buy <= 0:
            log.info(f"Лимит трат по стратегии исчерпан или недостаточно средств. Пропускаем покупку.")
            return
        
        log.info(f"Стратегия: {strategy.min_price}-{strategy.max_price} ⭐ (приоритет {strategy.priority})")
        log.info(f"Баланс: {balance} ⭐. Цена: {price} ⭐. Покупаем {quantity_to_buy} шт.")
        log.info(f"Потрачено по стратегии: {strategy.current_spent}/{strategy.max_spend} ⭐")
        log.info(f"Место отправки: {destination_info}")
        
        successful_purchases = 0
        for i in range(quantity_to_buy):
            try:
                log.info(f"Попытка покупки #{i + 1}/{quantity_to_buy}...")
                await client.send_gift(chat_id=chat_id, gift_id=gift_id)
                
                manager.update_purchase(client.name, price)
                successful_purchases += 1
                
                log.info(f"✅ УСПЕХ! Покупка #{i + 1} гифта ID:{gift_id} отправлен в {destination_info}!")
                await asyncio.sleep(SLEEP_AFTER_BUY_SECONDS)
                
            except RPCError as e:
                if "STARGIFT_USAGE_LIMITED" in str(e):
                    log.warning("Подарки этого типа закончились. Прекращаем покупки.")
                    break
                elif "STARGIFT_PREMIUM_NEEDED" in str(e):
                    log.error("Ошибка: для отправки этого подарка нужен Premium.")
                    break
                else:
                    log.error(f"Ошибка API при покупке: {e}")
                    break
        
        if successful_purchases > 0:
            # Обновляем конфиг, чтобы получить актуальные данные о тратах
            updated_config = manager.get_config(client.name)
            if updated_config:
                updated_strategy = updated_config.get_best_strategy(price)
                if updated_strategy:
                    remaining = updated_strategy.max_spend - updated_strategy.current_spent
                    log.info(f"Успешно куплено {successful_purchases} подарков. Остаток по стратегии: {remaining} ⭐")
        
    except FloodWait as e:
        wait_time = e.value if isinstance(e.value, (int, float)) else 300
        log.error(f"FloodWait: Превышен лимит запросов. Ожидаем {wait_time} секунд.")
        await asyncio.sleep(wait_time)
    except Exception as e:
        log.error(f"Произошла непредвиденная ошибка в цикле покупки: {e}", exc_info=True)


async def gift_handler(client: Client, message):
    """Обработчик новых подарков с поддержкой стратегий покупки"""
    log = logging.getLogger(client.name)
    log.info(f"🔔 Получено новое сообщение в целевом канале от {client.name}!")
    log.info(f"📝 Текст сообщения: {message.text[:100]}..." if len(message.text) > 100 else f"📝 Текст сообщения: {message.text}")
    
    if config_manager is None:
        log.error("Менеджер конфигураций не инициализирован!")
        return
    
    gift_data = parse_gift_data(message.text)
    if not gift_data:
        log.info("❌ Сообщение не содержит данных о подарке")
        return

    gift_id = gift_data['GIFT_ID']
    price = gift_data['PRICE']
    
    log.info(f"🎁 Обнаружен подарок ID:{gift_id}, цена:{price} ⭐")
    
    config, strategy = await get_purchase_parameters(client, price, config_manager)
    
    if config and strategy:
        log.info(f"✅ Найдена подходящая стратегия для покупки")
        await execute_purchase_loop(client, gift_id, price, strategy, config_manager)
    else:
        log.info(f"❌ Не найдена подходящая стратегия или конфигурация отключена")


async def run_buyer(session_name: str, workdir: str):
    """Запускает и поддерживает одного клиента-покупателя"""
    client = Client(session_name, api_id=API_ID, api_hash=API_HASH, workdir=workdir)
    client.add_handler(MessageHandler(gift_handler, filters=filters.chat(TARGET_CHANNEL_ID) & filters.text))
    
    logger = logging.getLogger(client.name)
    
    try:
        await client.start()
        logger.info(f"✅ Бот-покупатель {client.name} запущен и слушает канал {TARGET_CHANNEL_ID}")
        
        # Проверяем баланс при запуске
        try:
            balance = await client.get_stars_balance()
            logger.info(f"💰 Текущий баланс: {balance} ⭐")
        except Exception as e:
            logger.warning(f"Не удалось получить баланс: {e}")
        
        # Ожидаем сообщения (запускаем бесконечный цикл)
        await asyncio.sleep(float('inf'))
        
    except Exception as e:
        logger.error(f"Ошибка при запуске покупателя {client.name}: {e}")
    finally:
        if client.is_connected:
            await client.stop()
            logger.info(f"Покупатель {client.name} остановлен")

async def main(workdir: str = "data"):
    """Основная функция для запуска всех ботов-покупателей"""
    global config_manager
    
    # Инициализируем менеджер конфигураций
    config_file = os.path.join(workdir, "buyer_configs.json")
    config_manager = BuyerConfigManager(config_file)
    
    if not BUYER_SESSIONS:
        logging.error("Список BUYER_SESSIONS в config.py пуст. Покупатели не запущены.")
        return
    
    logging.info(f"Запускаем {len(BUYER_SESSIONS)} аккаунтов-покупателей...")
    logging.info("Система стратегий покупки активирована!")
    
    tasks = [run_buyer(session, workdir) for session in BUYER_SESSIONS]
    await asyncio.gather(*tasks)
