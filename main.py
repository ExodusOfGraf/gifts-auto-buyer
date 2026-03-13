import asyncio
import logging
import sys
import os

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(ROOT_DIR, 'data')
APP_DIR = os.path.join(ROOT_DIR, 'app')

os.makedirs(DATA_DIR, exist_ok=True)
sys.path.append(ROOT_DIR)

try:
    from scanners.scanner import main as scanner_main
    from buyers.buyer_v2 import main as buyer_main
    from config_bot.config_bot import main as config_bot_main
except ImportError as e:
    print(f"Ошибка импорта: {e}")
    sys.exit(1)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - [MAIN] - %(levelname)s - %(message)s'
)

async def run_trading_only():
    """Запускает сканеры и покупателей"""
    logging.info("Запуск торговых компонентов: сканеры и покупатели.")
    
    # Передаем путь к data
    scanner_task = asyncio.create_task(scanner_main(workdir=DATA_DIR))
    buyer_task = asyncio.create_task(buyer_main(workdir=DATA_DIR))

    await asyncio.gather(scanner_task, buyer_task)

async def run_project():
    """Запускает все компоненты"""
    logging.info("Запуск проекта: сканеры, покупатели и бот-конфигуратор.")
    
    # Передаем путь к data
    scanner_task = asyncio.create_task(scanner_main(workdir=DATA_DIR))
    buyer_task = asyncio.create_task(buyer_main(workdir=DATA_DIR))
    config_bot_task = asyncio.create_task(config_bot_main())

    await asyncio.gather(scanner_task, buyer_task, config_bot_task)

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
            elif mode == "trading":
                logging.info("Запуск торговых компонентов (сканеры + покупатели).")
                asyncio.run(run_trading_only())
            else:
                logging.warning(f"Неизвестный режим '{mode}'. Доступные режимы: scanner, buyer, config, trading")
                logging.info("Запускаем все компоненты.")
                asyncio.run(run_project())
        else:
            logging.info("Запуск в режиме 'все компоненты' (сканеры + покупатели + бот-конфигуратор).")
            asyncio.run(run_project())

    except (KeyboardInterrupt, SystemExit):
        logging.info("Проект остановлен пользователем.")
    except Exception as e:
        logging.error(f"Критическая ошибка на верхнем уровне: {e}", exc_info=True)