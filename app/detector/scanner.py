import asyncio
import logging
import json
import os

from pyrogram.client import Client
from pyrogram import types

# --- Настройки ---
API_ID = int(os.getenv("API_ID", "12345678"))
API_HASH = os.getenv("API_HASH", "YOUR_API_HASH")
SESSION_NAME = "pyrogram_scanner"
TARGET_CHANNEL_ID = int(os.getenv("TARGET_CHANNEL_ID", "-1001234567890"))
KNOWN_GIFTS_FILE = "known_gifts.json"
CHECK_INTERVAL = 15

# Настройка логирования
logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s",
    level=logging.INFO
)

def load_known_gift_ids() -> set[int]:
    """Загружает ID известных гифтов из файла."""
    if not os.path.exists(KNOWN_GIFTS_FILE):
        return set()
    try:
        with open(KNOWN_GIFTS_FILE, "r", encoding="utf-8") as f:
            return set(json.load(f))
    except (json.JSONDecodeError, TypeError):
        return set()

def save_gift_ids(gift_ids: set[int]):
    """Сохраняет все актуальные ID гифтов в файл."""
    with open(KNOWN_GIFTS_FILE, "w", encoding="utf-8") as f:
        json.dump(list(gift_ids), f, ensure_ascii=False, indent=2)

async def main():
    """Основная функция запуска сканера."""
    # `Client`  из pyrofork
    app = Client(SESSION_NAME, api_id=API_ID, api_hash=API_HASH)
    
    async with app:
        logging.info("Сканер запущен на Pyrofork.")
        known_gift_ids = load_known_gift_ids()
        logging.info(f"Загружено {len(known_gift_ids)} известных гифтов.")

        while True:
            try:
                logging.info("Проверка новых подарков...")
                
                all_gifts_objects = await app.get_available_gifts()

                new_gifts = {}
                current_gift_ids = set()
                
                for gift in all_gifts_objects:
                    current_gift_ids.add(gift.id)
                    if gift.id not in known_gift_ids:
                        new_gifts[gift.id] = json.loads(
                            json.dumps(gift, default=types.Object.default)
                        )

                if new_gifts:
                    logging.warning(f"Найдены новые подарки! Количество: {len(new_gifts)}")
                    
                    for gift_id, gift_data in new_gifts.items():
                        message = (
                            f"NEW_GIFT\n"
                            f"GIFT_ID:{gift_data['id']}\n"
                            f"PRICE:{gift_data['amount']}\n"
                            f"MONTHS:{gift_data['months']}"
                        )
                        await app.send_message(TARGET_CHANNEL_ID, message)
                        logging.info(f"Отправлена информация о подарке ID: {gift_data['id']}")

                    save_gift_ids(current_gift_ids)
                    known_gift_ids = current_gift_ids
                else:
                    logging.info("Новых подарков не найдено.")

            except Exception as e:
                logging.error(f"Произошла ошибка в основном цикле: {e}", exc_info=True)
            
            await asyncio.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logging.info("Сканер остановлен.")