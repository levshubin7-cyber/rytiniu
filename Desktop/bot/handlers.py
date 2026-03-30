import logging
from datetime import datetime, timedelta
from typing import Optional, Tuple, List, Dict, Any
import re

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ChatPermissions
from telegram.error import TelegramError
from telegram.ext import ContextTypes

from config import Config
from database import Database

logger = logging.getLogger(__name__)


# ============================
#  Утилиты
# ============================

class PermissionUtils:
    """Утилиты для проверки прав"""
    
    def __init__(self, db: Database):
        self.db = db
    
    async def is_chat_owner(self, bot, user_id: int, chat_id: int) -> bool:
        """Проверка, является ли пользователь владельцем чата"""
        owner_id = self.db.get_chat_owner(chat_id)
        if owner_id == user_id:
            return True
        
        try:
            from telegram import ChatMemberOwner
            member = await bot.get_chat_member(chat_id, user_id)
            if isinstance(member, ChatMemberOwner):
                self.db.set_chat_owner(chat_id, user_id)
                return True
        except TelegramError:
            pass
        return False
    
    async def can_use_panel(self, bot, user_id: int, chat_id: int) -> bool:
        """Проверка, может ли пользователь использовать панель"""
        if await self.is_chat_owner(bot, user_id, chat_id):
            return True
        return self.db.is_bot_admin(user_id, chat_id)
    
    async def is_group_admin(self, bot, user_id: int, chat_id: int) -> bool:
        """Проверка, является ли пользователь администратором группы"""
        try:
            from telegram import ChatMemberOwner, ChatMemberAdministrator
            member = await bot.get_chat_member(chat_id, user_id)
            if isinstance(member, (ChatMemberOwner, ChatMemberAdministrator)):
                return True
        except TelegramError:
            pass
        return False


class UserResolver:
    """Утилиты для поиска пользователей"""
    
    def __init__(self, bot):
        self.bot = bot
    
    async def resolve(self, user_input: str, chat_id: int = None) -> Tuple[Optional[int], Optional[str], Optional[str]]:
        """Поиск пользователя по ID, username или имени"""
        user_input = user_input.strip()
        clean_input = user_input.lstrip('@')
        
        # 1. По числовому ID
        try:
            user_id = int(clean_input)
            name = str(user_id)
            if chat_id:
                try:
                    member = await self.bot.get_chat_member(chat_id, user_id)
                    name = member.user.first_name or member.user.username or str(user_id)
                except TelegramError:
                    pass
            return user_id, name, None
        except ValueError:
            pass
        
        # 2. По username
        try:
            user = await self.bot.get_chat(f"@{clean_input}")
            return user.id, user.first_name or user.username or str(user.id), None
        except TelegramError:
            pass
        
        # 3. Поиск среди администраторов
        if chat_id:
            try:
                admins = await self.bot.get_chat_administrators(chat_id)
                for admin in admins:
                    if admin.user.username and admin.user.username.lower() == clean_input.lower():
                        return admin.user.id, admin.user.first_name or admin.user.username, None
                    if admin.user.first_name and admin.user.first_name.lower() == clean_input.lower():
                        return admin.user.id, admin.user.first_name, None
            except TelegramError:
                pass
        
        return None, None, f"❌ Пользователь {user_input} не найден"


class ChatPermissionsHelper:
    """Вспомогательные функции для прав чата"""
    
    _no_permissions = None
    _full_permissions = None
    
    @classmethod
    def no_permissions(cls) -> ChatPermissions:
        """Нет прав (мут)"""
        if cls._no_permissions is None:
            cls._no_permissions = ChatPermissions(
                can_send_messages=False,
                can_send_audios=False,
                can_send_documents=False,
                can_send_photos=False,
                can_send_videos=False,
                can_send_video_notes=False,
                can_send_voice_notes=False,
                can_send_polls=False,
                can_send_other_messages=False,
                can_add_web_page_previews=False,
            )
        return cls._no_permissions
    
    @classmethod
    def full_permissions(cls) -> ChatPermissions:
        """Полные права"""
        if cls._full_permissions is None:
            cls._full_permissions = ChatPermissions(
                can_send_messages=True,
                can_send_audios=True,
                can_send_documents=True,
                can_send_photos=True,
                can_send_videos=True,
                can_send_video_notes=True,
                can_send_voice_notes=True,
                can_send_polls=True,
                can_send_other_messages=True,
                can_add_web_page_previews=True,
            )
        return cls._full_permissions


