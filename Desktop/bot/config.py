import os
import logging
from pathlib import Path
from dotenv import load_dotenv

# Загрузка переменных окружения из .env файла
load_dotenv()


class Config:
    """Конфигурация бота"""
    
    # === Основные настройки ===
    BOT_TOKEN = os.getenv("BOT_TOKEN")
    if not BOT_TOKEN:
        raise ValueError("BOT_TOKEN не найден в .env файле!")
    
    # === Пути ===
    BASE_DIR = Path(__file__).parent
    DB_PATH = BASE_DIR / os.getenv("DB_PATH", "bot_data.db")
    
    # === Настройки бота ===
    MAX_WARNS = int(os.getenv("MAX_WARNS", 3))
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
    DEBUG = os.getenv("DEBUG", "False").lower() == "true"
    
    # === Настройки мута ===
    MUTE_DURATIONS = {
        "15m": int(os.getenv("MUTE_15M", 15)),
        "1h": int(os.getenv("MUTE_1H", 60)),
        "24h": int(os.getenv("MUTE_24H", 1440)),
        "7d": int(os.getenv("MUTE_7D", 10080))
    }
    
    MUTE_LABELS = {
        0: "навсегда",
        15: "15 минут",
        60: "1 час",
        1440: "24 часа",
        10080: "7 дней"
    }
    
    # === Приветствия ===
    DEFAULT_WELCOME = os.getenv("DEFAULT_WELCOME", "Привет, {name}! Добро пожаловать в чат! 🌟")
    
    # === Настройки администрирования ===
    ALLOW_BOT_ADMINS = os.getenv("ALLOW_BOT_ADMINS", "True").lower() == "true"
    
    # === Ограничения ===
    MAX_MESSAGE_LENGTH = int(os.getenv("MAX_MESSAGE_LENGTH", 4096))
    MAX_REASON_LENGTH = int(os.getenv("MAX_REASON_LENGTH", 500))
    
    # === Настройки пользовательских команд ===
    MAX_CUSTOM_COMMANDS = int(os.getenv("MAX_CUSTOM_COMMANDS", 50))
    MAX_COMMAND_NAME_LEN = int(os.getenv("MAX_COMMAND_NAME_LEN", 50))
    MAX_COMMAND_RESPONSE_LEN = int(os.getenv("MAX_COMMAND_RESPONSE_LEN", 1000))
    
    # === Часовой пояс ===
    TIMEZONE = os.getenv("TIMEZONE", "Europe/Moscow")
    
    # === Rate limiting ===
    RATE_LIMIT_ENABLED = os.getenv("RATE_LIMIT_ENABLED", "False").lower() == "true"
    RATE_LIMIT_MESSAGES = int(os.getenv("RATE_LIMIT_MESSAGES", 10))
    RATE_LIMIT_PERIOD = int(os.getenv("RATE_LIMIT_PERIOD", 60))
    
    # === Callback префиксы ===
    CALLBACK_PREFIXES = {
        "chats_list": "chats_list",
        "menu": "menu",
        "ban_menu": "ban_menu",
        "mute_menu": "mute_menu",
        "stats": "stats",
        "settings": "settings",
        "access": "access",
        "set_welcome": "set_welcome",
        "toggle_welcome": "toggle_welcome",
        "add_admin": "add_admin",
        "del_admin": "del_admin",
        "do_ban": "do_ban",
        "do_unban": "do_unban",
        "do_mute": "do_mute",
        "do_unmute": "do_unmute",
        "confirm_ban": "confirm_ban",
        "confirm_unban": "confirm_unban",
        "confirm_mute": "confirm_mute",
        "confirm_unmute": "confirm_unmute",
        "confirm_add_admin": "confirm_add_admin",
        "confirm_del_admin": "confirm_del_admin"
    }
    
    # === Настройки логирования ===
    LOGGING_CONFIG = {
        "format": "%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        "datefmt": "%Y-%m-%d %H:%M:%S",
        "level": getattr(logging, LOG_LEVEL.upper(), logging.INFO)
    }
    
    @classmethod
    def validate(cls):
        """Проверка корректности конфигурации"""
        errors = []
        
        if not cls.BOT_TOKEN:
            errors.append("BOT_TOKEN не установлен")
        
        if cls.MAX_WARNS < 1:
            errors.append("MAX_WARNS должен быть больше 0")
        
        if cls.MAX_MESSAGE_LENGTH < 100:
            errors.append("MAX_MESSAGE_LENGTH слишком маленький")
        
        if cls.MAX_CUSTOM_COMMANDS < 1:
            errors.append("MAX_CUSTOM_COMMANDS должен быть больше 0")
        
        if errors:
            raise ValueError(f"Ошибки конфигурации:\n" + "\n".join(errors))
        
        return True
    
    @classmethod
    def display(cls):
        """Отображение текущей конфигурации (без секретов)"""
        print("=" * 50)
        print("Текущая конфигурация:")
        print("=" * 50)
        print(f"BOT_TOKEN: {'✅ установлен' if cls.BOT_TOKEN else '❌ не установлен'}")
        print(f"DB_PATH: {cls.DB_PATH}")
        print(f"MAX_WARNS: {cls.MAX_WARNS}")
        print(f"LOG_LEVEL: {cls.LOG_LEVEL}")
        print(f"DEBUG: {cls.DEBUG}")
        print(f"MUTE_DURATIONS: {cls.MUTE_DURATIONS}")
        print(f"ALLOW_BOT_ADMINS: {cls.ALLOW_BOT_ADMINS}")
        print(f"MAX_CUSTOM_COMMANDS: {cls.MAX_CUSTOM_COMMANDS}")
        print(f"RATE_LIMIT_ENABLED: {cls.RATE_LIMIT_ENABLED}")
        print(f"TIMEZONE: {cls.TIMEZONE}")
        print("=" * 50)


# Автоматическая валидация при импорте
if __name__ != "__main__":
    try:
        Config.validate()
    except ValueError as e:
        print(f"⚠️ Внимание: {e}")
        print("Бот может работать некорректно!")