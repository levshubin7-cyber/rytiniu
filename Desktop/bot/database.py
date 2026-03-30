import sqlite3
import logging
from contextlib import contextmanager
from typing import Optional, List, Dict, Any
from datetime import datetime
from config import Config

logger = logging.getLogger(__name__)


class Database:
    """Класс для работы с базой данных"""
    
    def __init__(self, db_path: str = None):
        self.db_path = db_path or str(Config.DB_PATH)
        self._init_db()
    
    @contextmanager
    def get_connection(self):
        """Контекстный менеджер для соединения с БД"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            conn.close()
    
    def _init_db(self):
        """Инициализация базы данных"""
        with self.get_connection() as conn:
            # Основные таблицы
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS chats (
                    chat_id          INTEGER PRIMARY KEY,
                    title            TEXT    NOT NULL,
                    welcome_message  TEXT    DEFAULT NULL,
                    welcome_enabled  INTEGER DEFAULT 0,
                    owner_id         INTEGER DEFAULT NULL,
                    clean_system_messages INTEGER DEFAULT 1
                );
                
                CREATE TABLE IF NOT EXISTS user_stats (
                    chat_id       INTEGER NOT NULL,
                    user_id       INTEGER NOT NULL,
                    username      TEXT    DEFAULT '',
                    first_name    TEXT    DEFAULT '',
                    message_count INTEGER DEFAULT 0,
                    join_date     TEXT    NOT NULL,
                    PRIMARY KEY (chat_id, user_id)
                );
                
                CREATE TABLE IF NOT EXISTS chat_stats (
                    chat_id        INTEGER PRIMARY KEY,
                    total_messages INTEGER DEFAULT 0,
                    last_updated   TEXT
                );
                
                CREATE TABLE IF NOT EXISTS warns (
                    chat_id    INTEGER NOT NULL,
                    user_id    INTEGER NOT NULL,
                    count      INTEGER DEFAULT 0,
                    reasons    TEXT    DEFAULT '',
                    PRIMARY KEY (chat_id, user_id)
                );
                
                CREATE TABLE IF NOT EXISTS bot_admins (
                    user_id    INTEGER NOT NULL,
                    chat_id    INTEGER NOT NULL,
                    granted_by INTEGER NOT NULL,
                    granted_at TEXT    NOT NULL,
                    PRIMARY KEY (user_id, chat_id)
                );
                
                CREATE TABLE IF NOT EXISTS custom_commands (
                    chat_id    INTEGER NOT NULL,
                    command    TEXT    NOT NULL,
                    response   TEXT    NOT NULL,
                    created_by INTEGER NOT NULL,
                    created_at TEXT    NOT NULL,
                    PRIMARY KEY (chat_id, command)
                );
            """)
            
            # Миграции: добавляем недостающие колонки
            migrations = [
                ("ALTER TABLE chats ADD COLUMN owner_id INTEGER DEFAULT NULL", "owner_id"),
                ("ALTER TABLE chats ADD COLUMN clean_system_messages INTEGER DEFAULT 1", "clean_system_messages"),
                ("ALTER TABLE user_stats ADD COLUMN username TEXT DEFAULT ''", "username"),
                ("ALTER TABLE user_stats ADD COLUMN first_name TEXT DEFAULT ''", "first_name"),
            ]
            
            for sql, column in migrations:
                try:
                    conn.execute(sql)
                    logger.info(f"Миграция: добавлена колонка {column}")
                except sqlite3.OperationalError:
                    pass  # Колонка уже существует
            
            logger.info("✅ База данных инициализирована")
    
    # === Методы для работы с чатами ===
    
    def register_chat(self, chat_id: int, title: str, owner_id: int = None):
        """Регистрация чата"""
        with self.get_connection() as conn:
            conn.execute(
                """INSERT OR IGNORE INTO chats (chat_id, title, owner_id, clean_system_messages) 
                   VALUES (?, ?, ?, 1)""",
                (chat_id, title, owner_id)
            )
            conn.execute(
                "UPDATE chats SET title = ?, owner_id = COALESCE(?, owner_id) WHERE chat_id = ?",
                (title, owner_id, chat_id)
            )
            conn.execute(
                "INSERT OR IGNORE INTO chat_stats (chat_id, total_messages, last_updated) VALUES (?, 0, ?)",
                (chat_id, datetime.now().isoformat())
            )
            logger.info(f"Чат зарегистрирован: {chat_id} ({title}), владелец: {owner_id}")
    
    def get_chat(self, chat_id: int) -> Optional[Dict[str, Any]]:
        """Получение информации о чате"""
        with self.get_connection() as conn:
            return conn.execute(
                "SELECT * FROM chats WHERE chat_id = ?",
                (chat_id,)
            ).fetchone()
    
    def get_all_chats(self) -> List[Dict[str, Any]]:
        """Получение всех чатов"""
        with self.get_connection() as conn:
            return conn.execute("SELECT * FROM chats ORDER BY chat_id").fetchall()
    
    def set_welcome_message(self, chat_id: int, text: str, enabled: bool = True):
        """Установка приветственного сообщения"""
        with self.get_connection() as conn:
            conn.execute(
                "UPDATE chats SET welcome_message = ?, welcome_enabled = ? WHERE chat_id = ?",
                (text, 1 if enabled else 0, chat_id)
            )
            logger.info(f"Приветствие установлено для чата {chat_id}")
    
    def toggle_welcome(self, chat_id: int, enabled: bool):
        """Включение/выключение приветствия"""
        with self.get_connection() as conn:
            conn.execute(
                "UPDATE chats SET welcome_enabled = ? WHERE chat_id = ?",
                (1 if enabled else 0, chat_id)
            )
            logger.info(f"Приветствие {'включено' if enabled else 'выключено'} для чата {chat_id}")
    
    def set_chat_owner(self, chat_id: int, owner_id: int):
        """Установка владельца чата"""
        with self.get_connection() as conn:
            conn.execute(
                "UPDATE chats SET owner_id = ? WHERE chat_id = ?",
                (owner_id, chat_id)
            )
            logger.info(f"Владелец чата {chat_id} установлен: {owner_id}")
    
    def get_chat_owner(self, chat_id: int) -> Optional[int]:
        """Получение владельца чата"""
        with self.get_connection() as conn:
            row = conn.execute(
                "SELECT owner_id FROM chats WHERE chat_id = ?",
                (chat_id,)
            ).fetchone()
            return row["owner_id"] if row else None
    
    def set_clean_system_messages(self, chat_id: int, enabled: bool):
        """Включение/выключение очистки системных сообщений"""
        with self.get_connection() as conn:
            try:
                conn.execute("ALTER TABLE chats ADD COLUMN clean_system_messages INTEGER DEFAULT 1")
            except sqlite3.OperationalError:
                pass
            
            conn.execute(
                "UPDATE chats SET clean_system_messages = ? WHERE chat_id = ?",
                (1 if enabled else 0, chat_id)
            )
            logger.info(f"Очистка системных сообщений для чата {chat_id}: {'включена' if enabled else 'выключена'}")
    
    def get_clean_system_messages(self, chat_id: int) -> bool:
        """Получение статуса очистки системных сообщений"""
        with self.get_connection() as conn:
            row = conn.execute(
                "SELECT clean_system_messages FROM chats WHERE chat_id = ?",
                (chat_id,)
            ).fetchone()
            return bool(row["clean_system_messages"]) if row else True
    
    # === Методы для работы со статистикой ===
    
    def update_user_stats(self, chat_id: int, user_id: int, username: str, first_name: str):
        """Обновление статистики пользователя"""
        now = datetime.now().isoformat()
        with self.get_connection() as conn:
            conn.execute(
                """INSERT INTO user_stats (chat_id, user_id, username, first_name, message_count, join_date)
                   VALUES (?, ?, ?, ?, 1, ?)
                   ON CONFLICT(chat_id, user_id) DO UPDATE SET
                       username = COALESCE(?, username),
                       first_name = COALESCE(?, first_name),
                       message_count = message_count + 1""",
                (chat_id, user_id, username or "", first_name or "", now, 
                 username or "", first_name or "")
            )
            conn.execute(
                """INSERT INTO chat_stats (chat_id, total_messages, last_updated)
                   VALUES (?, 1, ?)
                   ON CONFLICT(chat_id) DO UPDATE SET
                       total_messages = total_messages + 1,
                       last_updated = ?""",
                (chat_id, now, now)
            )
    
    def register_member(self, chat_id: int, user_id: int, username: str, first_name: str):
        """Регистрация нового участника"""
        now = datetime.now().isoformat()
        with self.get_connection() as conn:
            conn.execute(
                """INSERT OR IGNORE INTO user_stats 
                   (chat_id, user_id, username, first_name, message_count, join_date) 
                   VALUES (?, ?, ?, ?, 0, ?)""",
                (chat_id, user_id, username or "", first_name or "", now)
            )
            logger.info(f"Новый участник {user_id} в чате {chat_id}")
    
    def get_chat_stats(self, chat_id: int) -> tuple:
        """Получение статистики чата"""
        with self.get_connection() as conn:
            stats = conn.execute(
                "SELECT * FROM chat_stats WHERE chat_id = ?",
                (chat_id,)
            ).fetchone()
            top_users = conn.execute(
                """SELECT user_id, username, first_name, message_count
                   FROM user_stats 
                   WHERE chat_id = ?
                   ORDER BY message_count DESC 
                   LIMIT 5""",
                (chat_id,)
            ).fetchall()
        return stats, top_users
    
    # === Методы для работы с варнами ===
    
    def add_warn(self, chat_id: int, user_id: int, reason: str = "") -> int:
        """Добавление варна"""
        with self.get_connection() as conn:
            row = conn.execute(
                "SELECT count, reasons FROM warns WHERE chat_id = ? AND user_id = ?",
                (chat_id, user_id)
            ).fetchone()
            
            if row:
                new_count = row["count"] + 1
                reasons = (row["reasons"] + "\n" + reason).strip() if reason else row["reasons"]
                conn.execute(
                    "UPDATE warns SET count = ?, reasons = ? WHERE chat_id = ? AND user_id = ?",
                    (new_count, reasons, chat_id, user_id)
                )
            else:
                new_count = 1
                conn.execute(
                    "INSERT INTO warns (chat_id, user_id, count, reasons) VALUES (?, ?, 1, ?)",
                    (chat_id, user_id, reason)
                )
            
            logger.info(f"Варн выдан {user_id} в чате {chat_id}, всего: {new_count}")
            return new_count
    
    def remove_warn(self, chat_id: int, user_id: int) -> int:
        """Удаление варна"""
        with self.get_connection() as conn:
            row = conn.execute(
                "SELECT count FROM warns WHERE chat_id = ? AND user_id = ?",
                (chat_id, user_id)
            ).fetchone()
            
            if not row or row["count"] == 0:
                return 0
            
            new_count = max(0, row["count"] - 1)
            if new_count == 0:
                conn.execute(
                    "DELETE FROM warns WHERE chat_id = ? AND user_id = ?",
                    (chat_id, user_id)
                )
            else:
                conn.execute(
                    "UPDATE warns SET count = ? WHERE chat_id = ? AND user_id = ?",
                    (new_count, chat_id, user_id)
                )
            
            logger.info(f"Варн снят с {user_id} в чате {chat_id}, осталось: {new_count}")
            return new_count
    
    def clear_warns(self, chat_id: int, user_id: int):
        """Очистка варнов"""
        with self.get_connection() as conn:
            conn.execute(
                "DELETE FROM warns WHERE chat_id = ? AND user_id = ?",
                (chat_id, user_id)
            )
            logger.info(f"Варны очищены для {user_id} в чате {chat_id}")
    
    def get_warns(self, chat_id: int, user_id: int) -> Optional[Dict[str, Any]]:
        """Получение варнов"""
        with self.get_connection() as conn:
            return conn.execute(
                "SELECT count, reasons FROM warns WHERE chat_id = ? AND user_id = ?",
                (chat_id, user_id)
            ).fetchone()
    
    # === Методы для работы с администраторами бота ===
    
    def add_bot_admin(self, user_id: int, chat_id: int, granted_by: int):
        """Добавление администратора бота"""
        with self.get_connection() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO bot_admins (user_id, chat_id, granted_by, granted_at) 
                   VALUES (?, ?, ?, ?)""",
                (user_id, chat_id, granted_by, datetime.now().isoformat())
            )
            logger.info(f"Администратор бота добавлен: user={user_id}, chat={chat_id}, by={granted_by}")
    
    def remove_bot_admin(self, user_id: int, chat_id: int):
        """Удаление администратора бота"""
        with self.get_connection() as conn:
            conn.execute(
                "DELETE FROM bot_admins WHERE user_id = ? AND chat_id = ?",
                (user_id, chat_id)
            )
            logger.info(f"Администратор бота удален: user={user_id}, chat={chat_id}")
    
    def is_bot_admin(self, user_id: int, chat_id: int) -> bool:
        """Проверка, является ли пользователь администратором бота"""
        with self.get_connection() as conn:
            row = conn.execute(
                "SELECT 1 FROM bot_admins WHERE user_id = ? AND chat_id = ?",
                (user_id, chat_id)
            ).fetchone()
            return row is not None
    
    def get_bot_admins(self, chat_id: int) -> List[Dict[str, Any]]:
        """Получение списка администраторов бота"""
        with self.get_connection() as conn:
            return conn.execute(
                "SELECT user_id, granted_by, granted_at FROM bot_admins WHERE chat_id = ?",
                (chat_id,)
            ).fetchall()
    
    # === Методы для работы с пользовательскими командами ===
    
    def add_custom_command(self, chat_id: int, command: str, response: str, created_by: int) -> bool:
        """Добавление пользовательской команды"""
        command = command.lower().strip()
        with self.get_connection() as conn:
            try:
                conn.execute(
                    """INSERT OR REPLACE INTO custom_commands (chat_id, command, response, created_by, created_at)
                       VALUES (?, ?, ?, ?, ?)""",
                    (chat_id, command, response, created_by, datetime.now().isoformat())
                )
                logger.info(f"Команда !{command} добавлена в чате {chat_id}")
                return True
            except Exception as e:
                logger.error(f"Ошибка добавления команды: {e}")
                return False
    
    def remove_custom_command(self, chat_id: int, command: str) -> bool:
        """Удаление пользовательской команды"""
        command = command.lower().strip()
        with self.get_connection() as conn:
            try:
                conn.execute(
                    "DELETE FROM custom_commands WHERE chat_id = ? AND command = ?",
                    (chat_id, command)
                )
                logger.info(f"Команда !{command} удалена в чате {chat_id}")
                return True
            except Exception as e:
                logger.error(f"Ошибка удаления команды: {e}")
                return False
    
    def get_custom_command(self, chat_id: int, command: str) -> Optional[Dict[str, Any]]:
        """Получение пользовательской команды"""
        command = command.lower().strip()
        with self.get_connection() as conn:
            return conn.execute(
                "SELECT * FROM custom_commands WHERE chat_id = ? AND command = ?",
                (chat_id, command)
            ).fetchone()
    
    def get_all_custom_commands(self, chat_id: int) -> List[Dict[str, Any]]:
        """Получение всех команд чата"""
        with self.get_connection() as conn:
            return conn.execute(
                "SELECT command, response, created_by, created_at FROM custom_commands WHERE chat_id = ? ORDER BY command",
                (chat_id,)
            ).fetchall()
    
    def get_custom_commands_count(self, chat_id: int) -> int:
        """Количество команд в чате"""
        with self.get_connection() as conn:
            row = conn.execute(
                "SELECT COUNT(*) as count FROM custom_commands WHERE chat_id = ?",
                (chat_id,)
            ).fetchone()
            return row["count"] if row else 0
    
    # === Вспомогательные методы ===
    
    def is_chat_exists(self, chat_id: int) -> bool:
        """Проверка существования чата в БД"""
        with self.get_connection() as conn:
            row = conn.execute(
                "SELECT 1 FROM chats WHERE chat_id = ?",
                (chat_id,)
            ).fetchone()
            return row is not None
    
    def delete_chat(self, chat_id: int):
        """Удаление чата из БД"""
        with self.get_connection() as conn:
            conn.execute("DELETE FROM chats WHERE chat_id = ?", (chat_id,))
            conn.execute("DELETE FROM chat_stats WHERE chat_id = ?", (chat_id,))
            conn.execute("DELETE FROM bot_admins WHERE chat_id = ?", (chat_id,))
            conn.execute("DELETE FROM warns WHERE chat_id = ?", (chat_id,))
            conn.execute("DELETE FROM user_stats WHERE chat_id = ?", (chat_id,))
            conn.execute("DELETE FROM custom_commands WHERE chat_id = ?", (chat_id,))
            logger.info(f"Чат {chat_id} удален из БД")
    
    def get_all_bot_admins(self, user_id: int) -> List[Dict[str, Any]]:
        """Получение всех чатов, где пользователь является администратором бота"""
        with self.get_connection() as conn:
            return conn.execute(
                """SELECT c.chat_id, c.title, c.owner_id 
                   FROM bot_admins ba
                   JOIN chats c ON c.chat_id = ba.chat_id
                   WHERE ba.user_id = ?""",
                (user_id,)
            ).fetchall()
    
    def get_statistics(self) -> Dict[str, Any]:
        """Получение общей статистики"""
        with self.get_connection() as conn:
            total_chats = conn.execute("SELECT COUNT(*) as count FROM chats").fetchone()["count"]
            total_users = conn.execute("SELECT COUNT(DISTINCT user_id) as count FROM user_stats").fetchone()["count"]
            total_messages = conn.execute("SELECT SUM(total_messages) as total FROM chat_stats").fetchone()["total"] or 0
            total_warns = conn.execute("SELECT SUM(count) as total FROM warns").fetchone()["total"] or 0
            total_commands = conn.execute("SELECT COUNT(*) as count FROM custom_commands").fetchone()["count"] or 0
            
            return {
                "total_chats": total_chats,
                "total_users": total_users,
                "total_messages": total_messages,
                "total_warns": total_warns,
                "total_commands": total_commands
            }
    
    def debug_print_all(self):
        """Вывод всей информации из БД (для отладки)"""
        with self.get_connection() as conn:
            print("\n" + "=" * 50)
            print("ЧАТЫ:")
            chats = conn.execute("SELECT * FROM chats").fetchall()
            for chat in chats:
                print(dict(chat))
            
            print("\nАДМИНИСТРАТОРЫ БОТА:")
            admins = conn.execute("SELECT * FROM bot_admins").fetchall()
            for admin in admins:
                print(dict(admin))
            
            print("\nВАРНЫ:")
            warns = conn.execute("SELECT * FROM warns").fetchall()
            for warn in warns:
                print(dict(warn))
            
            print("\nПОЛЬЗОВАТЕЛЬСКИЕ КОМАНДЫ:")
            commands = conn.execute("SELECT * FROM custom_commands").fetchall()
            for cmd in commands:
                print(dict(cmd))
            
            print("=" * 50 + "\n")


# Для тестирования
if __name__ == "__main__":
    db = Database()
    db.debug_print_all()
    print("\n📊 Статистика:")
    stats = db.get_statistics()
    for key, value in stats.items():
        print(f"  {key}: {value}")