class KeyboardBuilder:
    """Построитель клавиатур"""
    
    @staticmethod
    def chat_list(chats: list) -> InlineKeyboardMarkup:
        """Клавиатура со списком чатов"""
        rows = [
            [InlineKeyboardButton(f"💬 {c['title']}", callback_data=f"menu:{c['chat_id']}")]
            for c in chats
        ]
        return InlineKeyboardMarkup(rows)
    
    @staticmethod
    def main(chat_id: int) -> InlineKeyboardMarkup:
        """Главное меню"""
        return InlineKeyboardMarkup([
            [
                InlineKeyboardButton("🔨 Бан", callback_data=f"ban_menu:{chat_id}"),
                InlineKeyboardButton("🔇 Мут", callback_data=f"mute_menu:{chat_id}"),
            ],
            [
                InlineKeyboardButton("📊 Статистика", callback_data=f"stats:{chat_id}"),
                InlineKeyboardButton("⚙️ Настройки", callback_data=f"settings:{chat_id}"),
            ],
            [InlineKeyboardButton("👮 Управление доступом", callback_data=f"access:{chat_id}")],
            [InlineKeyboardButton("◀️ К списку чатов", callback_data="chats_list")],
        ])
    
    @staticmethod
    def back(chat_id: int) -> InlineKeyboardMarkup:
        """Кнопка назад"""
        return InlineKeyboardMarkup([
            [InlineKeyboardButton("◀️ Главное меню", callback_data=f"menu:{chat_id}")]
        ])
    
    @staticmethod
    def confirm_action(chat_id: int, user_id: int, action: str, name: str = "") -> InlineKeyboardMarkup:
        """Клавиатура подтверждения действия"""
        text = f"✅ {action} {name}" if name else f"✅ {action}"
        return InlineKeyboardMarkup([[
            InlineKeyboardButton(text, callback_data=f"confirm_{action}:{chat_id}:{user_id}"),
            InlineKeyboardButton("❌ Отмена", callback_data=f"menu:{chat_id}"),
        ]])
    
    @staticmethod
    def mute_duration(chat_id: int, user_id: int, name: str = "") -> InlineKeyboardMarkup:
        """Клавиатура выбора длительности мута"""
        durations = Config.MUTE_DURATIONS
        buttons = []
        for label, minutes in durations.items():
            buttons.append([InlineKeyboardButton(label, callback_data=f"confirm_mute:{chat_id}:{user_id}:{minutes}")])
        
        buttons.append([InlineKeyboardButton("Навсегда", callback_data=f"confirm_mute:{chat_id}:{user_id}:0")])
        buttons.append([InlineKeyboardButton("❌ Отмена", callback_data=f"menu:{chat_id}")])
        return InlineKeyboardMarkup(buttons)


# ============================
#  Обработчики команд
# ============================

