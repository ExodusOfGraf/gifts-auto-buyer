#!/usr/bin/env python3
"""
Скрипт для безопасной отправки всех накопленных подарков с обработкой FLOOD_WAIT
"""

import asyncio
import json
import logging
import os
import re
from pyrogram import Client
from app.config import API_ID, API_HASH, SCANNER_SESSIONS, TARGET_CHANNEL_ID, KNOWN_GIFTS_FILE_NAME

logging.basicConfig(
    format="%(asctime)s - %(levelname)s - [%(name)s] - %(message)s",
    level=logging.INFO
)
log = logging.getLogger(__name__)

async def send_all_gifts_safely():
    """Безопасно отправляет все накопленные подарки с обработкой FLOOD_WAIT"""
    
    # Очищаем файл known_gifts.json для повторной отправки
    gifts_file_path = os.path.join(os.getcwd(), "data", KNOWN_GIFTS_FILE_NAME)
    
    # Создаем резервную копию
    backup_path = gifts_file_path + ".backup"
    if os.path.exists(gifts_file_path):
        with open(gifts_file_path, 'r') as f:
            backup_data = f.read()
        with open(backup_path, 'w') as f:
            f.write(backup_data)
        log.info(f"Создана резервная копия: {backup_path}")
    
    # Очищаем файл для повторной отправки
    with open(gifts_file_path, 'w') as f:
        json.dump([], f)
    log.info("Файл known_gifts.json очищен для повторной отправки")
    
    # Запускаем клиент
    client_name = SCANNER_SESSIONS[0]
    client = Client(client_name, api_id=API_ID, api_hash=API_HASH, workdir=os.getcwd())
    
    try:
        await client.start()
        log.info(f"Клиент {client_name} запущен")
        
        # Получаем все подарки
        all_gifts = await client.get_available_gifts()
        rare_gifts = [gift for gift in all_gifts if gift.is_limited]
        
        log.info(f"Найдено {len(rare_gifts)} редких подарков для отправки")
        
        sent_count = 0
        failed_count = 0
        
        for i, gift in enumerate(rare_gifts):
            gift_name = gift.name or "Безымянный подарок"
            
            # Формируем сообщение
            message = f"💎 **НОВЫЙ РЕДКИЙ ПОДАРОК!** 💎\n\n"
            message += f"**🎁 Название:** `{gift_name}`\n"
            message += f"**💰 Цена:** `{gift.price if gift.price is not None else 'Неизвестно'}` ⭐\n"
            message += f"**📊 Всего доступно:** `{gift.total_amount if gift.total_amount is not None else 'Неограниченно'}` шт.\n"
            message += f"**📈 Осталось:** `{gift.available_amount if gift.available_amount is not None else 'Неизвестно'}` шт.\n"
            message += f"**🔒 Лимитированный:** `{gift.is_limited}`\n"
            message += f"\n--- Техническая информация для бота ---\n"
            message += f"NEW_GIFT\n"
            message += f"GIFT_ID:{gift.id}\n"
            message += f"PRICE:{gift.price}\n"
            message += f"NAME:{gift_name}\n"
            message += f"IS_LIMITED:{gift.is_limited}\n"
            message += f"TOTAL_AMOUNT:{gift.total_amount}\n"
            message += f"AVAILABLE_AMOUNT:{gift.available_amount}\n"
            
            try:
                await client.send_message(TARGET_CHANNEL_ID, message, disable_web_page_preview=True)
                sent_count += 1
                log.info(f"[{sent_count}/{len(rare_gifts)}] Отправлен подарок: {gift_name} (ID: {gift.id})")
                
                # Сохраняем отправленный подарок
                with open(gifts_file_path, 'r') as f:
                    known_gifts = json.load(f)
                known_gifts.append(gift.id)
                with open(gifts_file_path, 'w') as f:
                    json.dump(known_gifts, f)
                
            except Exception as e:
                failed_count += 1
                log.error(f"[{failed_count} ошибок] Ошибка при отправке подарка {gift_name}: {e}")
                
                if "FLOOD_WAIT" in str(e):
                    wait_time_match = re.search(r'wait of (\d+) seconds', str(e))
                    if wait_time_match:
                        wait_time = int(wait_time_match.group(1))
                        log.warning(f"FLOOD_WAIT: ожидание {wait_time} секунд...")
                        await asyncio.sleep(wait_time + 5)  # Ждем + 5 секунд для безопасности
                        
                        # Пробуем отправить повторно
                        try:
                            await client.send_message(TARGET_CHANNEL_ID, message, disable_web_page_preview=True)
                            sent_count += 1
                            log.info(f"[{sent_count}/{len(rare_gifts)}] Повторно отправлен подарок: {gift_name} (ID: {gift.id})")
                            
                            # Сохраняем отправленный подарок
                            with open(gifts_file_path, 'r') as f:
                                known_gifts = json.load(f)
                            known_gifts.append(gift.id)
                            with open(gifts_file_path, 'w') as f:
                                json.dump(known_gifts, f)
                        except Exception as e2:
                            log.error(f"Повторная отправка тоже не удалась: {e2}")
                            continue
            
            # Увеличенная задержка между сообщениями
            if i < len(rare_gifts) - 1:
                await asyncio.sleep(20)  # 20 секунд между сообщениями
        
        log.info(f"Отправка завершена. Успешно: {sent_count}, Ошибок: {failed_count}")
        
    finally:
        await client.stop()
        log.info("Клиент остановлен")

if __name__ == "__main__":
    asyncio.run(send_all_gifts_safely())
