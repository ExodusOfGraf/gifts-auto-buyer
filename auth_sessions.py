#!/usr/bin/env python3
"""
Скрипт для авторизации сессий юзер-ботов (сканеров и покупателей)
Использование: python auth_sessions.py [scanner|buyer] [имя_сессии]
"""

import asyncio
import sys
import os
import locale
import getpass
from pyrogram import Client
from pyrogram.errors import (
    FloodWait, PhoneCodeInvalid, PasswordHashInvalid, 
    PhoneCodeExpired, PhoneNumberInvalid, SessionPasswordNeeded
)

# Добавляем путь к корневой папке проекта
ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.append(ROOT_DIR)

from app.config import API_ID, API_HASH, SCANNER_SESSIONS, BUYER_SESSIONS

# Устанавливаем правильную локаль для консоли
try:
    locale.setlocale(locale.LC_ALL, '')
except:
    pass
os.environ['PYTHONIOENCODING'] = 'utf-8'

def print_header(session_name, session_type):
    """Выводит заголовок авторизации"""
    print("\n" + "=" * 60)
    print(f"АВТОРИЗАЦИЯ СЕССИИ: {session_name}")
    print(f"Тип: {session_type.upper()}")
    print("=" * 60 + "\n")

def safe_input(prompt, required=True):
    """Ввод с обработкой ошибок"""
    while True:
        try:
            value = input(prompt).strip()
            if required and not value:
                print("❌ Поле не может быть пустым. Попробуйте снова.")
                continue
            return value
        except (EOFError, KeyboardInterrupt):
            print("\n❌ Операция отменена пользователем.")
            sys.exit(1)
        except Exception as e:
            print(f"❌ Ошибка ввода: {e}. Попробуйте снова.")

def validate_phone(phone):
    """Валидация номера телефона"""
    if not phone.startswith("+"):
        return False, "Номер должен начинаться с '+'"
    
    if len(phone) < 10:
        return False, "Номер слишком короткий"
    
    # Убираем + и проверяем что остальное - цифры
    if not phone[1:].isdigit():
        return False, "Номер должен содержать только цифры после '+'"
    
    return True, "OK"

def validate_code(code):
    """Валидация кода подтверждения"""
    # Убираем пробелы и дефисы
    code = code.replace(" ", "").replace("-", "")
    
    if not code.isdigit():
        return False, "Код должен содержать только цифры"
    
    if len(code) < 4 or len(code) > 6:
        return False, "Код должен содержать 4-6 цифр"
    
    return True, code