class BanHandler:
    """Обработчик команды бана"""
    
    def __init__(self, db: Database, permissions: PermissionUtils):
        self.db = db
        self.permissions = permissions
    
    async def handle(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        msg = update.message
        chat_id = msg.chat_id
        
        if not await self.permissions.is_group_admin(context.bot, msg.from_user.id, chat_id):
            await msg.reply_text("❌ Только администраторы могут банить.")
            return
        
        target_id = None
        target_name = None
        
        if msg.reply_to_message and msg.reply_to_message.from_user:
            user = msg.reply_to_message.from_user
            target_id = user.id
            target_name = user.first_name or str(user.id)
        elif msg.text:
            parts = msg.text.split()
            if len(parts) >= 2:
                resolver = UserResolver(context.bot)
                target_id, target_name, error = await resolver.resolve(parts[1], chat_id)
                if error:
                    await msg.reply_text(error)
                    return
        
        if not target_id:
            await msg.reply_text("❌ Ответь на сообщение или укажи ID/username.")
            return
        
        reason = ""
        if msg.text:
            parts = msg.text.split(None, 2)
            if len(parts) >= 3:
                reason = parts[2]
        
        try:
            await context.bot.ban_chat_member(chat_id, target_id)
            text = f"🔨 {target_name} забанен."
            if reason:
                text += f"\n📝 Причина: {reason}"
            await msg.reply_text(text)
        except Exception as e:
            await msg.reply_text(f"❌ Ошибка: {e}")


class WarnHandler:
    """Обработчик команды варнов"""
    
    def __init__(self, db: Database, permissions: PermissionUtils):
        self.db = db
        self.permissions = permissions
    
    async def handle(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        msg = update.message
        chat_id = msg.chat_id
        
        if not await self.permissions.is_group_admin(context.bot, msg.from_user.id, chat_id):
            await msg.reply_text("❌ Только администраторы могут выдавать варны.")
            return
        
        target_id = None
        target_name = None
        
        if msg.reply_to_message and msg.reply_to_message.from_user:
            user = msg.reply_to_message.from_user
            target_id = user.id
            target_name = user.first_name or str(user.id)
        elif msg.text:
            parts = msg.text.split()
            if len(parts) >= 2:
                resolver = UserResolver(context.bot)
                target_id, target_name, error = await resolver.resolve(parts[1], chat_id)
                if error:
                    await msg.reply_text(error)
                    return
        
        if not target_id:
            await msg.reply_text("❌ Ответь на сообщение или укажи ID/username.")
            return
        
        parts = msg.text.split(None, 2) if msg.text else []
        reason = parts[2] if len(parts) >= 3 else ""
        
        warn_count = self.db.add_warn(chat_id, target_id, reason)
        text = f"⚠️ {target_name} получает варн ({warn_count}/{Config.MAX_WARNS})."
        if reason:
            text += f"\n📝 Причина: {reason}"
        
        if warn_count >= Config.MAX_WARNS:
            try:
                await context.bot.ban_chat_member(chat_id, target_id)
                self.db.clear_warns(chat_id, target_id)
                text += f"\n\n🔨 Автобан — достигнут лимит {Config.MAX_WARNS} варнов."
            except Exception as e:
                text += f"\n\n❌ Не удалось забанить: {e}"
        
        await msg.reply_text(text)


class CallbackHandler:
    """Обработчик callback-запросов"""
    
    def __init__(self, db: Database, permissions: PermissionUtils):
        self.db = db
        self.permissions = permissions
        self.keyboard = KeyboardBuilder()
    
    async def handle(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Основной обработчик"""
        query = update.callback_query
        await query.answer()
        
        parts = query.data.split(":")
        action = parts[0]
        
        if action == "chats_list":
            await self._show_chats_list(query, context)
        elif action == "menu" and len(parts) > 1:
            await self._show_main_menu(query, context, int(parts[1]))
        elif action == "ban_menu" and len(parts) > 1:
            await self._show_ban_menu(query, int(parts[1]))
        elif action == "mute_menu" and len(parts) > 1:
            await self._show_mute_menu(query, int(parts[1]))
        elif action == "stats" and len(parts) > 1:
            await self._show_stats(query, context, int(parts[1]))
        elif action == "settings" and len(parts) > 1:
            await self._show_settings(query, context, int(parts[1]))
        elif action == "access" and len(parts) > 1:
            await self._show_access(query, context, int(parts[1]))
        elif action == "confirm_ban" and len(parts) > 2:
            await self._confirm_ban(query, context, int(parts[1]), int(parts[2]))
        elif action == "confirm_unban" and len(parts) > 2:
            await self._confirm_unban(query, context, int(parts[1]), int(parts[2]))
        elif action == "confirm_mute" and len(parts) > 3:
            await self._confirm_mute(query, context, int(parts[1]), int(parts[2]), int(parts[3]))
        elif action == "confirm_unmute" and len(parts) > 2:
            await self._confirm_unmute(query, context, int(parts[1]), int(parts[2]))
    
    async def _show_chats_list(self, query, context):
        user_id = query.from_user.id
        all_chats = self.db.get_all_chats()
        
        accessible = []
        for chat in all_chats:
            if await self.permissions.can_use_panel(context.bot, user_id, chat["chat_id"]):
                accessible.append(chat)
        
        if not accessible:
            await query.edit_message_text("❌ Нет доступных чатов.")
            return
        
        await query.edit_message_text(
            "🛡 Панель управления\n\nВыбери чат:",
            reply_markup=self.keyboard.chat_list(accessible)
        )
    
    async def _show_main_menu(self, query, context, chat_id):
        try:
            chat = await context.bot.get_chat(chat_id)
            title = chat.title
        except Exception:
            title = str(chat_id)
        
        await query.edit_message_text(
            f"🛡 Панель управления\n💬 {title}\n\nВыбери раздел:",
            reply_markup=self.keyboard.main(chat_id)
        )
    
    async def _show_ban_menu(self, query, chat_id):
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔨 Забанить пользователя", callback_data=f"do_ban:{chat_id}")],
            [InlineKeyboardButton("🔓 Разбанить пользователя", callback_data=f"do_unban:{chat_id}")],
            [InlineKeyboardButton("◀️ Главное меню", callback_data=f"menu:{chat_id}")],
        ])
        await query.edit_message_text("🔨 Раздел бана\n\nВыбери действие:", reply_markup=keyboard)
    
    async def _show_mute_menu(self, query, chat_id):
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔇 Замутить пользователя", callback_data=f"do_mute:{chat_id}")],
            [InlineKeyboardButton("🔊 Размутить пользователя", callback_data=f"do_unmute:{chat_id}")],
            [InlineKeyboardButton("◀️ Главное меню", callback_data=f"menu:{chat_id}")],
        ])
        await query.edit_message_text("🔇 Раздел мута\n\nВыбери действие:", reply_markup=keyboard)
    
    async def _show_stats(self, query, context, chat_id):
        stats, top = self.db.get_chat_stats(chat_id)
        try:
            member_count = await context.bot.get_chat_member_count(chat_id)
        except Exception:
            member_count = "—"
        
        lines = [f"📊 Статистика чата\n", f"👥 Участников: {member_count}"]
        if stats:
            lines.append(f"💬 Сообщений всего: {stats['total_messages'] or 0}")
        
        if top:
            lines.append("\n🏆 Топ-5 активных:")
            for i, u in enumerate(top, 1):
                name = u["first_name"] or u["username"] or str(u["user_id"])
                lines.append(f"{i}. {name} — {u['message_count']} сообщ.")
        
        await query.edit_message_text("\n".join(lines), reply_markup=self.keyboard.back(chat_id))
    
    async def _show_settings(self, query, context, chat_id):
        row = self.db.get_chat(chat_id)
        enabled = bool(row["welcome_enabled"]) if row else False
        text_msg = row["welcome_message"] if row else None
        
        body = "⚙️ Настройки чата\n\n"
        body += f"Приветствие: {'✅ включено' if enabled else '❌ выключено'}\n"
        if text_msg:
            body += f"\n📝 Текущий текст:\n{text_msg}\n\nИспользуй {{name}} для имени"
        else:
            body += "\nТекст приветствия не задан"
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("✏️ Изменить текст приветствия", callback_data=f"set_welcome:{chat_id}")],
            [InlineKeyboardButton(f"{'✅' if enabled else '❌'} Приветствие: {'вкл.' if enabled else 'выкл.'}", 
                                 callback_data=f"toggle_welcome:{chat_id}")],
            [InlineKeyboardButton("◀️ Главное меню", callback_data=f"menu:{chat_id}")],
        ])
        
        await query.edit_message_text(body, reply_markup=keyboard)
    
    async def _show_access(self, query, context, chat_id):
        admins = self.db.get_bot_admins(chat_id)
        body = "👮 Управление доступом к боту\n\n"
        body += "Администраторы бота (могут использовать панель):\n"
        
        if admins:
            for a in admins:
                name = str(a['user_id'])
                try:
                    member = await context.bot.get_chat_member(chat_id, a['user_id'])
                    name = member.user.first_name or member.user.username or str(a['user_id'])
                except Exception:
                    pass
                body += f"• {name} (`{a['user_id']}`)\n"
        else:
            body += "Нет дополнительных администраторов.\n"
        
        body += "\nВладелец чата имеет доступ автоматически."
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("➕ Добавить администратора", callback_data=f"add_admin:{chat_id}")],
            [InlineKeyboardButton("➖ Удалить администратора", callback_data=f"del_admin:{chat_id}")],
            [InlineKeyboardButton("◀️ Главное меню", callback_data=f"menu:{chat_id}")],
        ])
        
        await query.edit_message_text(body, reply_markup=keyboard, parse_mode="Markdown")
    
    async def _confirm_ban(self, query, context, chat_id, user_id):
        try:
            await context.bot.ban_chat_member(chat_id, user_id)
            await query.edit_message_text(f"✅ Пользователь {user_id} забанен.", reply_markup=self.keyboard.back(chat_id))
        except Exception as e:
            await query.edit_message_text(f"❌ Ошибка: {e}", reply_markup=self.keyboard.back(chat_id))
    
    async def _confirm_unban(self, query, context, chat_id, user_id):
        try:
            await context.bot.unban_chat_member(chat_id, user_id, only_if_banned=True)
            await query.edit_message_text(f"✅ Пользователь {user_id} разбанен.", reply_markup=self.keyboard.back(chat_id))
        except Exception as e:
            await query.edit_message_text(f"❌ Ошибка: {e}", reply_markup=self.keyboard.back(chat_id))
    
    async def _confirm_mute(self, query, context, chat_id, user_id, duration):
        until = None if duration == 0 else datetime.now() + timedelta(minutes=duration)
        labels = {0: "навсегда", 15: "15 минут", 60: "1 час", 1440: "24 часа", 10080: "7 дней"}
        try:
            await context.bot.restrict_chat_member(chat_id, user_id, permissions=ChatPermissionsHelper.no_permissions(), until_date=until)
            await query.edit_message_text(f"✅ Пользователь {user_id} замучен {labels.get(duration, str(duration))}.", reply_markup=self.keyboard.back(chat_id))
        except Exception as e:
            await query.edit_message_text(f"❌ Ошибка: {e}", reply_markup=self.keyboard.back(chat_id))
    
    async def _confirm_unmute(self, query, context, chat_id, user_id):
        try:
            await context.bot.restrict_chat_member(chat_id, user_id, permissions=ChatPermissionsHelper.full_permissions())
            await query.edit_message_text(f"✅ Мут снят с {user_id}.", reply_markup=self.keyboard.back(chat_id))
        except Exception as e:
            await query.edit_message_text(f"❌ Ошибка: {e}", reply_markup=self.keyboard.back(chat_id))


class MessageHandler:
    """Обработчик сообщений"""
    
    def __init__(self, db: Database):
        self.db = db
    
    async def handle_private_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка сообщений в ЛС"""
        pass  # Можно добавить логику при необходимости
    
    async def handle_group_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка сообщений в группе"""
        user = update.effective_user
        chat = update.effective_chat
        
        if user and not user.is_bot and chat.type in ("group", "supergroup"):
            self.db.update_user_stats(chat.id, user.id, user.username, user.first_name)


class CustomCommandHandler:
    """Обработчик пользовательских команд"""
    
    def __init__(self, db: Database):
        self.db = db
    
    async def handle(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка сообщений на наличие команд !команда"""
        message = update.message
        if not message or not message.text:
            return
        
        chat_id = message.chat_id
        text = message.text.strip()
        
        if not text.startswith('!'):
            return
        
        parts = text.split(maxsplit=1)
        command = parts[0][1:].lower()
        
        cmd_data = self.db.get_custom_command(chat_id, command)
        
        if not cmd_data:
            return
        
        response = cmd_data["response"]
        response = self._replace_variables(response, message)
        
        try:
            await message.reply_text(response)
        except Exception as e:
            logger.error(f"Ошибка отправки ответа на команду !{command}: {e}")
    
    def _replace_variables(self, text: str, message) -> str:
        """Замена переменных в тексте"""
        user = message.from_user
        chat = message.chat
        
        replacements = {
            "{name}": user.first_name or user.username or "Пользователь",
            "{user}": f"@{user.username}" if user.username else user.first_name or str(user.id),
            "{username}": f"@{user.username}" if user.username else "нет_username",
            "{id}": str(user.id),
            "{first_name}": user.first_name or "",
            "{last_name}": user.last_name or "",
            "{full_name}": f"{user.first_name or ''} {user.last_name or ''}".strip() or user.username or "Пользователь",
            "{chat_name}": chat.title or "Чат",
            "{chat_id}": str(chat.id),
            "{date}": datetime.now().strftime("%d.%m.%Y"),
            "{time}": datetime.now().strftime("%H:%M:%S"),
        }
        
        for var, value in replacements.items():
            text = text.replace(var, value)
        
        return text


class CommandManagerHandler:
    """Управление пользовательскими командами"""
    
    def __init__(self, db: Database, permissions: PermissionUtils):
        self.db = db
        self.permissions = permissions
    
    async def add_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Добавление команды: /addcmd команда текст ответа"""
        if not await self.permissions.is_group_admin(context.bot, update.effective_user.id, update.effective_chat.id):
            await update.message.reply_text("❌ Только администраторы могут создавать команды.")
            return
        
        chat_id = update.effective_chat.id
        text = update.message.text
        
        parts = text.split(maxsplit=2)
        
        if len(parts) < 3:
            await update.message.reply_text(
                "❌ Использование: /addcmd команда текст ответа\n\n"
                "Пример: /addcmd hello Привет, {name}!\n\n"
                "Доступные переменные:\n"
                "• {name} - имя пользователя\n"
                "• {user} - username или имя\n"
                "• {id} - ID пользователя\n"
                "• {chat_name} - название чата\n"
                "• {date} - текущая дата\n"
                "• {time} - текущее время"
            )
            return
        
        command = parts[1].lower()
        response = parts[2]
        
        if len(command) > 50:
            await update.message.reply_text("❌ Название команды не может быть длиннее 50 символов.")
            return
        
        if len(response) > 1000:
            await update.message.reply_text("❌ Текст ответа не может быть длиннее 1000 символов.")
            return
        
        forbidden = ["addcmd", "delcmd", "commands", "admin", "ban", "mute", "warn", "start", "help"]
        if command in forbidden:
            await update.message.reply_text(f"❌ Команда !{command} зарезервирована системой.")
            return
        
        if self.db.add_custom_command(chat_id, command, response, update.effective_user.id):
            await update.message.reply_text(
                f"✅ Команда !{command} создана!\n\n"
                f"Ответ: {response[:100]}{'...' if len(response) > 100 else ''}"
            )
        else:
            await update.message.reply_text("❌ Ошибка при создании команды.")
    
    async def del_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Удаление команды: /delcmd команда"""
        if not await self.permissions.is_group_admin(context.bot, update.effective_user.id, update.effective_chat.id):
            await update.message.reply_text("❌ Только администраторы могут удалять команды.")
            return
        
        chat_id = update.effective_chat.id
        text = update.message.text
        
        parts = text.split(maxsplit=1)
        
        if len(parts) < 2:
            await update.message.reply_text("❌ Использование: /delcmd команда")
            return
        
        command = parts[1].lower()
        
        cmd_data = self.db.get_custom_command(chat_id, command)
        if not cmd_data:
            await update.message.reply_text(f"❌ Команда !{command} не найдена.")
            return
        
        if self.db.remove_custom_command(chat_id, command):
            await update.message.reply_text(f"✅ Команда !{command} удалена!")
        else:
            await update.message.reply_text("❌ Ошибка при удалении команды.")
    
    async def list_commands(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Список команд: /commands"""
        chat_id = update.effective_chat.id
        
        commands = self.db.get_all_custom_commands(chat_id)
        
        if not commands:
            await update.message.reply_text(
                "📋 В этом чате пока нет пользовательских команд.\n\n"
                "Создать команду: /addcmd команда текст ответа\n"
                "Пример: /addcmd hello Привет, {name}!"
            )
            return
        
        text = f"📋 Команды чата ({len(commands)}):\n\n"
        for cmd in commands:
            response_preview = cmd["response"][:40] + "..." if len(cmd["response"]) > 40 else cmd["response"]
            text += f"• !{cmd['command']} - {response_preview}\n"
        
        text += "\n📝 Доступные переменные:\n"
        text += "• {name} - имя пользователя\n"
        text += "• {user} - username или имя\n"
        text += "• {date} - текущая дата\n"
        text += "• {time} - текущее время\n\n"
        text += "Создать: /addcmd, удалить: /delcmd"
        
        await update.message.reply_text(text)