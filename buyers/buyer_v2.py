import asyncio
import logging
import os
import sys
import time
import json
from typing import Optional
from dataclasses import dataclass, field, asdict
from collections import defaultdict

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pyrogram import Client, filters
from pyrogram.handlers import MessageHandler
from pyrogram.errors import FloodWait, RPCError
from app.config import (
    API_ID, API_HASH, BUYER_SESSIONS, TARGET_CHANNEL_ID,
    SLEEP_AFTER_BUY_SECONDS, ENABLE_PERFORMANCE_TRACKING, PERFORMANCE_LOG_INTERVAL,
    SYSTEM_STATS_LOG_INTERVAL_MINUTES
)
from .buyer_config import BuyerConfig, BuyerConfigManager, BuyingStrategy

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - [%(name)s] - %(levelname)s - %(message)s'
)

@dataclass
class PurchaseStats:
    """Статистика времени покупок"""
    total_purchases: int = 0
    successful_purchases: int = 0
    failed_purchases: int = 0
    total_time: float = 0.0
    min_time: float = float('inf')
    max_time: float = 0.0
    purchase_times: list = field(default_factory=list)
    reaction_times: list = field(default_factory=list)
    api_call_times: list = field(default_factory=list)
    total_reaction_time: float = 0.0
    total_api_time: float = 0.0
    
    def add_purchase(self, duration: float, success: bool):
        """Добавляет статистику покупки"""
        self.total_purchases += 1
        if success:
            self.successful_purchases += 1
        else:
            self.failed_purchases += 1
            
        self.total_time += duration
        self.min_time = min(self.min_time, duration)
        self.max_time = max(self.max_time, duration)
        self.purchase_times.append(duration)
        
        # Ограничиваем историю
        if len(self.purchase_times) > 100:
            self.purchase_times.pop(0)
    
    def add_reaction_time(self, duration: float):
        self.total_reaction_time += duration
        self.reaction_times.append(duration)
        if len(self.reaction_times) > 100:
            self.reaction_times.pop(0)
    
    def add_api_time(self, duration: float):
        self.total_api_time += duration
        self.api_call_times.append(duration)
        if len(self.api_call_times) > 100:
            self.api_call_times.pop(0)
    
    def get_average_time(self) -> float:
        return self.total_time / max(1, self.total_purchases)
    
    def get_recent_average(self, count: int = 10) -> float:
        recent = self.purchase_times[-count:] if self.purchase_times else []
        return sum(recent) / max(1, len(recent))
    
    def get_average_reaction_time(self) -> float:
        return (self.total_reaction_time / max(1, len(self.reaction_times))) if self.reaction_times else 0.0
    
    def get_average_api_time(self) -> float:
        return (self.total_api_time / max(1, len(self.api_call_times))) if self.api_call_times else 0.0

# Глобальные переменные
config_manager: Optional[BuyerConfigManager] = None
performance_stats: dict[str, PurchaseStats] = defaultdict(PurchaseStats)