async def auth_session(session_name, session_type):
    """Авторизует сессию юзер-бота"""
    print_header(session_name, session_type)
    
    # Создаем папку data если её нет
    data_dir = os.path.join(ROOT_DIR, "data")
    os.makedirs(data_dir, exist_ok=True)
    
    # Путь к файлу сессии
    session_path = os.path.join(data_dir, session_name)
    
    # Создаем клиента
    client = Client(
        session_path,
        API_ID,
        API_HASH,
        device_model="Desktop",
        app_version="1.0.0",
        system_version="Linux"
    )
    
    try:
        print("🔗 Подключение к Telegram...")
        await client.start()
        
        # Проверяем авторизацию
        me = await client.get_me()
        if me:
            print("✅ Сессия уже авторизована!")
            print(f"👤 Пользователь: {me.first_name} {me.last_name or ''}")
            print(f"🆔 ID: {me.id}")
            print(f"📱 Телефон: {me.phone_number or 'Скрыт'}")
            print(f"👑 Премиум: {'Да' if me.is_premium else 'Нет'}")
            return True
            
    except Exception:
        # Сессия не авторизована - начинаем процесс авторизации
        print("⚠️ Сессия не авторизована. Начинаем процесс авторизации...\n")
        
        try:
            await client.connect()
            
            # Шаг 1: Запрос номера телефона
            while True:
                phone = safe_input("📱 Введите номер телефона (формат: +7XXXXXXXXXX): ")
                is_valid, message = validate_phone(phone)
                if is_valid:
                    break
                print(f"❌ {message}")
            
            # Шаг 2: Отправка кода
            print(f"📤 Отправка кода на номер {phone}...")
            try:
                sent_code = await client.send_code(phone)
                print("✅ Код отправлен! Проверьте Telegram или SMS.")
            except FloodWait as e:
                wait_time = e.value if isinstance(e.value, (int, float)) else 60
                print(f"⏳ Слишком много запросов. Подождите {wait_time} секунд.")
                await asyncio.sleep(wait_time)
                sent_code = await client.send_code(phone)
            except PhoneNumberInvalid:
                print("❌ Неверный номер телефона!")
                return False
            except Exception as e:
                print(f"❌ Не удалось отправить код: {e}")
                return False
            
            # Шаг 3: Ввод кода подтверждения
            attempts = 3
            signed_in = False
            
            while attempts > 0 and not signed_in:
                code_input = safe_input(f"🔢 Введите код подтверждения (осталось попыток: {attempts}): ")
                is_valid, clean_code = validate_code(code_input)
                
                if not is_valid:
                    print(f"❌ {clean_code}")
                    continue
                
                try:
                    await client.sign_in(phone, sent_code.phone_code_hash, clean_code)
                    signed_in = True
                    break
                except PhoneCodeInvalid:
                    attempts -= 1
                    if attempts > 0:
                        print(f"❌ Неверный код. Попробуйте снова. (осталось попыток: {attempts})")
                    else:
                        print("❌ Исчерпаны попытки ввода кода.")
                        return False
                except PhoneCodeExpired:
                    print("❌ Код истек. Попробуйте запустить скрипт заново.")
                    return False
                except SessionPasswordNeeded:
                    print("🔐 Требуется пароль двухфакторной аутентификации.")
                    signed_in = True
                    break
                except Exception as e:
                    if "2FA" in str(e) or "PASSWORD_HASH_INVALID" in str(e) or "password" in str(e).lower():
                        print("🔐 Требуется пароль двухфакторной аутентификации.")
                        signed_in = True
                        break
                    else:
                        attempts -= 1
                        if attempts > 0:
                            print(f"❌ Ошибка: {e}. Попробуйте снова. (осталось попыток: {attempts})")
                        else:
                            print(f"❌ Не удалось войти: {e}")
                            return False
            
            # Шаг 4: Двухфакторная аутентификация (если нужна)
            me = await client.get_me()
            if not me:
                print("🔑 Введите пароль двухфакторной аутентификации...")
                attempts = 3
                while attempts > 0:
                    password = getpass.getpass(f"🔒 Пароль 2FA (осталось попыток: {attempts}): ")
                    try:
                        await client.check_password(password)
                        break
                    except PasswordHashInvalid:
                        attempts -= 1
                        if attempts > 0:
                            print(f"❌ Неверный пароль. Попробуйте снова. (осталось попыток: {attempts})")
                        else:
                            print("❌ Исчерпаны попытки ввода пароля.")
                            return False
                    except Exception as e:
                        print(f"❌ Ошибка: {e}")
                        return False
            
            # Проверяем финальную авторизацию
            me = await client.get_me()
            if me:
                print("\n🎉 УСПЕШНАЯ АВТОРИЗАЦИЯ!")
                print("=" * 40)
                print(f"👤 Имя: {me.first_name} {me.last_name or ''}")
                print(f"🆔 ID: {me.id}")
                print(f"📱 Телефон: {me.phone_number or 'Скрыт'}")
                print(f"📛 Username: @{me.username or 'Не установлен'}")
                print(f"👑 Премиум: {'Да' if me.is_premium else 'Нет'}")
                print(f"💾 Сессия сохранена: {session_path}.session")
                print("=" * 40)
                return True
            else:
                print("❌ Не удалось завершить авторизацию.")
                return False
                
        except KeyboardInterrupt:
            print("\n❌ Операция отменена пользователем.")
            return False
        except Exception as e:
            print(f"❌ Критическая ошибка: {e}")
            return False
            
    finally:
        try:
            await client.stop()
        except:
            pass

def show_help():
    """Показывает справку"""
    print("\nСкрипт авторизации сессий юзер-ботов")
    print("=" * 50)
    print("\n📋 Использование:")
    print("  python auth_sessions.py [тип] [имя_сессии]")
    print("\n🔧 Параметры:")
    print("  тип          - scanner или buyer")
    print("  имя_сессии   - имя сессии из config.py")
    print("\n📝 Примеры:")
    print("  python auth_sessions.py scanner scan_2")
    print("  python auth_sessions.py buyer buyer_FormulaPobedi")
    print("\n📊 Доступные сессии:")
    print("  Сканеры:")
    for session in SCANNER_SESSIONS:
        print(f"    - {session}")
    print("  Покупатели:")
    for session in BUYER_SESSIONS:
        print(f"    - {session}")
    print()

def main():
    """Главная функция"""
    if len(sys.argv) != 3:
        show_help()
        sys.exit(1)
    
    session_type = sys.argv[1].lower()
    session_name = sys.argv[2]
    
    # Проверяем тип сессии
    if session_type not in ["scanner", "buyer"]:
        print("❌ Неверный тип сессии. Используйте 'scanner' или 'buyer'.")
        show_help()
        sys.exit(1)
    
    # Проверяем существование сессии в конфиге
    if session_type == "scanner":
        if session_name not in SCANNER_SESSIONS:
            print(f"❌ Сессия '{session_name}' не найдена в SCANNER_SESSIONS в config.py")
            print(f"📋 Доступные сканеры: {', '.join(SCANNER_SESSIONS)}")
            sys.exit(1)
    else:  # buyer
        if session_name not in BUYER_SESSIONS:
            print(f"❌ Сессия '{session_name}' не найдена в BUYER_SESSIONS в config.py")
            print(f"📋 Доступные покупатели: {', '.join(BUYER_SESSIONS)}")
            sys.exit(1)
    
    # Запускаем авторизацию
    try:
        result = asyncio.run(auth_session(session_name, session_type))
        
        if result:
            print(f"\n✅ Сессия {session_name} успешно авторизована!")
            print("🚀 Теперь можно запускать основную систему.")
        else:
            print(f"\n❌ Не удалось авторизовать сессию {session_name}.")
            print("🔄 Попробуйте запустить скрипт заново.")
            sys.exit(1)
            
    except KeyboardInterrupt:
        print("\n❌ Операция отменена пользователем.")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Критическая ошибка: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
