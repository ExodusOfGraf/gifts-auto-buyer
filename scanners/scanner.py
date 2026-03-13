import asyncio
import logging
import json
import os

from pyrogram import Client
from pyrogram.errors import RPCError

from app.config import (
    API_ID, API_HASH, SCANNER_SESSIONS, TARGET_CHANNEL_ID,
    KNOWN_GIFTS_FILE_NAME, CHECK_INTERVAL_SECONDS,
    MAX_GIFTS_TO_SEND, MESSAGE_SEND_DELAY, SCANNER_TEST_MODE
)

logging.basicConfig(
    format="%(asctime)s - %(levelname)s - [%(name)s] - %(message)s",
    level=logging.INFO
)
log = logging.getLogger(__name__)

def load_known_gift_ids(gifts_file_path: str) -> set[int]:
    """Загружает ID известных подарков"""
    if not os.path.exists(gifts_file_path):
        return set()
    try:
        with open(gifts_file_path, "r", encoding="utf-8") as f:
            return set(json.load(f))
    except (json.JSONDecodeError, TypeError, FileNotFoundError):
        return set()

def save_gift_ids(gift_ids: set[int], gifts_file_path: str):
    """Сохраняет ID подарков в файл"""
    with open(gifts_file_path, "w", encoding="utf-8") as f:
        json.dump(list(gift_ids), f, ensure_ascii=False, indent=2)

async def check_gifts_with_client(client: Client, known_ids: set, gifts_file_path: str) -> set:
    """Проверяет подарки и отправляет уведомления"""
    all_gifts = await client.get_available_gifts()

    # Фильтрация
    if SCANNER_TEST_MODE:
        rare_gifts = all_gifts
        # log.info(f"Тест режим: все подарки ({len(all_gifts)} шт.)")
    else:
        rare_gifts = [gift for gift in all_gifts if gift.is_limited]
        # log.info(f"Только лимитированные подарки ({len(rare_gifts)} шт.)")
    
    current_rare_gift_ids = {gift.id for gift in rare_gifts}
    
    new_gift_ids = current_rare_gift_ids - known_ids
    
    if new_gift_ids:
        gift_type = "ПОДАРКИ" if SCANNER_TEST_MODE else "РЕДКИЕ ПОДАРКИ"
        log.warning(f"💎 НАЙДЕНЫ НОВЫЕ {gift_type}! Количество: {len(new_gift_ids)}. Аккаунт: {client.name}")
        rare_gifts_dict = {gift.id: gift for gift in rare_gifts}
        
        # Ограничиваем количество отправляемых подарков из конфигурации
        gifts_to_send = list(new_gift_ids)[:MAX_GIFTS_TO_SEND]
        
        if len(new_gift_ids) > MAX_GIFTS_TO_SEND:
            # log.info(f"Ограничиваем отправку до {MAX_GIFTS_TO_SEND} подарков из {len(new_gift_ids)} найденных")
            pass
        
        for i, gift_id in enumerate(gifts_to_send):
            gift_data = rare_gifts_dict[gift_id]
            
            # Получаем все доступные атрибуты подарка
            attributes = get_gift_attributes(gift_data)
            
            # Форматируем сообщение с информацией о подарке
            message = format_gift_message(gift_data, attributes)
            
            # Пытаемся отправить сообщение с медиа (изображение вместо стикера)
            try:
                # Отправляем только текстовое сообщение (убираем проблемную отправку thumbnail)
                await client.send_message(TARGET_CHANNEL_ID, message, disable_web_page_preview=True)
                # log.info(f"Отправлено текстовое сообщение для подарка '{gift_data.name}' (ID: {gift_data.id})")
                
                # Добавляем отправленный подарок в известные сразу после успешной отправки
                known_ids.add(gift_id)
                    
            except Exception as e:
                log.error(f"Ошибка при отправке сообщения для подарка '{gift_data.name}': {e}")
                # Если это FLOOD_WAIT, ждем указанное время и пропускаем
                if "FLOOD_WAIT" in str(e):
                    import re
                    wait_time_match = re.search(r'wait of (\d+) seconds', str(e))
                    if wait_time_match:
                        wait_time = int(wait_time_match.group(1))
                        log.warning(f"FLOOD_WAIT: необходимо ждать {wait_time} секунд. Пропускаем остальные подарки.")
                        # Прерываем цикл отправки, чтобы не получать еще больше FLOOD_WAIT
                        break
                    else:
                        log.warning(f"Пропускаем отправку из-за FLOOD_WAIT для подарка ID: {gift_data.id}")
                        continue
            
            # Добавляем настраиваемую задержку между отправкой сообщений
            if i < len(gifts_to_send) - 1:  # Не ждем после последнего сообщения
                await asyncio.sleep(MESSAGE_SEND_DELAY)
        
        # Сохраняем только те подарки, которые были успешно отправлены
        save_gift_ids(known_ids, gifts_file_path)
    else:
        gift_type = "подарков" if SCANNER_TEST_MODE else "редких подарков"
        # log.info(f"Новых {gift_type} не найдено через аккаунт '{client.name}'.")
    return known_ids

