import asyncio
import logging
import os

from pyrogram.client import Client
from pyrogram import filters
# Мы все еще ловим ошибки, поэтому импорт остается
from pyrogram.errors import FloodWait, RPCError

# --- Настройки ---
API_ID = int(os.getenv("API_ID", "1234567"))
API_HASH = os.getenv("API_HASH", "your_api_hash")
# Важно: У каждого бота-покупателя должно быть свое уникальное имя сессии
SESSION_NAME = os.getenv("SESSION_NAME", "pyrogram_buyer_1")
TARGET_CHANNEL_ID = int(os.getenv("TARGET_CHANNEL_ID", "-1001234567890"))
 
# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format=f'%(asctime)s - {SESSION_NAME} - %(levelname)s - %(message)s'
)

def parse_gift_data(text: str) -> dict | None:
    """Парсит данные о гифте из сообщения."""
    try:
        if not text.startswith("NEW_GIFT"):
            return None
        lines = text.strip().split('\n')
        data = {}
        for line in lines[1:]:
            key, value = line.split(':', 1)
            data[key.strip()] = value.strip()
        data['GIFT_ID'] = int(data['GIFT_ID'])
        data['PRICE'] = int(data['PRICE'])
        return data
    except (ValueError, IndexError, KeyError):
        return None

# Инициализация клиента Pyrofork
app = Client(SESSION_NAME, api_id=API_ID, api_hash=API_HASH)

@app.on_message(filters.chat(TARGET_CHANNEL_ID) & filters.text)
async def gift_handler(client: Client, message):
    """Ловит новое сообщение в канале и пытается купить гифт."""
    logging.info("Получено новое сообщение в канале!")
    gift_data = parse_gift_data(message.text)
    if not gift_data:
        return

    gift_id = gift_data['GIFT_ID']
    price = gift_data['PRICE']

    try:
        me = await client.get_me()
        if me is None:
            logging.error("Не удалось получить информацию о себе.")
            return
            
        balance = getattr(me, 'stars_balance', 0)
        
        if balance < price:
            logging.warning(f"Недостаточно средств. Баланс: {balance}, Цена гифта: {price}")
            return

        quantity_to_buy = balance // price
        logging.info(f"Баланс: {balance} звезд. Цена: {price}. Покупаем {quantity_to_buy} шт. гифта ID:{gift_id}")

        # Для отправки подарка себе мы используем свой ID
        my_chat_id = me.id

        for i in range(quantity_to_buy):
            current_gift_num = i + 1
            logging.info(f"Попытка покупки #{current_gift_num}/{quantity_to_buy}...")
            
            # КЛЮЧЕВОЕ ИЗМЕНЕНИЕ: Используем чистый метод send_gift
            # Pylance не должен на него ругаться!
            await client.send_gift(
                chat_id=my_chat_id,
                gift_id=gift_id
            )
            
            logging.info(f"Покупка #{current_gift_num} гифта ID:{gift_id} УСПЕШНА!")
            await asyncio.sleep(0.2)
            
    except FloodWait as e:
        if isinstance(e.value, (int, float)):
            wait_time = float(e.value)
            logging.error(f"Превышен лимит запросов. Ожидаем {wait_time} секунд.")
            await asyncio.sleep(wait_time)
        else:
            # Безопасный fallback, если e.value вдруг окажется не числом
            wait_time = 300.0 # 5 минут
            logging.error(f"Получен неожиданный тип FloodWait.value: {type(e.value)}. Ожидаем {wait_time} секунд по умолчанию.")
            await asyncio.sleep(wait_time)
    except RPCError as e:
        # Общая обработка других ошибок API, как в вашем примере
        logging.error(f"Произошла ошибка API при покупке гифта ID:{gift_id}: {e}", exc_info=True)
    except Exception as e:
        logging.error(f"Произошла непредвиденная ошибка: {e}", exc_info=True)


async def main():
    """Основная асинхронная функция для запуска клиента."""
    await app.start()
    logging.info(f"Бот-покупатель {SESSION_NAME} (Pyrofork) успешно запущен.")
    await asyncio.Event().wait()
    await app.stop()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logging.info("Бот-покупатель остановлен.")

