# scanner.py

import asyncio
import logging
import json
import os

from pyrogram import Client
from pyrogram.errors import RPCError
# импортируем настройки из нашего конфига
from app.config import (
    API_ID, API_HASH, SCANNER_SESSIONS, TARGET_CHANNEL_ID,
    KNOWN_GIFTS_FILE, CHECK_INTERVAL_SECONDS
)

# Настройка логирования
logging.basicConfig(
    format="%(asctime)s - %(levelname)s - [%(name)s] - %(message)s",
    level=logging.INFO
)
log = logging.getLogger(__name__)


def load_known_gift_ids() -> set[int]:
    """Загружает ID известных гифтов из файла."""
    if not os.path.exists(KNOWN_GIFTS_FILE):
        return set()
    try:
        with open(KNOWN_GIFTS_FILE, "r", encoding="utf-8") as f:
            return set(json.load(f))
    except (json.JSONDecodeError, TypeError, FileNotFoundError):
        return set()


def save_gift_ids(gift_ids: set[int]):
    """Сохраняет все актуальные ID гифтов в файл."""
    with open(KNOWN_GIFTS_FILE, "w", encoding="utf-8") as f:
        json.dump(list(gift_ids), f, ensure_ascii=False, indent=2)


async def check_gifts_with_client(client: Client, known_ids: set) -> set:
    """Проверяет подарки с одного клиента и отправляет уведомления."""
    log.info(f"Проверка с аккаунта '{client.name}'...")
    all_gifts = await client.get_available_gifts()

    new_gifts_found = False
    current_gift_ids = {gift.id for gift in all_gifts}

    # Находим ID, которые есть в current_gift_ids, но нет в known_ids
    new_gift_ids = current_gift_ids - known_ids
    
    if new_gift_ids:
        log.warning(f"Найдены новые подарки! Количество: {len(new_gift_ids)}. Аккаунт: {client.name}")
        
        # Создаем словарь всех подарков для быстрого доступа по ID
        all_gifts_dict = {gift.id: gift for gift in all_gifts}

        for gift_id in new_gift_ids:
            gift_data = all_gifts_dict[gift_id]
            message = (
                f"NEW_GIFT\n"
                f"GIFT_ID:{gift_data.id}\n"
                f"PRICE:{gift_data.price}\n"
                # Добавим больше полезной информации
                f"TOTAL_AMOUNT:{gift_data.total_amount}"
            )
            await client.send_message(TARGET_CHANNEL_ID, message)
            log.info(f"Отправлена информация о подарке ID: {gift_data.id} в канал {TARGET_CHANNEL_ID}")
        
        # Обновляем глобальный set и сохраняем в файл
        known_ids.update(new_gift_ids)
        save_gift_ids(known_ids)
        new_gifts_found = True

    if not new_gifts_found:
        log.info(f"Новых подарков не найдено через аккаунт '{client.name}'.")

    return known_ids


async def main():
    """Основная функция для запуска сканеров."""
    if not SCANNER_SESSIONS:
        log.error("Список SCANNER_SESSIONS в config.py пуст. Сканер не запущен.")
        return

    clients = [Client(name, api_id=API_ID, api_hash=API_HASH) for name in SCANNER_SESSIONS]
    
    try:
        # Запускаем всех клиентов одновременно
        await asyncio.gather(*[client.start() for client in clients])
        log.info(f"Все {len(clients)} сканера успешно запущены.")
        
        known_gift_ids = load_known_gift_ids()
        log.info(f"Загружено {len(known_gift_ids)} известных ID подарков.")

        while True:
            # Поочередно используем клиентов для проверки
            for client in clients:
                try:
                    known_gift_ids = await check_gifts_with_client(client, known_gift_ids)
                except RPCError as e:
                    log.error(f"Ошибка API у клиента '{client.name}': {e}")
                except Exception as e:
                    log.error(f"Непредвиденная ошибка у клиента '{client.name}': {e}", exc_info=True)
                
                # Небольшая пауза между запросами от разных аккаунтов
                await asyncio.sleep(1)

            log.info(f"Цикл проверки завершен. Ожидаем {CHECK_INTERVAL_SECONDS} секунд...")
            await asyncio.sleep(CHECK_INTERVAL_SECONDS)

    finally:
        # Корректно останавливаем всех клиентов
        log.info("Остановка всех клиентов-сканеров...")
        await asyncio.gather(*[client.stop() for client in clients if client.is_connected])
        log.info("Сканеры остановлены.")