def parse_gift_data(text: str) -> dict | None:
    """Парсит данные подарка из сообщения"""
    try:
        if "NEW_GIFT" not in text:
            return None
        
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
    """Проверяет конфиг и выбирает стратегию покупки"""
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
    """Выполняет цикл покупки подарков"""
    log = logging.getLogger(client.name)
    start_time = time.time()
    
    try:
        balance = await client.get_stars_balance()
        if balance < price:
            log.warning(f"Недостаточно средств. Баланс: {balance} ⭐, Цена: {price} ⭐")
            return

        # Определяем место отправки
        if strategy.send_to_self:
            chat_id = "me"
            destination_info = "профиль"
        else:
            chat_id = strategy.target_channel_id
            destination_info = f"канал {chat_id}"

        # Вычисляем количество подарков для покупки
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
            purchase_start = time.time()
            purchase_success = False
            
            try:
                log.info(f"Попытка покупки #{i + 1}/{quantity_to_buy}...")
                
                api_start = time.time()
                await client.send_gift(chat_id=chat_id, gift_id=gift_id)
                api_time = time.time() - api_start
                
                manager.update_purchase(client.name, price)
                successful_purchases += 1
                purchase_success = True
                
                purchase_time = time.time() - purchase_start
                log.info(f"✅ УСПЕХ! Покупка #{i + 1} гифта ID:{gift_id} отправлен в {destination_info}! Время: {purchase_time:.3f}с (API: {api_time:.3f}с)")
                
                if ENABLE_PERFORMANCE_TRACKING:
                    performance_stats[client.name].add_purchase(purchase_time, True)
                    performance_stats[client.name].add_api_time(api_time)
                
                await asyncio.sleep(SLEEP_AFTER_BUY_SECONDS)
                
            except RPCError as e:
                purchase_time = time.time() - purchase_start
                
                if ENABLE_PERFORMANCE_TRACKING:
                    performance_stats[client.name].add_purchase(purchase_time, False)
                
                if "STARGIFT_USAGE_LIMITED" in str(e):
                    log.warning(f"Подарки этого типа закончились. Прекращаем покупки. Время попытки: {purchase_time:.3f}с")
                    break
                elif "STARGIFT_PREMIUM_NEEDED" in str(e):
                    log.error(f"Ошибка: для отправки этого подарка нужен Premium. Время попытки: {purchase_time:.3f}с")
                    break
                else:
                    log.error(f"Ошибка API при покупке: {e}. Время попытки: {purchase_time:.3f}с")
                    break
        
        # Общее время обработки
        total_time = time.time() - start_time
        
        if successful_purchases > 0:
            updated_config = manager.get_config(client.name)
            if updated_config:
                updated_strategy = updated_config.get_best_strategy(price)
                if updated_strategy:
                    remaining = updated_strategy.max_spend - updated_strategy.current_spent
                    log.info(f"Успешно куплено {successful_purchases} подарков. Остаток по стратегии: {remaining} ⭐")
            
            if ENABLE_PERFORMANCE_TRACKING:
                stats = performance_stats[client.name]
                log.info(f"⏱️ Общее время обработки: {total_time:.3f}с. Среднее время покупки: {stats.get_average_time():.3f}с")
                
                if PERFORMANCE_LOG_INTERVAL > 0 and stats.total_purchases % PERFORMANCE_LOG_INTERVAL == 0:
                    log_performance_stats(client.name, stats)
        
    except FloodWait as e:
        wait_time = e.value if isinstance(e.value, (int, float)) else 300
        log.error(f"FloodWait: Превышен лимит запросов. Ожидаем {wait_time} секунд.")
        await asyncio.sleep(wait_time)
    except Exception as e:
        log.error(f"Произошла непредвиденная ошибка в цикле покупки: {e}", exc_info=True)


async def gift_handler(client: Client, message):
    """Обработчик новых подарков"""
    log = logging.getLogger(client.name)
    reaction_start = time.time()
    
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
    
    reaction_time = time.time() - reaction_start
    log.info(f"🎁 Обнаружен подарок ID:{gift_id}, цена:{price} ⭐. Время реакции: {reaction_time:.3f}с")
    
    if ENABLE_PERFORMANCE_TRACKING:
        performance_stats[client.name].add_reaction_time(reaction_time)
    
    config, strategy = await get_purchase_parameters(client, price, config_manager)
    
    if config and strategy:
        log.info(f"✅ Найдена подходящая стратегия для покупки")
        await execute_purchase_loop(client, gift_id, price, strategy, config_manager)
    else:
        log.info(f"❌ Не найдена подходящая стратегия или конфигурация отключена")
    
    total_processing_time = time.time() - reaction_start
    if ENABLE_PERFORMANCE_TRACKING:
        log.info(f"⏰ Общее время обработки сообщения: {total_processing_time:.3f}с")