def get_gift_attributes(gift) -> dict:
    """Получает все доступные атрибуты подарка"""
    attributes = {}
    
    # Основные атрибуты
    basic_attrs = [
        'id', 'name', 'title', 'price', 'total_amount', 'available_amount',
        'is_limited', 'can_upgrade', 'upgrade_price', 'description',
        'emoji', 'currency', 'first_sale_date', 'last_sale_date'
    ]
    
    for attr in basic_attrs:
        try:
            value = getattr(gift, attr, None)
            if value is not None:
                attributes[attr] = value
        except:
            pass
    
    return attributes

def format_gift_message(gift_data, attributes: dict) -> str:
    """Форматирует сообщение о подарке"""
    gift_name = gift_data.name or gift_data.title or "Безымянный подарок"
    
    # Заголовок
    if SCANNER_TEST_MODE:
        if gift_data.is_limited:
            message = f"💎 **НОВЫЙ РЕДКИЙ ПОДАРОК!** 💎\n\n"
        else:
            message = f"🎁 **НОВЫЙ ПОДАРОК!** 🎁\n\n"
    else:
        message = f"💎 **НОВЫЙ РЕДКИЙ ПОДАРОК!** 💎\n\n"
    
    # Основная информация
    message += f"**🎁 Название:** `{gift_name}`\n"
    message += f"**💰 Цена:** `{gift_data.price if gift_data.price is not None else 'Неизвестно'}` ⭐\n"
    message += f"**📊 Всего доступно:** `{gift_data.total_amount if gift_data.total_amount is not None else 'Неограниченно'}` шт.\n"
    message += f"**📈 Осталось:** `{gift_data.available_amount if gift_data.available_amount is not None else 'Неизвестно'}` шт.\n"
    message += f"**🔒 Лимитированный:** `{gift_data.is_limited}`\n"
    
    # Дополнительная информация
    if attributes.get('emoji'):
        message += f"**😊 Эмодзи:** `{attributes['emoji']}`\n"
    
    if attributes.get('description'):
        message += f"**📝 Описание:** `{attributes['description']}`\n"
    
    if attributes.get('can_upgrade'):
        message += f"**⬆️ Можно улучшить:** `{attributes['can_upgrade']}`\n"
    
    if attributes.get('upgrade_price'):
        message += f"**💎 Цена улучшения:** `{attributes['upgrade_price']}` ⭐\n"
    
    if attributes.get('currency'):
        message += f"**💱 Валюта:** `{attributes['currency']}`\n"
    
    if attributes.get('first_sale_date'):
        message += f"**📅 Первая продажа:** `{attributes['first_sale_date']}`\n"
    
    if attributes.get('last_sale_date'):
        message += f"**📅 Последняя продажа:** `{attributes['last_sale_date']}`\n"
    
    # Данные для бота
    message += f"\n--- Данные для бота ---\n"
    message += f"NEW_GIFT\n"
    message += f"GIFT_ID:{gift_data.id}\n"
    message += f"PRICE:{gift_data.price}\n"
    message += f"NAME:{gift_name}\n"
    message += f"IS_LIMITED:{gift_data.is_limited}\n"
    message += f"TOTAL_AMOUNT:{gift_data.total_amount}\n"
    message += f"AVAILABLE_AMOUNT:{gift_data.available_amount}\n"
    
    return message

async def main(workdir: str):
    #Основная функция для запуска сканеров
    gifts_file_path = os.path.join(workdir, KNOWN_GIFTS_FILE_NAME)
    
    if not SCANNER_SESSIONS:
        log.error("Список SCANNER_SESSIONS в config.py пуст. Сканер не запущен.")
        return

    clients = [Client(name, api_id=API_ID, api_hash=API_HASH, workdir=workdir) for name in SCANNER_SESSIONS]
    try:
        await asyncio.gather(*[client.start() for client in clients])
        # log.info(f"Все {len(clients)} сканера успешно запущены.")
        known_gift_ids = load_known_gift_ids(gifts_file_path)
        
        mode_text = "тестирования (все подарки)" if SCANNER_TEST_MODE else "продакшена (только лимитированные)"
        # log.info(f"Режим: {mode_text}")
        # log.info(f"Загружено {len(known_gift_ids)} известных ID подарков.")
        # log.info(f"Настройки: макс. подарков={MAX_GIFTS_TO_SEND}, задержка={MESSAGE_SEND_DELAY}с, интервал={CHECK_INTERVAL_SECONDS}с")
        while True:
            for client in clients:
                try:
                    known_gift_ids = await check_gifts_with_client(client, known_gift_ids, gifts_file_path)
                except RPCError as e:
                    log.error(f"Ошибка API у клиента '{client.name}': {e}")
                except Exception as e:
                    log.error(f"Непредвиденная ошибка у клиента '{client.name}': {e}", exc_info=True)
                # Убираем задержку между сканерами для ускорения обработки
            # log.info(f"Цикл проверки завершен. Ожидаем {CHECK_INTERVAL_SECONDS} секунд...")
            await asyncio.sleep(CHECK_INTERVAL_SECONDS)
    finally:
        # log.info("Остановка всех клиентов-сканеров...")
        stop_tasks = [client.stop() for client in clients if client.is_connected]
        if stop_tasks:
            await asyncio.gather(*stop_tasks)
        # log.info("Сканеры остановлены.")