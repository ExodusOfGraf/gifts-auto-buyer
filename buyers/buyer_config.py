import json
import os
from dataclasses import dataclass, asdict
from typing import Dict, List, Optional
from datetime import datetime

@dataclass
class BuyingStrategy:
    """Стратегия покупки для определенного диапазона цен"""
    min_price: int  # Минимальная цена подарка
    max_price: int  # Максимальная цена подарка
    max_spend: int  # Максимум звезд для трат на этой стратегии
    priority: int   # Приоритет (1 - самый высокий)
    current_spent: int = 0  # Текущая потраченная сумма
    
    def can_buy(self, price: int) -> bool:
        """Проверяет, можно ли купить подарок по этой стратегии"""
        return (self.min_price <= price <= self.max_price and 
                self.current_spent + price <= self.max_spend)
    
    def add_purchase(self, price: int):
        """Добавляет покупку к текущим тратам"""
        self.current_spent += price
    
    def reset_spent(self):
        """Сбрасывает текущие траты"""
        self.current_spent = 0

@dataclass
class BuyerConfig:
    """Конфигурация для одного покупателя"""
    session_name: str
    strategies: List[BuyingStrategy]
    enabled: bool = True
    auto_reset_daily: bool = True  # Автоматически сбрасывать траты каждый день
    last_reset: str = ""  # Дата последнего сброса
    
    def get_best_strategy(self, price: int) -> Optional[BuyingStrategy]:
        """Возвращает лучшую стратегию для покупки по цене"""
        available_strategies = [s for s in self.strategies if s.can_buy(price)]
        if not available_strategies:
            return None
        # Сортируем по приоритету (чем меньше число, тем выше приоритет)
        return sorted(available_strategies, key=lambda x: x.priority)[0]
    
    def should_reset_daily(self) -> bool:
        """Проверяет, нужно ли сбросить ежедневные траты"""
        if not self.auto_reset_daily:
            return False
        
        today = datetime.now().strftime("%Y-%m-%d")
        return self.last_reset != today
    
    def reset_daily_spending(self):
        """Сбрасывает ежедневные траты"""
        for strategy in self.strategies:
            strategy.reset_spent()
        self.last_reset = datetime.now().strftime("%Y-%m-%d")

class BuyerConfigManager:
    """Менеджер конфигураций покупателей"""
    
    def __init__(self, config_file: str):
        self.config_file = config_file
        self.configs: Dict[str, BuyerConfig] = {}
        self.load_configs()
    
    def load_configs(self):
        """Загружает конфигурации из файла"""
        if not os.path.exists(self.config_file):
            self.configs = {}
            return
        
        try:
            with open(self.config_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            self.configs = {}
            for session_name, config_data in data.items():
                strategies = []
                for strategy_data in config_data.get('strategies', []):
                    strategies.append(BuyingStrategy(**strategy_data))
                
                config = BuyerConfig(
                    session_name=session_name,
                    strategies=strategies,
                    enabled=config_data.get('enabled', True),
                    auto_reset_daily=config_data.get('auto_reset_daily', True),
                    last_reset=config_data.get('last_reset', '')
                )
                self.configs[session_name] = config
        except Exception as e:
            print(f"Ошибка загрузки конфигурации: {e}")
            self.configs = {}
    
    def save_configs(self):
        """Сохраняет конфигурации в файл"""
        data = {}
        for session_name, config in self.configs.items():
            data[session_name] = {
                'strategies': [asdict(s) for s in config.strategies],
                'enabled': config.enabled,
                'auto_reset_daily': config.auto_reset_daily,
                'last_reset': config.last_reset
            }
        
        with open(self.config_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    
    def get_config(self, session_name: str) -> Optional[BuyerConfig]:
        """Получает конфигурацию для сессии"""
        return self.configs.get(session_name)
    
    def set_config(self, session_name: str, config: BuyerConfig):
        """Устанавливает конфигурацию для сессии"""
        self.configs[session_name] = config
        self.save_configs()
    
    def create_default_config(self, session_name: str) -> BuyerConfig:
        """Создает дефолтную конфигурацию"""
        default_strategies = [
            BuyingStrategy(min_price=1000, max_price=10000, max_spend=5000, priority=1),
            BuyingStrategy(min_price=100, max_price=999, max_spend=2000, priority=2),
            BuyingStrategy(min_price=1, max_price=99, max_spend=1000, priority=3)
        ]
        
        config = BuyerConfig(
            session_name=session_name,
            strategies=default_strategies
        )
        
        self.set_config(session_name, config)
        return config
    
    def update_purchase(self, session_name: str, price: int) -> bool:
        """Обновляет информацию о покупке"""
        config = self.get_config(session_name)
        if not config:
            return False
        
        # Проверяем, нужно ли сбросить ежедневные траты
        if config.should_reset_daily():
            config.reset_daily_spending()
        
        strategy = config.get_best_strategy(price)
        if not strategy:
            return False
        
        strategy.add_purchase(price)
        self.save_configs()
        return True
    
    def get_spending_stats(self, session_name: str) -> Dict:
        """Получает статистику трат для сессии"""
        config = self.get_config(session_name)
        if not config:
            return {}
        
        stats = {
            'session_name': session_name,
            'enabled': config.enabled,
            'strategies': []
        }
        
        for strategy in config.strategies:
            stats['strategies'].append({
                'price_range': f"{strategy.min_price}-{strategy.max_price}",
                'max_spend': strategy.max_spend,
                'current_spent': strategy.current_spent,
                'remaining': strategy.max_spend - strategy.current_spent,
                'priority': strategy.priority
            })
        
        return stats
