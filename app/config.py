import os

# API данные с my.telegram.org
API_ID = 28518284
API_HASH = "fcfac1e3d6ff3de090435839e67581e4"

# --- Аккаунты ---
# Имена файлов сессий. Должны быть уникальными.

# Сканеры - аккаунты для поиска новых подарков
# Рекомендуется 2-3 аккаунта для распределения нагрузки

# Для добавления новых сканеров:
# 1. Добавьте имя в список ниже
# 2. Запустите: python main.py scanner
# 3. Авторизуйте аккаунт в терминале
# ВАЖНО: добавляйте по одному аккаунту за раз 
SCANNER_SESSIONS = [
    "alex_goodscan_2",
    "scan_2",
    "scan_3"
]

# Покупатели - аккаунты для покупки подарков
# Для добавления:
# 1. Добавьте имя в список
# 2. Запустите: python main.py buyer
# 3. Авторизуйте аккаунт
# ВАЖНО: добавляйте по одному 
BUYER_SESSIONS = [
    "buyer_FormulaPobedi",
    "buyer_mewoem",
    "buyer_ONL1N9",
    "buyer_markycia",
    "buyer_trahnusuka",

]

#     "buyer_karinalovele" авторизовать не получилось

# --- Каналы и интервалы ---
# ID служебного канала для обмена данными между сканерами и покупателями
# Требования:
# 1. Канал должен быть приватным
# 2. Все аккаунты должны быть добавлены в канал
# 3. ID начинается с -100...
#
# Как узнать ID: переслать сообщение из канала боту @userinfobot
TARGET_CHANNEL_ID = -1002808452688  # Замените на ID ВАШЕГО служебного канала

# Задержка между циклами проверки (секунды)
CHECK_INTERVAL_SECONDS = 1

# Задержка между покупками одного аккаунта (секунды)
# Покупки с разных аккаунтов идут параллельно
SLEEP_AFTER_BUY_SECONDS = 0.2

# --- Настройки сканера ---
# Максимум подарков для отправки за раз
MAX_GIFTS_TO_SEND = 10

# Задержка между отправкой сообщений (секунды)
MESSAGE_SEND_DELAY = 1

# Режим тестирования
# True - все подарки
# False - только лимитированные
SCANNER_TEST_MODE = False

# --- Настройки производительности ---
# Отслеживание времени покупок
ENABLE_PERFORMANCE_TRACKING = False

# Интервал логирования статистики (0 - отключено)
PERFORMANCE_LOG_INTERVAL = 1

# Интервал общей статистики (минуты, 0 - отключено)
SYSTEM_STATS_LOG_INTERVAL_MINUTES = 10

# Файл для сохранения ID обнаруженных подарков
KNOWN_GIFTS_FILE_NAME = "known_gifts.json"

# --- Настройки Telegram бота для управления ---
# Токен бота для управления конфигурацией (получить у @BotFather)
MANAGEMENT_BOT_TOKEN = "7881882057:AAH1B4k_ujAq0yPN8RRBVV_VVYzQeIs-MMc" 

# Администраторы (доступ ко всем ботам)
ADMIN_USERNAMES = [
    "mrhephaestus",     # разраб 
]

# --- Настройки прокси ---
# Примеры:
# PROXY_URL = "socks5://127.0.0.1:1080"
# PROXY_URL = "http://proxy.example.com:8080"
PROXY_URL = None  # None для прямого соединения


# --- Права доступа ---

# Пользователи с доступом к боту управления (username без @)
# Могут управлять только своими ботами из BUYER_OWNERS
ALLOWED_USERS = [
    "FormulaPobedi", 
    "astalavis7",
    "vovn777",
    "dleo_26",
    "mrhephaestus",
    "tursunovu",
    "makar_pp",
    "top9ling",
    "POLERY_YP",
    "griezmann_leyenda",
    "scamshits",
    "wofur",
    "trahnusuka", 
    "markycia",
    "Tr4ster1",
    "paul_durov_friend",
    "ONL1N9",
    "lifeis_toohard",
    "ShavelDurov",
    "Eltonioo",
    "nigggaaaa77",
    "alexxand_er",
    "onspam",
]

# Aliases для пользователей с несколькими username
USERNAME_ALIASES = {
    "wofur": ["scamshits"],  # пользователь wofur также может заходить как scamshits
    # При необходимости можно добавить других пользователей:
    # "alexxand_er": ["другой_nickname"],
}

# Соответствие сессий покупателей и их владельцев
BUYER_OWNERS = {
    "buyer_FormulaPobedi": "FormulaPobedi",
    "buyer_mewoem": "alexxand_er",        
    "buyer_ONL1N9": "ONL1N9",       
    "buyer_markycia": "markycia",
    "buyer_trahnusuka": "trahnusuka", 
    "buyer_trahnusuka": "wofur", 
}

