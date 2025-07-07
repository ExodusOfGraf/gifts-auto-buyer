# app/buyer.py

import asyncio
import logging
import os

from pyrogram import Client, filters
from pyrogram.handlers import MessageHandler
from pyrogram.errors import FloodWait, RPCError
from app.config import (
    API_ID, API_HASH, BUYER_SESSIONS, TARGET_CHANNEL_ID,
    SLEEP_AFTER_BUY_SECONDS
)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - [%(name)s] - %(levelname)s - %(message)s'
)

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

async def gift_handler(client: Client, message):
    log = logging.getLogger(client.name)
    log.info("Получено новое сообщение в целевом канале!")
    gift_data = parse_gift_data(message.text)
    if not gift_data:
        return

    gift_id = gift_data['GIFT_ID']
    price = gift_data['PRICE']

    try:
        balance = await client.get_stars_balance()
        if balance < price:
            log.warning(f"Недостаточно средств. Баланс: {balance} ★, Цена: {price} ★")
            return

        quantity_to_buy = balance // price
        log.info(f"Баланс: {balance} ★. Цена: {price} ★. Покупаем {quantity_to_buy} шт. гифта ID:{gift_id}")
        for i in range(quantity_to_buy):
            log.info(f"Попытка покупки #{i + 1}/{quantity_to_buy}...")
            await client.send_gift(chat_id="me", gift_id=gift_id)
            log.info(f"✅ УСПЕХ! Покупка #{i + 1} гифта ID:{gift_id}!")
            await asyncio.sleep(SLEEP_AFTER_BUY_SECONDS)
    except FloodWait as e:
        wait_time = e.value if isinstance(e.value, (int, float)) else 300
        log.error(f"FloodWait: Превышен лимит запросов. Ожидаем {wait_time} секунд.")
        await asyncio.sleep(wait_time)
    except RPCError as e:
        if "STARGIFT_PREMIUM_NEEDED" in str(e):
            log.error("Ошибка: для отправки этого подарка нужен Premium.")
        elif "STARGIFT_USAGE_LIMITED" in str(e):
            log.warning("Подарки этого типа закончились (usage limited).")
        else:
            log.error(f"Произошла ошибка API при покупке гифта ID:{gift_id}: {e}", exc_info=True)
    except Exception as e:
        log.error(f"Произошла непредвиденная ошибка: {e}", exc_info=True)

async def run_buyer(session_name: str, workdir: str):
    """Запускает и поддерживает одного клиента-покупателя."""
    client = Client(session_name, api_id=API_ID, api_hash=API_HASH, workdir=workdir)
    client.add_handler(MessageHandler(gift_handler, filters=filters.chat(TARGET_CHANNEL_ID) & filters.text))
    await client.start()
    log = logging.getLogger(client.name)
    log.info(f"Бот-покупатель запущен и слушает канал {TARGET_CHANNEL_ID}.")
    await asyncio.Event().wait()
    await client.stop()
    log.info("Бот-покупатель остановлен.")

async def main(workdir: str):
    """Основная функция для запуска всех покупателей."""
    if not BUYER_SESSIONS:
        logging.error("Список BUYER_SESSIONS в config.py пуст. Покупатели не запущены.")
        return
    logging.info(f"Запускаем {len(BUYER_SESSIONS)} аккаунтов-покупателей...")
    tasks = [run_buyer(session, workdir) for session in BUYER_SESSIONS]
    await asyncio.gather(*tasks)