async def run_buyer(session_name: str, workdir: str):
    """Запускает клиента-покупателя"""
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
        
        # Логируем настройки производительности
        if ENABLE_PERFORMANCE_TRACKING:
            logger.info(f"📊 Отслеживание производительности включено (интервал: {PERFORMANCE_LOG_INTERVAL} покупок)")
            logger.info(f"⏱️ Система будет отслеживать: время реакции, время API вызовов, время покупок")
        else:
            logger.info("📊 Отслеживание производительности отключено")
        
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
    
    # Логируем настройки производительности
    if ENABLE_PERFORMANCE_TRACKING:
        logging.info(f"📊 Отслеживание производительности включено")
        logging.info(f"⏱️ Детальная статистика каждые {PERFORMANCE_LOG_INTERVAL} покупок")
        if SYSTEM_STATS_LOG_INTERVAL_MINUTES > 0:
            logging.info(f"🌍 Общая статистика системы каждые {SYSTEM_STATS_LOG_INTERVAL_MINUTES} минут")
    
    # Создаем задачи для всех покупателей
    buyer_tasks = [run_buyer(session, workdir) for session in BUYER_SESSIONS]
    
    # Добавляем задачу для периодической статистики системы
    if ENABLE_PERFORMANCE_TRACKING and SYSTEM_STATS_LOG_INTERVAL_MINUTES > 0:
        buyer_tasks.append(system_stats_logger())
    
    await asyncio.gather(*buyer_tasks)

def log_performance_stats(client_name: str, stats: PurchaseStats):
    """Логирует подробную статистику производительности"""
    log = logging.getLogger(client_name)
    
    success_rate = (stats.successful_purchases / max(1, stats.total_purchases)) * 100
    recent_avg = stats.get_recent_average(10)
    avg_reaction = stats.get_average_reaction_time()
    avg_api = stats.get_average_api_time()
    
    log.info("=" * 60)
    log.info(f"📊 ДЕТАЛЬНАЯ СТАТИСТИКА ПРОИЗВОДИТЕЛЬНОСТИ {client_name}")
    log.info("=" * 60)
    log.info(f"📈 Всего попыток покупки: {stats.total_purchases}")
    log.info(f"✅ Успешных покупок: {stats.successful_purchases}")
    log.info(f"❌ Неудачных покупок: {stats.failed_purchases}")
    log.info(f"🎯 Процент успешности: {success_rate:.1f}%")
    log.info("-" * 40)
    log.info(f"⏱️ Среднее время покупки: {stats.get_average_time():.3f}с")
    log.info(f"🔥 Среднее время последних 10: {recent_avg:.3f}с")
    log.info(f"⚡ Лучшее время покупки: {stats.min_time:.3f}с")
    log.info(f"🐌 Худшее время покупки: {stats.max_time:.3f}с")
    log.info("-" * 40)
    log.info(f"🚀 Среднее время реакции: {avg_reaction:.3f}с")
    log.info(f"🌐 Среднее время API вызовов: {avg_api:.3f}с")
    log.info(f"📊 Обработано сообщений: {len(stats.reaction_times)}")
    log.info("=" * 60)

def log_system_performance_stats():
    """Логирует общую статистику производительности всех скупщиков"""
    if not performance_stats:
        return
    
    # Создаем общий лог
    log = logging.getLogger("SYSTEM_STATS")
    
    total_purchases = sum(stats.total_purchases for stats in performance_stats.values())
    total_successful = sum(stats.successful_purchases for stats in performance_stats.values())
    total_failed = sum(stats.failed_purchases for stats in performance_stats.values())
    
    if total_purchases == 0:
        log.info("📊 Система пока не совершала покупок")
        return
    
    # Общая статистика
    overall_success_rate = (total_successful / total_purchases) * 100
    avg_purchase_times = [stats.get_average_time() for stats in performance_stats.values() if stats.total_purchases > 0]
    avg_reaction_times = [stats.get_average_reaction_time() for stats in performance_stats.values() if stats.reaction_times]
    avg_api_times = [stats.get_average_api_time() for stats in performance_stats.values() if stats.api_call_times]
    
    system_avg_purchase = sum(avg_purchase_times) / len(avg_purchase_times) if avg_purchase_times else 0
    system_avg_reaction = sum(avg_reaction_times) / len(avg_reaction_times) if avg_reaction_times else 0
    system_avg_api = sum(avg_api_times) / len(avg_api_times) if avg_api_times else 0
    
    log.info("🌍" + "=" * 80)
    log.info("🌍 ОБЩАЯ СТАТИСТИКА СИСТЕМЫ ПОКУПКИ ПОДАРКОВ")
    log.info("🌍" + "=" * 80)
    log.info(f"👥 Активных скупщиков: {len(performance_stats)}")
    log.info(f"📈 Всего попыток покупки: {total_purchases}")
    log.info(f"✅ Успешных покупок: {total_successful}")
    log.info(f"❌ Неудачных покупок: {total_failed}")
    log.info(f"🎯 Общий процент успешности: {overall_success_rate:.1f}%")
    log.info("-" * 60)
    log.info(f"⏱️ Среднее время покупки по системе: {system_avg_purchase:.3f}с")
    log.info(f"🚀 Среднее время реакции по системе: {system_avg_reaction:.3f}с")
    log.info(f"🌐 Среднее время API вызовов по системе: {system_avg_api:.3f}с")
    log.info("-" * 60)
    
    # Статистика по каждому скупщику
    for client_name, stats in performance_stats.items():
        if stats.total_purchases > 0:
            success_rate = (stats.successful_purchases / stats.total_purchases) * 100
            log.info(f"🤖 {client_name}: {stats.successful_purchases}/{stats.total_purchases} ({success_rate:.1f}%) | "
                    f"⏱️ {stats.get_average_time():.3f}с | 🚀 {stats.get_average_reaction_time():.3f}с")
    
    log.info("🌍" + "=" * 80)

