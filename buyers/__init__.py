"""
Модуль покупателей NFT-подарков.

Содержит:
- Логику покупки с поддержкой стратегий
- Управление конфигурациями
- Обновление настроек без перезапуска
- Контроль лимитов и приоритетов
"""

# Lazy imports
def get_buyer_main():
    from .buyer_v2 import main
    return main

def get_buyer_config_manager():
    from .buyer_config import BuyerConfigManager
    return BuyerConfigManager

__all__ = ['get_buyer_main', 'get_buyer_config_manager']
