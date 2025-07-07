# app/create_sessions.py

import asyncio
import sys
import os
from pyrogram import Client

try:
    from app.config import API_ID, API_HASH, SCANNER_SESSIONS, BUYER_SESSIONS
except ImportError:
    print("Ошибка: не удалось найти файл config.py. Убедитесь, что он находится в той же папке.")
    sys.exit(1)

# Определяем пути относительно этого файла
APP_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(APP_DIR)
DATA_DIR = os.path.join(ROOT_DIR, 'data')

# Создаем папку data, если ее нет
os.makedirs(DATA_DIR, exist_ok=True)


async def create_session(session_name: str):
    """Создает и авторизует одну сессию."""
    print(f"\n--- Создание/проверка сессии для '{session_name}' ---")
    
    # Явно указываем workdir, который мы определили выше
    async with Client(session_name, api_id=API_ID, api_hash=API_HASH, workdir=DATA_DIR) as app:
        try:
            me = await app.get_me()
            username = f"@{me.username}" if me.username else "N/A"
            print(f"✅ Сессия для пользователя {me.first_name} (ID: {me.id}, Username: {username}) успешно создана/проверена.")
        except Exception as e:
            print(f"❌ Не удалось получить информацию о пользователе для сессии '{session_name}'. Ошибка: {e}")

async def main():
    """Основная функция, которая проходит по всем сессиям из конфига."""
    all_sessions = set(SCANNER_SESSIONS + BUYER_SESSIONS)
    if not all_sessions:
        print("❗️ Списки SCANNER_SESSIONS и BUYER_SESSIONS в config.py пусты. Нечего создавать.")
        return

    print(f"Сессии будут сохранены в директорию: {DATA_DIR}")
    print("Начинаем процесс создания сессий...")
    
    for session_name in all_sessions:
        try:
            await create_session(session_name)
        except Exception as e:
            print(f"💥 Произошла критическая ошибка при обработке сессии '{session_name}': {e}")

if __name__ == "__main__":
    asyncio.run(main())
    print("\nПроцесс создания сессий завершен.")