# app/scanner.py

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
    """Загружает ID известных гифтов из файла."""
    if not os.path.exists(gifts_file_path):
        return set()
    try:
        with open(gifts_file_path, "r", encoding="utf-8") as f:
            return set(json.load(f))
    except (json.JSONDecodeError, TypeError, FileNotFoundError):
        return set()

def save_gift_ids(gift_ids: set[int], gifts_file_path: str):
    """Сохраняет все актуальные ID гифтов в файл."""
    with open(gifts_file_path, "w", encoding="utf-8") as f:
        json.dump(list(gift_ids), f, ensure_ascii=False, indent=2)

async def check_gifts_with_client(client: Client, known_ids: set, gifts_file_path: str) -> set:
    """Проверяет подарки с одного клиента и отправляет уведомления."""
    log.info(f"Проверка с аккаунта '{client.name}'...")
    all_gifts = await client.get_available_gifts()

    #----------- ОТЛАДКА ------------
    '''
    print(f"[{client.name}] Всего получено подарков: {len(all_gifts)}")
    
    # Посчитаем, сколько из них имеют флаг can_upgrade
    upgradeable_count = 0
    for gift in all_gifts:
        if gift.can_upgrade:
            upgradeable_count += 1
            # Распечатаем детали каждого редкого подарка
            print(f"  -> Найден редкий подарок: ID={gift.id}, Name='{gift.name}', Can_Upgrade={gift.can_upgrade}")

    print(f"[{client.name}] Из них редких (can_upgrade=True): {upgradeable_count}")

    #----------- ОТЛАДКА ------------
    '''
    
    rare_gifts = [gift for gift in all_gifts if gift.can_upgrade]
    current_rare_gift_ids = {gift.id for gift in rare_gifts}
    new_gift_ids = current_rare_gift_ids - known_ids
    
    if new_gift_ids:
        log.warning(f"💎 НАЙДЕНЫ НОВЫЕ РЕДКИЕ ПОДАРКИ! Количество: {len(new_gift_ids)}. Аккаунт: {client.name}")
        rare_gifts_dict = {gift.id: gift for gift in rare_gifts}
        for gift_id in new_gift_ids:
            gift_data = rare_gifts_dict[gift_id]
            message = (
                f"💎 **НОВЫЙ РЕДКИЙ ПОДАРОК!** 💎\n\n"
                f"**Название:** `{gift_data.name}`\n"
                f"**Цена:** `{gift_data.price}` ★\n"
                f"**Всего доступно:** `{gift_data.total_amount}` шт.\n\n"
                f"--- Техническая информация для бота ---\n"
                f"NEW_GIFT\n"
                f"GIFT_ID:{gift_data.id}\n"
                f"PRICE:{gift_data.price}\n"
                f"NAME:{gift_data.name}\n"
                f"CAN_UPGRADE:{gift_data.can_upgrade}"
            )
            await client.send_sticker(TARGET_CHANNEL_ID, gift_data.sticker.file_id)
            await client.send_message(TARGET_CHANNEL_ID, message, disable_web_page_preview=True)
            log.info(f"Отправлена информация о подарке '{gift_data.name}' (ID: {gift_data.id}) в канал {TARGET_CHANNEL_ID}")
        
        known_ids.update(new_gift_ids)
        save_gift_ids(known_ids, gifts_file_path)
    else:
        log.info(f"Новых редких подарков не найдено через аккаунт '{client.name}'.")
    return known_ids

async def main(workdir: str):
    """Основная функция для запуска сканеров."""
    # Путь к файлу строится с использованием KNOWN_GIFTS_FILE_NAME
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