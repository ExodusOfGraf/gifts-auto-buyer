import asyncio
import sys
import os
from pyrogram import Client

# Добавляем родительскую папку в путь, если скрипт запускается напрямую из app/
# Это нужно, чтобы импорт config сработал, даже если вы запускаете скрипт из корневой папки
# sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

try:
    # Пытаемся импортировать настройки
    from config import API_ID, API_HASH, SCANNER_SESSIONS, BUYER_SESSIONS
except ImportError:
    print("Ошибка: не удалось найти файл config.py. Убедитесь, что он находится в той же папке.")
    sys.exit(1)

async def create_session(session_name: str):
    """
    Создает и авторизует одну сессию.
    """
    print(f"\n--- Создание/проверка сессии для '{session_name}' ---")
    
    # Мы создаем клиент с указанием рабочей директории, чтобы .session файлы
    # всегда сохранялись в папке, где лежит этот скрипт (т.е. в /app)
    workdir = os.path.dirname(__file__)
    
    # Используем async with для автоматического старта и остановки клиента
    async with Client(session_name, api_id=API_ID, api_hash=API_HASH, workdir=workdir) as app:
        try:
            me = await app.get_me()
            # Проверяем, есть ли у пользователя username для более информативного вывода
            username = f"@{me.username}" if me.username else "N/A"
            print(f"✅ Сессия для пользователя {me.first_name} (ID: {me.id}, Username: {username}) успешно создана/проверена.")
            
        except Exception as e:
            print(f"❌ Не удалось получить информацию о пользователе для сессии '{session_name}'. Ошибка: {e}")

async def main():
    """
    Основная функция, которая проходит по всем сессиям из конфига.
    """
    # Объединяем списки сессий и убираем дубликаты с помощью set
    all_sessions = set(SCANNER_SESSIONS + BUYER_SESSIONS)
    
    if not all_sessions:
        print("❗️ Списки SCANNER_SESSIONS и BUYER_SESSIONS в config.py пусты. Нечего создавать.")
        return

    print("Начинаем процесс создания сессий. Для каждого нового аккаунта")
    print("потребуется ввести номер телефона, код подтверждения и, возможно, пароль 2ФА.")
    
    for session_name in all_sessions:
        try:
            await create_session(session_name)
        except Exception as e:
            print(f"💥 Произошла критическая ошибка при обработке сессии '{session_name}': {e}")

if __name__ == "__main__":
    # Запускаем асинхронную функцию main
    asyncio.run(main())
    print("\nПроцесс создания сессий завершен.")