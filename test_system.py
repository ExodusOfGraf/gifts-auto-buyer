#!/usr/bin/env python3
"""
Тестирование системы управления конфигурацией покупателей подарков
"""

import os
import sys
import json
from pathlib import Path

# Добавляем корень проекта в путь
ROOT_DIR = Path(__file__).parent
sys.path.append(str(ROOT_DIR))

from buyers.buyer_config import BuyerConfigManager, BuyingStrategy

def test_buyer_config_system():
    """Тестирует основные функции системы конфигурации"""
    print("🧪 Запуск тестирования системы конфигурации...")
    
    # Создаем временный файл конфигурации
    test_config_file = ROOT_DIR / "data" / "test_buyer_configs.json"
    test_config_file.parent.mkdir(exist_ok=True)
    
    try:
        # Инициализируем менеджер конфигураций
        config_manager = BuyerConfigManager(str(test_config_file))
        
        # Тест 1: Создание дефолтной конфигурации
        print("\n1️⃣ Тестируем создание дефолтной конфигурации...")
        test_session = "test_buyer_session"
        config = config_manager.create_default_config(test_session)
        
        assert config.session_name == test_session
        assert config.enabled == True
        assert len(config.strategies) == 3
        print("✅ Дефолтная конфигурация создана успешно")
        
        # Тест 2: Проверка стратегий
        print("\n2️⃣ Тестируем стратегии покупки...")
        
        # Тестируем подарок за 1500 звезд (должен подойти под стратегию 1)
        strategy = config.get_best_strategy(1500)
        assert strategy is not None
        assert strategy.min_price <= 1500 <= strategy.max_price
        assert strategy.priority == 1
        print("✅ Стратегия для дорогого подарка найдена")
        
        # Тестируем подарок за 500 звезд (должен подойти под стратегию 2)
        strategy = config.get_best_strategy(500)
        assert strategy is not None
        assert strategy.min_price <= 500 <= strategy.max_price
        assert strategy.priority == 2
        print("✅ Стратегия для среднего подарка найдена")
        
        # Тестируем подарок за 50 звезд (должен подойти под стратегию 3)
        strategy = config.get_best_strategy(50)
        assert strategy is not None
        assert strategy.min_price <= 50 <= strategy.max_price
        assert strategy.priority == 3
        print("✅ Стратегия для дешевого подарка найдена")
        
        # Тест 3: Проверка лимитов трат
        print("\n3️⃣ Тестируем лимиты трат...")
        
        # Симулируем покупки
        initial_spent = config.strategies[0].current_spent
        success = config_manager.update_purchase(test_session, 1000)
        assert success == True
        
        updated_config = config_manager.get_config(test_session)
        assert updated_config is not None
        assert updated_config.strategies[0].current_spent == initial_spent + 1000
        print("✅ Покупка записана, лимиты обновлены")
        
        # Тест 4: Проверка статистики
        print("\n4️⃣ Тестируем статистику...")
        stats = config_manager.get_spending_stats(test_session)
        assert stats['session_name'] == test_session
        assert stats['enabled'] == True
        assert len(stats['strategies']) == 3
        print("✅ Статистика формируется корректно")
        
        # Тест 5: Сброс лимитов
        print("\n5️⃣ Тестируем сброс лимитов...")
        updated_config.reset_daily_spending()
        config_manager.set_config(test_session, updated_config)
        
        final_config = config_manager.get_config(test_session)
        assert final_config is not None
        assert final_config.strategies[0].current_spent == 0
        print("✅ Лимиты сброшены успешно")
        
        print("\n🎉 Все тесты пройдены успешно!")
        return True
        
    except Exception as e:
        print(f"\n❌ Ошибка в тесте: {e}")
        return False
        
    finally:
        # Удаляем тестовый файл
        if test_config_file.exists():
            test_config_file.unlink()

def test_config_file_format():
    """Тестирует формат конфигурационного файла"""
    print("\n📄 Тестируем формат конфигурационного файла...")
    
    test_file = ROOT_DIR / "data" / "format_test.json"
    test_file.parent.mkdir(exist_ok=True)
    
    try:
        manager = BuyerConfigManager(str(test_file))
        
        # Создаем несколько конфигураций
        sessions = ["buyer_test1", "buyer_test2", "buyer_test3"]
        for session in sessions:
            manager.create_default_config(session)
        
        # Проверяем, что файл создался и имеет правильный формат
        assert test_file.exists()
        
        with open(test_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        assert len(data) == len(sessions)
        for session in sessions:
            assert session in data
            assert 'strategies' in data[session]
            assert 'enabled' in data[session]
            assert len(data[session]['strategies']) == 3
        
        print("✅ Формат конфигурационного файла корректный")
        return True
        
    except Exception as e:
        print(f"❌ Ошибка формата: {e}")
        return False
        
    finally:
        if test_file.exists():
            test_file.unlink()

if __name__ == "__main__":
    print("🎁 Тестирование системы управления покупкой подарков")
    print("=" * 60)
    
    all_tests_passed = True
    
    # Запускаем тесты
    all_tests_passed &= test_buyer_config_system()
    all_tests_passed &= test_config_file_format()
    
    print("\n" + "=" * 60)
    if all_tests_passed:
        print("🎉 ВСЕ ТЕСТЫ ПРОЙДЕНЫ! Система готова к использованию.")
        print("\nДля запуска:")
        print("1. Настройте токен бота в config.py")
        print("2. Запустите покупателей: python main.py buyer")
        print("3. Запустите бота управления: python main.py config")
    else:
        print("❌ НЕКОТОРЫЕ ТЕСТЫ НЕ ПРОЙДЕНЫ! Проверьте ошибки выше.")
        sys.exit(1)
