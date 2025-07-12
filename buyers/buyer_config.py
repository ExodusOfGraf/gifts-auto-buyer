import json
import os
from dataclasses import dataclass, asdict
from typing import Dict, List, Optional
from datetime import datetime

@dataclass
class BuyingProfile:
    """Профиль закупки - набор из 4 стратегий с приоритетами"""
    name: str  # Название профиля
    strategy_1: 'BuyingStrategy'  # Приоритет 1 (самый высокий)
    strategy_2: 'BuyingStrategy'  # Приоритет 2  
    strategy_3: 'BuyingStrategy'  # Приоритет 3
    strategy_4: 'BuyingStrategy'  # Приоритет 4 (самый низкий)
    
    def get_strategies(self) -> List['BuyingStrategy']:
        """Возвращает все стратегии профиля отсортированные по приоритету"""
        return [self.strategy_1, self.strategy_2, self.strategy_3, self.strategy_4]
    
    def get_best_strategy(self, price: int) -> Optional['BuyingStrategy']:
        """Возвращает лучшую стратегию для покупки по цене (с учетом приоритета)"""
        strategies = self.get_strategies()
        for strategy in strategies:  # Уже отсортированы по приоритету
            if strategy.can_buy(price):
                return strategy
        return None

@dataclass
class BuyingStrategy:
    """Стратегия покупки для определенного диапазона цен"""
    min_price: int  # Минимальная цена подарка
    max_price: int  # Максимальная цена подарка
    max_spend: int  # Максимум звезд для трат на этой стратегии
    priority: int   # Приоритет (1 - самый высокий)
    current_spent: int = 0  # Текущая потраченная сумма
    send_to_self: bool = True  # True - отправлять себе, False - в канал
    target_channel_id: int = 0  # ID канала для отправки (если send_to_self = False)
    
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
    strategies: List[BuyingStrategy]  # Оставляем для обратной совместимости
    profiles: Dict[str, BuyingProfile]  # Новые профили закупки
    active_profile: str  # Название активного профиля
    enabled: bool = True
    auto_reset_daily: bool = True  # Автоматически сбрасывать траты каждый день
    last_reset: str = ""  # Дата последнего сброса
    owner_id: int = 0  # ID владельца бота (для прав доступа)
    
    def get_active_profile(self) -> Optional[BuyingProfile]:
        """Возвращает активный профиль"""
        return self.profiles.get(self.active_profile)
    
    def get_best_strategy(self, price: int) -> Optional[BuyingStrategy]:
        """Возвращает лучшую стратегию для покупки по цене"""
        # Сначала пробуем использовать активный профиль
        active_profile = self.get_active_profile()
        if active_profile:
            return active_profile.get_best_strategy(price)
        
        # Если профиля нет, используем старую систему стратегий
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
        # Сбрасываем траты в активном профиле
        active_profile = self.get_active_profile()
        if active_profile:
            for strategy in active_profile.get_strategies():
                strategy.reset_spent()
        
        # Также сбрасываем в старых стратегиях для обратной совместимости
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
                
                # Загружаем профили если они есть
                profiles = {}
                profiles_data = config_data.get('profiles', {})
                for profile_name, profile_data in profiles_data.items():
                    # Загружаем стратегии с новыми полями отправки
                    strategy_1_data = profile_data['strategy_1']
                    strategy_1 = BuyingStrategy(**strategy_1_data)
                    
                    strategy_2_data = profile_data['strategy_2']
                    strategy_2 = BuyingStrategy(**strategy_2_data)
                    
                    strategy_3_data = profile_data['strategy_3']
                    strategy_3 = BuyingStrategy(**strategy_3_data)
                    
                    strategy_4_data = profile_data['strategy_4']
                    strategy_4 = BuyingStrategy(**strategy_4_data)
                    
                    profiles[profile_name] = BuyingProfile(
                        name=profile_name,
                        strategy_1=strategy_1,
                        strategy_2=strategy_2,
                        strategy_3=strategy_3,
                        strategy_4=strategy_4
                    )
                
                config = BuyerConfig(
                    session_name=session_name,
                    strategies=strategies,
                    profiles=profiles,
                    active_profile=config_data.get('active_profile', ''),
                    enabled=config_data.get('enabled', True),
                    auto_reset_daily=config_data.get('auto_reset_daily', True),
                    last_reset=config_data.get('last_reset', ''),
                    owner_id=config_data.get('owner_id', 0)
                )
                self.configs[session_name] = config
        except Exception as e:
            print(f"Ошибка загрузки конфигурации: {e}")
            self.configs = {}
    
    def save_configs(self):
        """Сохраняет конфигурации в файл"""
        data = {}
        for session_name, config in self.configs.items():
            profiles_data = {}
            for profile_name, profile in config.profiles.items():
                profiles_data[profile_name] = {
                    'strategy_1': asdict(profile.strategy_1),
                    'strategy_2': asdict(profile.strategy_2),
                    'strategy_3': asdict(profile.strategy_3),
                    'strategy_4': asdict(profile.strategy_4)
                }
            
            data[session_name] = {
                'strategies': [asdict(s) for s in config.strategies],
                'profiles': profiles_data,
                'active_profile': config.active_profile,
                'enabled': config.enabled,
                'auto_reset_daily': config.auto_reset_daily,
                'last_reset': config.last_reset,
                'owner_id': config.owner_id
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
    
    def create_default_config(self, session_name: str, owner_id: int = 0) -> BuyerConfig:
        """Создает дефолтную конфигурацию"""
        default_strategies = [
            BuyingStrategy(min_price=1000, max_price=10000, max_spend=5000, priority=1),
            BuyingStrategy(min_price=100, max_price=999, max_spend=2000, priority=2),
            BuyingStrategy(min_price=1, max_price=99, max_spend=1000, priority=3)
        ]
        
        # Создаем дефолтный профиль
        default_profile = BuyingProfile(
            name="default",
            strategy_1=BuyingStrategy(min_price=1000, max_price=10000, max_spend=5000, priority=1, send_to_self=True, target_channel_id=0),
            strategy_2=BuyingStrategy(min_price=500, max_price=999, max_spend=3000, priority=2, send_to_self=True, target_channel_id=0),
            strategy_3=BuyingStrategy(min_price=100, max_price=499, max_spend=2000, priority=3, send_to_self=True, target_channel_id=0),
            strategy_4=BuyingStrategy(min_price=1, max_price=99, max_spend=1000, priority=4, send_to_self=True, target_channel_id=0)
        )
        
        config = BuyerConfig(
            session_name=session_name,
            strategies=default_strategies,
            profiles={"default": default_profile},
            active_profile="default",
            owner_id=owner_id
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

    def has_access(self, session_name: str, user_id: int) -> bool:
        """Проверяет, имеет ли пользователь доступ к настройкам сессии"""
        # Импортируем здесь, чтобы избежать циклических импортов
        try:
            from app.config import SUPER_ADMINS, BUYER_OWNERS
            
            # Суперадмины имеют доступ ко всем сессиям
            if user_id in SUPER_ADMINS:
                return True
            
            # Проверяем права владельца по BUYER_OWNERS
            if BUYER_OWNERS.get(session_name) == user_id:
                return True
        except ImportError:
            pass  # Если нет config файла, используем старую логику
        
        config = self.get_config(session_name)
        if not config:
            return False
        
        # Если owner_id не установлен (старые конфиги), разрешаем доступ
        if config.owner_id == 0:
            return True
        
        return config.owner_id == user_id
    
    def create_profile(self, session_name: str, profile_name: str, user_id: int) -> bool:
        """Создает новый профиль для сессии"""
        if not self.has_access(session_name, user_id):
            return False
        
        config = self.get_config(session_name)
        if not config:
            return False
        
        if len(config.profiles) >= 4:
            return False  # Максимум 4 профиля
        
        new_profile = BuyingProfile(
            name=profile_name,
            strategy_1=BuyingStrategy(min_price=1000, max_price=10000, max_spend=5000, priority=1, send_to_self=True, target_channel_id=0),
            strategy_2=BuyingStrategy(min_price=500, max_price=999, max_spend=3000, priority=2, send_to_self=True, target_channel_id=0),
            strategy_3=BuyingStrategy(min_price=100, max_price=499, max_spend=2000, priority=3, send_to_self=True, target_channel_id=0),
            strategy_4=BuyingStrategy(min_price=1, max_price=99, max_spend=1000, priority=4, send_to_self=True, target_channel_id=0)
        )
        
        config.profiles[profile_name] = new_profile
        self.set_config(session_name, config)
        return True
    
    def delete_profile(self, session_name: str, profile_name: str, user_id: int) -> bool:
        """Удаляет профиль"""
        if not self.has_access(session_name, user_id):
            return False
        
        config = self.get_config(session_name)
        if not config or profile_name not in config.profiles:
            return False
        
        if profile_name == "default":
            return False  # Нельзя удалить дефолтный профиль
        
        # Если удаляется активный профиль, переключаемся на default
        if config.active_profile == profile_name:
            config.active_profile = "default"
        
        del config.profiles[profile_name]
        self.set_config(session_name, config)
        return True
    
    def set_active_profile(self, session_name: str, profile_name: str, user_id: int) -> bool:
        """Устанавливает активный профиль"""
        if not self.has_access(session_name, user_id):
            return False
        
        config = self.get_config(session_name)
        if not config or profile_name not in config.profiles:
            return False
        
        config.active_profile = profile_name
        self.set_config(session_name, config)
        return True
    
    def update_profile_strategy(self, session_name: str, profile_name: str, 
                              strategy_num: int, strategy: BuyingStrategy, user_id: int) -> bool:
        """Обновляет стратегию в профиле"""
        if not self.has_access(session_name, user_id):
            return False
        
        config = self.get_config(session_name)
        if not config or profile_name not in config.profiles:
            return False
        
        profile = config.profiles[profile_name]
        
        if strategy_num == 1:
            profile.strategy_1 = strategy
        elif strategy_num == 2:
            profile.strategy_2 = strategy
        elif strategy_num == 3:
            profile.strategy_3 = strategy
        elif strategy_num == 4:
            profile.strategy_4 = strategy
        else:
            return False
        
        self.set_config(session_name, config)
        return True