async def system_stats_logger():
    """Периодически логирует общую статистику системы"""
    if SYSTEM_STATS_LOG_INTERVAL_MINUTES <= 0:
        return
    
    iteration = 0
    while True:
        await asyncio.sleep(SYSTEM_STATS_LOG_INTERVAL_MINUTES * 60)  # Конвертируем минуты в секунды
        if ENABLE_PERFORMANCE_TRACKING:
            iteration += 1
            log_system_performance_stats()
            
            # Экспортируем статистику каждые 3 итерации (каждые 30 минут по умолчанию)
            if iteration % 3 == 0:
                export_performance_stats_to_file()

def export_performance_stats_to_file(workdir: str = "data"):
    """Экспортирует статистику производительности в JSON файл"""
    if not performance_stats:
        return
    
    # Подготавливаем данные для экспорта
    export_data = {
        "timestamp": time.time(),
        "timestamp_human": time.strftime("%Y-%m-%d %H:%M:%S"),
        "total_buyers": len(performance_stats),
        "buyers": {}
    }
    
    for client_name, stats in performance_stats.items():
        # Конвертируем dataclass в dict, исключая большие списки времен
        stats_dict = {
            "total_purchases": stats.total_purchases,
            "successful_purchases": stats.successful_purchases,
            "failed_purchases": stats.failed_purchases,
            "success_rate": (stats.successful_purchases / max(1, stats.total_purchases)) * 100,
            "total_time": stats.total_time,
            "min_time": stats.min_time if stats.min_time != float('inf') else 0,
            "max_time": stats.max_time,
            "average_time": stats.get_average_time(),
            "recent_average_10": stats.get_recent_average(10),
            "average_reaction_time": stats.get_average_reaction_time(),
            "average_api_time": stats.get_average_api_time(),
            "total_messages_processed": len(stats.reaction_times),
            "total_api_calls": len(stats.api_call_times)
        }
        export_data["buyers"][client_name] = stats_dict
    
    # Добавляем общую статистику
    total_purchases = sum(stats.total_purchases for stats in performance_stats.values())
    total_successful = sum(stats.successful_purchases for stats in performance_stats.values())
    
    export_data["system_summary"] = {
        "total_purchases": total_purchases,
        "total_successful": total_successful,
        "total_failed": total_purchases - total_successful,
        "overall_success_rate": (total_successful / max(1, total_purchases)) * 100
    }
    
    # Сохраняем в файл
    stats_file = os.path.join(workdir, f"performance_stats_{int(time.time())}.json")
    try:
        with open(stats_file, 'w', encoding='utf-8') as f:
            json.dump(export_data, f, ensure_ascii=False, indent=2)
        
        logging.info(f"📊 Статистика производительности экспортирована в {stats_file}")
    except Exception as e:
        logging.error(f"Ошибка при экспорте статистики: {e}")
