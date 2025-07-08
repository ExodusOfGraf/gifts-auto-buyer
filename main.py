import asyncio
import logging
import sys
import os

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(ROOT_DIR, 'data')
APP_DIR = os.path.join(ROOT_DIR, 'app')

# Создаем папку data, если ее нет
os.makedirs(DATA_DIR, exist_ok=True)

# Добавляем папку 'app' в путь для импорта
sys.path.append(ROOT_DIR)

try:
    from scanners.scanner import main as scanner_main
    from buyers.buyer_v2 import main as buyer_main  # Используем новую версию покупателя
    from config_bot.config_bot import main as config_bot_main
except ImportError as e:
    print(f"Ошибка импорта. Убедитесь, что main.py находится в корне проекта, а скрипты - в соответствующих папках.")
    print(f"Подробности: {e}")
    sys.exit(1)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - [MAIN] - %(levelname)s - %(message)s'
)

async def run_project():
    #Запускает сканеры и покупателей параллельно
    logging.info("Запуск проекта: сканеры и покупатели.")
    
    # Передаем путь к папке data в наши функции
    scanner_task = asyncio.create_task(scanner_main(workdir=DATA_DIR))
    buyer_task = asyncio.create_task(buyer_main(workdir=DATA_DIR))

    await asyncio.gather(scanner_task, buyer_task)

if __name__ == "__main__":
    try:
        if len(sys.argv) > 1:
            mode = sys.argv[1].lower()
            if mode == "scanner":
                logging.info("Запуск в режиме 'только сканеры'.")
                # Передаем путь к папке data
                asyncio.run(scanner_main(workdir=DATA_DIR))
            elif mode == "buyer":
                logging.info("Запуск в режиме 'только покупатели'.")
                # Передаем путь к папке data
                asyncio.run(buyer_main(workdir=DATA_DIR))
            elif mode == "config":
                logging.info("Запуск бота управления конфигурацией.")
                asyncio.run(config_bot_main())
            else:
                logging.warning(f"Неизвестный режим '{mode}'. Запускаем все компоненты.")
                asyncio.run(run_project())
        else:
            logging.info("Запуск в режиме 'все компоненты'.")
            asyncio.run(run_project())

    except (KeyboardInterrupt, SystemExit):
        logging.info("Проект остановлен пользователем.")
    except Exception as e:
        logging.error(f"Критическая ошибка на верхнем уровне: {e}", exc_info=True)