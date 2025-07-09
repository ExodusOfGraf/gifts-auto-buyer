import asyncio
import logging
import json
import os

from pyrogram import Client
from pyrogram.errors import RPCError

from app.config import (
    API_ID, API_HASH, SCANNER_SESSIONS, TARGET_CHANNEL_ID,
    KNOWN_GIFTS_FILE_NAME, CHECK_INTERVAL_SECONDS
)

logging.basicConfig(
    format="%(asctime)s - %(levelname)s - [%(name)s] - %(message)s",
    level=logging.INFO
)
log = logging.getLogger(__name__)

def load_known_gift_ids(gifts_file_path: str) -> set[int]:
    #Загружает ID известных гифтов из файла
    if not os.path.exists(gifts_file_path):
        return set()
    try:
        with open(gifts_file_path, "r", encoding="utf-8") as f:
            return set(json.load(f))
    except (json.JSONDecodeError, TypeError, FileNotFoundError):
        return set()

def save_gift_ids(gift_ids: set[int], gifts_file_path: str):
    #Сохраняет все актуальные ID гифтов в файл
    with open(gifts_file_path, "w", encoding="utf-8") as f:
        json.dump(list(gift_ids), f, ensure_ascii=False, indent=2)

async def check_gifts_with_client(client: Client, known_ids: set, gifts_file_path: str) -> set:
    #Проверяет подарки с одного клиента и отправляет уведомления
    log.info(f"Проверка с аккаунта '{client.name}'...")
    all_gifts = await client.get_available_gifts()

    #----------- КРАТКАЯ ДИАГНОСТИКА ------------
    
    print(f"[{client.name}] Всего получено подарков: {len(all_gifts)}")
    
    # Посчитаем, сколько из них имеют разные флаги
    upgradeable_count = sum(1 for gift in all_gifts if gift.can_upgrade)
    limited_count = sum(1 for gift in all_gifts if gift.is_limited)
    
    print(f"[{client.name}] Из них с can_upgrade=True: {upgradeable_count}")
    print(f"[{client.name}] Из них с is_limited=True: {limited_count}")
    
    # Проверим подарки с высокой ценой (возможно, это индикатор редкости)
    expensive_gifts = [gift for gift in all_gifts if gift.price and gift.price > 100]  # Подарки дороже 100 звезд
    if expensive_gifts:
        print(f"[{client.name}] Найдено дорогих подарков (>100 звезд): {len(expensive_gifts)}")

    #----------- КРАТКАЯ ДИАГНОСТИКА ------------
    
    
    # ИСПРАВЛЯЕМ ЛОГИКУ ОПРЕДЕЛЕНИЯ РЕДКИХ ПОДАРКОВ
    # can_upgrade не работает в новой версии API, используем is_limited
    rare_gifts = [gift for gift in all_gifts if gift.is_limited]
    current_rare_gift_ids = {gift.id for gift in rare_gifts}
    
    print(f"[{client.name}] Редких подарков (is_limited=True): {len(rare_gifts)}")
    
    # Если не найдено редких подарков через is_limited, пробуем альтернативные критерии
    if not rare_gifts:
        print(f"[{client.name}] is_limited не дал результатов, пробуем альтернативные критерии...")
        
        # Вариант 1: дорогие подарки (>1000 звезд)
        alternative_rare_1 = [gift for gift in all_gifts if gift.price and gift.price > 1000]
        
        # Вариант 2: подарки с upgrade_price
        alternative_rare_2 = [gift for gift in all_gifts if hasattr(gift, 'upgrade_price') and gift.upgrade_price]
        
        # Вариант 3: комбинация критериев
        alternative_rare_3 = [gift for gift in all_gifts if 
                             gift.price and gift.total_amount and
                             (gift.price > 150 and gift.total_amount < 50000)]
        
        print(f"[{client.name}] Альтернативные варианты редких подарков:")
        print(f"  - Очень дорогие (>1000 звезд): {len(alternative_rare_1)}")
        print(f"  - С upgrade_price: {len(alternative_rare_2)}")
        print(f"  - Комбинированные критерии: {len(alternative_rare_3)}")
        
        # Используем is_limited как основной критерий, а при отсутствии - upgrade_price
        rare_gifts = alternative_rare_2 if alternative_rare_2 else alternative_rare_1
        current_rare_gift_ids = {gift.id for gift in rare_gifts}
        
        if rare_gifts:
            print(f"[{client.name}] Переключаемся на альтернативный способ определения редких подарков!")
            for gift in rare_gifts[:3]:  # Показываем первые 3
                print(f"  -> Альтернативный редкий подарок: ID={gift.id}, Name={gift.name}, Price={gift.price}, Total={gift.total_amount}")
    else:
        # Показываем найденные редкие подарки
        for gift in rare_gifts[:3]:  # Показываем первые 3
            print(f"  -> Редкий подарок (is_limited): ID={gift.id}, Name={gift.name}, Price={gift.price}, Total={gift.total_amount}")
    
    new_gift_ids = current_rare_gift_ids - known_ids
    
    if new_gift_ids:
        log.warning(f"💎 НАЙДЕНЫ НОВЫЕ РЕДКИЕ ПОДАРКИ! Количество: {len(new_gift_ids)}. Аккаунт: {client.name}")
        rare_gifts_dict = {gift.id: gift for gift in rare_gifts}
        
        # Ограничиваем количество отправляемых подарков, чтобы избежать FLOOD_WAIT
        max_gifts_to_send = 3  # Отправляем максимум 3 подарка за раз
        gifts_to_send = list(new_gift_ids)[:max_gifts_to_send]
        
        if len(new_gift_ids) > max_gifts_to_send:
            log.info(f"Ограничиваем отправку до {max_gifts_to_send} подарков из {len(new_gift_ids)} найденных")
        
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
                log.info(f"Отправлено текстовое сообщение для подарка '{gift_data.name}' (ID: {gift_data.id})")
                    
            except Exception as e:
                log.error(f"Ошибка при отправке сообщения для подарка '{gift_data.name}': {e}")
                # Если это FLOOD_WAIT, ждем и пропускаем
                if "FLOOD_WAIT" in str(e):
                    log.warning(f"Пропускаем отправку из-за FLOOD_WAIT для подарка ID: {gift_data.id}")
                    continue
            
            # Добавляем задержку между отправкой сообщений
            if i < len(gifts_to_send) - 1:  # Не ждем после последнего сообщения
                await asyncio.sleep(5)  # Увеличиваем задержку до 5 секунд между сообщениями
        
        known_ids.update(new_gift_ids)
        save_gift_ids(known_ids, gifts_file_path)
    else:
        log.info(f"Новых редких подарков не найдено через аккаунт '{client.name}'.")
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
    """Форматирует сообщение с информацией о подарке"""
    gift_name = gift_data.name or gift_data.title or "Безымянный подарок"
    
    # Основное сообщение
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
    
    # Техническая информация для бота (только основная)
    message += f"\n--- Техническая информация для бота ---\n"
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
        log.info(f"Все {len(clients)} сканера успешно запущены.")
        known_gift_ids = load_known_gift_ids(gifts_file_path)
        log.info(f"Загружено {len(known_gift_ids)} известных ID редких подарков.")
        while True:
            for client in clients:
                try:
                    known_gift_ids = await check_gifts_with_client(client, known_gift_ids, gifts_file_path)
                except RPCError as e:
                    log.error(f"Ошибка API у клиента '{client.name}': {e}")
                except Exception as e:
                    log.error(f"Непредвиденная ошибка у клиента '{client.name}': {e}", exc_info=True)
                await asyncio.sleep(1)
            log.info(f"Цикл проверки завершен. Ожидаем {CHECK_INTERVAL_SECONDS} секунд...")
            await asyncio.sleep(CHECK_INTERVAL_SECONDS)
    finally:
        log.info("Остановка всех клиентов-сканеров...")
        stop_tasks = [client.stop() for client in clients if client.is_connected]
        if stop_tasks:
            await asyncio.gather(*stop_tasks)
        log.info("Сканеры остановлены.")