"""
Модуль покупателей NFT-подарков.

Этот модуль содержит:
- Логику покупки подарков с поддержкой стратегий
- Систему управления конфигурациями покупателей
- Механизм "горячего" обновления настроек
- Контроль лимитов и приоритетов
"""

# Lazy imports для избежания циклических зависимостей
def get_buyer_main():
    from .buyer_v2 import main
    return main

def get_buyer_config_manager():
    from .buyer_config import BuyerConfigManager
    return BuyerConfigManager

__all__ = ['get_buyer_main', 'get_buyer_config_manager']
