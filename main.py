# main.py

import asyncio
import logging
import sys
import os

# Добавляем папку 'app' в путь для импорта, чтобы найти наши модули
# Это нужно, так как main.py находится на уровень выше
sys.path.append(os.path.join(os.path.dirname(__file__), 'app'))

# Теперь мы можем импортировать функции main из наших скриптов
try:
    from app import scanner, buyer
except ImportError as e:
    print(f"Ошибка импорта. Убедитесь, что main.py находится в корне проекта, а скрипты - в папке 'app'.")
    print(f"Подробности: {e}")
    sys.exit(1)


# Настройка базового логирования для главного скрипта
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - [MAIN] - %(levelname)s - %(message)s'
)

async def run_project():
    """
    Запускает сканеры и покупателей параллельно.
    """
    logging.info("Запуск проекта: сканеры и покупатели.")
    
    #  задачи для сканеров и покупателей
    scanner_task = asyncio.create_task(scanner.main())
    buyer_task = asyncio.create_task(buyer.main())

    # Ожидаем завершения обеих задач
    # Если одна из них завершится (например, из-за ошибки), gather тоже завершится.
    await asyncio.gather(scanner_task, buyer_task)


if __name__ == "__main__":
    try:
        # python main.py -> запустить всё
        # python main.py scanner -> запустить только сканер
        # python main.py buyer -> запустить только покупателей
        
        if len(sys.argv) > 1:
            mode = sys.argv[1].lower()
            if mode == "scanner":
                logging.info("Запуск в режиме 'только сканеры'.")
                asyncio.run(scanner.main())
            elif mode == "buyer":
                logging.info("Запуск в режиме 'только покупатели'.")
                asyncio.run(buyer.main())
            else:
                logging.warning(f"Неизвестный режим '{mode}'. Запускаем все компоненты.")
                asyncio.run(run_project())
        else:
            # Режим по умолчанию: запустить все
            logging.info("Запуск в режиме 'все компоненты'.")
            asyncio.run(run_project())

    except (KeyboardInterrupt, SystemExit):
        logging.info("Проект остановлен пользователем.")
    except Exception as e:
        logging.error(f"Критическая ошибка на верхнем уровне: {e}", exc_info=True)