import logging
from datetime import datetime, timedelta
from typing import Optional
import asyncio

from telegram import Update
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, ChatMemberHandler, filters, ContextTypes
)

from config import Config
from database import Database
from handlers import (
    PermissionUtils, BanHandler, WarnHandler, CallbackHandler, 
    MessageHandler as MsgHandler, CustomCommandHandler, CommandManagerHandler
)

# Настройка логирования
logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


class BotApplication:
    """Главный класс приложения"""
    
    def __init__(self):
        self.db = Database()
        self.permissions = PermissionUtils(self.db)
        self.callback_handler = CallbackHandler(self.db, self.permissions)
        self.msg_handler = MsgHandler(self.db)
        self.ban_handler = BanHandler(self.db, self.permissions)
        self.warn_handler = WarnHandler(self.db, self.permissions)
        self.custom_command_handler = CustomCommandHandler(self.db)
        self.command_manager = CommandManagerHandler(self.db, self.permissions)
        
        self.app = Application.builder().token(Config.BOT_TOKEN).build()
        self._setup_handlers()
    
    def _setup_handlers(self):
        """Настройка обработчиков"""
        # Основные команды
        self.app.add_handler(CommandHandler("start", self.cmd_start))
        self.app.add_handler(CommandHandler("help", self.cmd_help))
        self.app.add_handler(CommandHandler("admin", self.cmd_admin))
        self.app.add_handler(CommandHandler("check_perms", self.check_bot_permissions))
        
        # Команды управления чатом
        self.app.add_handler(CommandHandler("ban", self.ban_handler.handle))
        self.app.add_handler(CommandHandler("unban", self.cmd_unban))
        self.app.add_handler(CommandHandler("mute", self.cmd_mute))
        self.app.add_handler(CommandHandler("unmute", self.cmd_unmute))
        self.app.add_handler(CommandHandler("warn", self.warn_handler.handle))
        self.app.add_handler(CommandHandler("unwarn", self.cmd_unwarn))
        self.app.add_handler(CommandHandler("warns", self.cmd_warns))
        self.app.add_handler(CommandHandler("clearwarns", self.cmd_clearwarns))
        self.app.add_handler(CommandHandler("add_me", self.cmd_add_me))
        self.app.add_handler(CommandHandler("toggle_clean", self.cmd_toggle_clean))
        
        # Команды управления пользовательскими командами
        self.app.add_handler(CommandHandler("addcmd", self.command_manager.add_command))
        self.app.add_handler(CommandHandler("delcmd", self.command_manager.del_command))
        self.app.add_handler(CommandHandler("commands", self.command_manager.list_commands))
        
        # Callback обработчик
        self.app.add_handler(CallbackQueryHandler(self.callback_handler.handle))
        
        # Обработчик системных сообщений (высокий приоритет)
        self.app.add_handler(
            MessageHandler(filters.StatusUpdate.ALL, self.delete_system_messages),
            group=1
        )
        
        # Обработчик новых участников
        self.app.add_handler(
            MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, self.handle_new_chat_members),
            group=2
        )
        
        # Обработчик обычных сообщений в группах
        self.app.add_handler(
            MessageHandler(filters.ChatType.GROUPS & ~filters.StatusUpdate.ALL, self.msg_handler.handle_group_message),
            group=3
        )
        
        # Обработчик пользовательских команд (низкий приоритет)
        self.app.add_handler(
            MessageHandler(filters.ChatType.GROUPS & filters.TEXT & ~filters.COMMAND, 
                          self.custom_command_handler.handle),
            group=4
        )
        
        # Обработчик личных сообщений
        self.app.add_handler(MessageHandler(
            filters.ChatType.PRIVATE & filters.TEXT & ~filters.COMMAND, 
            self.msg_handler.handle_private_message
        ))
        
        # Обработчик изменений статуса бота
        self.app.add_handler(ChatMemberHandler(
            self.handle_my_chat_member, 
            ChatMemberHandler.MY_CHAT_MEMBER
        ))
    
    async def delete_system_messages(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Удаляет все системные сообщения"""
        message = update.message
        
        if not message or not message.chat:
            return
        
        chat_id = message.chat.id
        chat_type = message.chat.type
        
        if chat_type not in ["group", "supergroup"]:
            return
        
        # Проверяем настройки чата
        row = self.db.get_chat(chat_id)
        clean_enabled = 1
        if row and "clean_system_messages" in row.keys():
            clean_enabled = row["clean_system_messages"]
        
        if not clean_enabled:
            return
        
        # Проверяем, является ли сообщение системным
        is_system = False
        message_type = None
        
        if message.new_chat_members:
            is_system = True
            message_type = "new_members"
            logger.info(f"Обнаружено сообщение о новых участниках в чате {chat_id}")
        
        elif message.left_chat_member:
            is_system = True
            message_type = "left_member"
            logger.info(f"Обнаружено сообщение о выходе участника в чате {chat_id}")
        
        elif message.new_chat_title:
            is_system = True
            message_type = "new_title"
        
        elif message.new_chat_photo or message.delete_chat_photo:
            is_system = True
            message_type = "photo_change"
        
        elif message.group_chat_created or message.supergroup_chat_created:
            is_system = True
            message_type = "chat_created"
        
        elif message.pinned_message:
            is_system = True
            message_type = "pinned"
        
        if is_system:
            try:
                await message.delete()
                logger.info(f"✅ Системное сообщение ({message_type}) удалено в чате {chat_id}")
            except Exception as e:
                error_msg = str(e)
                if "Message can't be deleted" in error_msg:
                    logger.warning(f"⚠️ Не могу удалить сообщение ({message_type}) в чате {chat_id}: нет прав администратора")
                else:
                    logger.error(f"❌ Ошибка при удалении ({message_type}): {error_msg}")
    
    async def handle_new_chat_members(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик новых участников"""
        message = update.message
        chat = update.effective_chat
        user_who_added = message.from_user
        
        await asyncio.sleep(0.5)
        
        for new_member in message.new_chat_members:
            if new_member.id == context.bot.id:
                logger.info(f"Бот добавлен в чат {chat.id} пользователем {user_who_added.id}")
                
                self.db.register_chat(chat.id, chat.title, user_who_added.id)
                self.db.set_clean_system_messages(chat.id, True)
                self.db.add_bot_admin(user_who_added.id, chat.id, context.bot.id)
                
                try:
                    admins = await context.bot.get_chat_administrators(chat.id)
                    for admin in admins:
                        if admin.user.id != user_who_added.id:
                            self.db.add_bot_admin(admin.user.id, chat.id, context.bot.id)
                except Exception as e:
                    logger.error(f"Ошибка: {e}")
                
                await context.bot.send_message(
                    chat.id,
                    "✅ Бот успешно добавлен в чат!\n\n"
                    f"👤 Добавил: {user_who_added.first_name}\n"
                    "👑 Теперь вы администратор бота\n\n"
                    "📋 Используйте /admin в личных сообщениях\n"
                    "🧹 Системные сообщения будут автоматически удаляться\n"
                    "🔧 Для отключения очистки: /toggle_clean\n"
                    "📝 Пользовательские команды: !addcmd, !delcmd, !commands"
                )
                
                try:
                    await context.bot.send_message(
                        user_who_added.id,
                        f"🎉 Вы добавили бота в чат \"{chat.title}\"!\n\n"
                        "Теперь вы можете управлять чатом: /admin\n\n"
                        "🧹 Системные сообщения (вход/выход) автоматически удаляются\n"
                        "Для отключения очистки используйте /toggle_clean в чате\n\n"
                        "📝 Создавайте свои команды:\n"
                        "!addcmd привет Привет, {name}!\n"
                        "!addcmd время Текущее время: {time}\n"
                        "!commands - список всех команд"
                    )
                except Exception as e:
                    logger.error(f"Ошибка: {e}")
                
                return
            
            else:
                self.db.register_member(chat.id, new_member.id, new_member.username, new_member.first_name)
                
                row = self.db.get_chat(chat.id)
                if row:
                    welcome_enabled = row["welcome_enabled"] if "welcome_enabled" in row.keys() else 0
                    welcome_message = row["welcome_message"] if "welcome_message" in row.keys() else None
                    
                    if welcome_enabled and welcome_message:
                        name = new_member.first_name or new_member.username or str(new_member.id)
                        text = welcome_message.replace("{name}", name)
                        try:
                            await asyncio.sleep(1)
                            await context.bot.send_message(chat.id, text)
                        except Exception as e:
                            logger.error(f"Ошибка: {e}")
    
    async def cmd_toggle_clean(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Включение/выключение очистки"""
        chat_id = update.effective_chat.id
        user_id = update.effective_user.id
        
        if not await self.permissions.is_group_admin(context.bot, user_id, chat_id):
            await update.message.reply_text("❌ Только администраторы могут изменять эту настройку.")
            return
        
        row = self.db.get_chat(chat_id)
        current = row["clean_system_messages"] if row and "clean_system_messages" in row.keys() else 1
        new_status = not current
        self.db.set_clean_system_messages(chat_id, new_status)
        
        status_text = "включена" if new_status else "выключена"
        await update.message.reply_text(
            f"🧹 Очистка системных сообщений {status_text}!\n\n"
            f"Теперь все сообщения о входе/выходе участников будут {'удаляться' if new_status else 'оставаться'}."
        )
    
    async def check_bot_permissions(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Проверка прав бота в чате"""
        chat_id = update.effective_chat.id
        
        try:
            bot_member = await context.bot.get_chat_member(chat_id, context.bot.id)
            
            if bot_member.status == "administrator":
                can_delete = bot_member.can_delete_messages
                can_ban = bot_member.can_restrict_members
                
                text = f"✅ Права бота в чате:\n"
                text += f"• Статус: Администратор\n"
                text += f"• Удаление сообщений: {'✅' if can_delete else '❌'}\n"
                text += f"• Бан/мут: {'✅' if can_ban else '❌'}\n\n"
                
                if not can_delete:
                    text += "⚠️ Для удаления системных сообщений нужно право 'Удаление сообщений'"
                else:
                    text += "✅ Бот готов к работе!"
                
                await update.message.reply_text(text)
            else:
                await update.message.reply_text(
                    "⚠️ Бот не является администратором чата!\n\n"
                    "Для полноценной работы (удаление системных сообщений, бан, мут) "
                    "пожалуйста, сделайте меня администратором."
                )
        except Exception as e:
            logger.error(f"Ошибка проверки прав: {e}")
            await update.message.reply_text("❌ Не удалось проверить права бота.")
    
    async def handle_my_chat_member(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик изменений статуса бота"""
        result = update.my_chat_member
        chat = update.effective_chat
        
        if result.new_chat_member.user.id == context.bot.id:
            if result.new_chat_member.status == "administrator" and result.old_chat_member.status != "administrator":
                logger.info(f"Бот получил права администратора в чате {chat.id}")
                
                try:
                    admins = await context.bot.get_chat_administrators(chat.id)
                    for admin in admins:
                        if admin.status == "creator":
                            self.db.add_bot_admin(admin.user.id, chat.id, context.bot.id)
                            await context.bot.send_message(
                                chat.id,
                                f"✅ Владелец чата {admin.user.first_name} добавлен как администратор бота"
                            )
                            break
                except Exception as e:
                    logger.error(f"Ошибка: {e}")
    
    async def cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /start"""
        chat = update.effective_chat
        
        if chat.type == "private":
            await update.message.reply_text(
                "👋 Привет! Я бот для управления чатами.\n\n"
                "📋 /admin — открыть панель управления\n\n"
                "📌 Как использовать:\n"
                "1. Добавьте меня в группу\n"
                "2. Я автоматически дам права администратора тому, кто меня добавил\n"
                "3. Используйте /admin в ЛС для управления\n\n"
                "🧹 Особенности:\n"
                "• Системные сообщения (вход/выход) автоматически удаляются\n"
                "• Для отключения очистки: /toggle_clean в чате\n\n"
                "📝 Пользовательские команды (как Nightbot):\n"
                "• !addcmd команда текст — создать команду\n"
                "• !delcmd команда — удалить команду\n"
                "• !commands — список команд\n\n"
                "Пример: !addcmd hello Привет, {name}!\n\n"
                "Команды в чате:\n"
                "• /ban [причина] — забанить\n"
                "• /unban <ID> — разбанить\n"
                "• /mute [15m|1h|24h|7d] — замутить\n"
                "• /unmute — снять мут\n"
                "• /warn [причина] — выдать варн\n"
                "• /unwarn — снять варн\n"
                "• /warns — посмотреть варны\n"
                "• /toggle_clean — вкл/выкл удаление системных сообщений\n"
                "• /check_perms — проверить права бота"
            )
        else:
            await update.message.reply_text(
                "🌟 Я — бот для управления чатом 🌟\n\n"
                "🧹 Системные сообщения автоматически удаляются\n"
                "🔧 Для отключения: /toggle_clean\n"
                "📝 Свои команды: !addcmd, !delcmd, !commands\n\n"
                "📋 Панель управления: /admin в ЛС\n"
                "🔍 Проверить права: /check_perms"
            )
    
    async def cmd_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /help"""
        text = (
            "📖 *Команды бота*\n\n"
            "*Панель (в ЛС):*\n"
            "/admin — открыть панель\n\n"
            "*Команды в чате:*\n"
            "/ban [причина] — бан\n"
            "/unban <ID> — разбан\n"
            "/mute [15m|1h|24h|7d] — мут\n"
            "/unmute — снять мут\n"
            "/warn [причина] — варн\n"
            "/unwarn — снять варн\n"
            "/warns — варны пользователя\n"
            "/toggle_clean — вкл/выкл удаление системных сообщений\n"
            "/check_perms — проверить права бота\n\n"
            "*Пользовательские команды:*\n"
            "!addcmd команда текст — создать команду\n"
            "!delcmd команда — удалить команду\n"
            "!commands — список команд\n\n"
            "*Переменные для команд:*\n"
            "{name} — имя пользователя\n"
            "{user} — username или имя\n"
            "{id} — ID пользователя\n"
            "{chat_name} — название чата\n"
            "{date} — текущая дата\n"
            "{time} — текущее время\n\n"
            "*Особенности:*\n"
            "• Системные сообщения удаляются автоматически\n"
            "• Приветствия настраиваются через панель управления"
        )
        await update.message.reply_text(text, parse_mode="Markdown")
    
    async def cmd_admin(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /admin"""
        if update.effective_chat.type != "private":
            try:
                await update.message.delete()
            except Exception:
                pass
            return
        
        from handlers import KeyboardBuilder
        
        user_id = update.effective_user.id
        all_chats = self.db.get_all_chats()
        
        accessible = []
        for chat in all_chats:
            if await self.permissions.can_use_panel(context.bot, user_id, chat["chat_id"]):
                accessible.append(chat)
        
        if not accessible:
            await update.message.reply_text(
                "❌ Нет доступных чатов.\n\n"
                "Возможные причины:\n"
                "• Вы не добавили бота в чат\n"
                "• Бот не видит вас как администратора\n\n"
                "Решение:\n"
                "Добавьте бота в чат заново, и он автоматически даст вам права"
            )
            return
        
        await update.message.reply_text(
            "🛡 Панель управления\n\nВыбери чат:",
            reply_markup=KeyboardBuilder.chat_list(accessible)
        )
    
    async def cmd_add_me(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда для добавления себя как администратора"""
        chat_id = update.effective_chat.id
        user_id = update.effective_user.id
        
        try:
            member = await context.bot.get_chat_member(chat_id, user_id)
            if member.status in ("creator", "administrator"):
                self.db.add_bot_admin(user_id, chat_id, user_id)
                await update.message.reply_text(
                    "✅ Вы добавлены как администратор бота!\n"
                    "Теперь используйте /admin в личных сообщениях"
                )
            else:
                await update.message.reply_text("❌ Вы должны быть администратором чата")
        except Exception as e:
            await update.message.reply_text(f"❌ Ошибка: {e}")
    
    async def cmd_unban(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /unban"""
        from handlers import UserResolver
        
        msg = update.message
        chat_id = msg.chat_id
        
        if not await self.permissions.is_group_admin(context.bot, msg.from_user.id, chat_id):
            await msg.reply_text("❌ Только администраторы могут разбанивать.")
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
            await msg.reply_text("❌ Укажи ID или username: /unban @username")
            return
        
        try:
            await context.bot.unban_chat_member(chat_id, target_id, only_if_banned=True)
            await msg.reply_text(f"✅ Пользователь {target_name or target_id} разбанен.")
        except Exception as e:
            await msg.reply_text(f"❌ Ошибка: {e}")
    
    async def cmd_mute(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /mute"""
        from handlers import UserResolver, ChatPermissionsHelper
        
        msg = update.message
        chat_id = msg.chat_id
        
        if not await self.permissions.is_group_admin(context.bot, msg.from_user.id, chat_id):
            await msg.reply_text("❌ Только администраторы могут мутить.")
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
        
        parts = msg.text.split() if msg.text else []
        time_arg = "15m"
        
        time_map = Config.MUTE_DURATIONS
        for p in parts:
            if p.lower() in time_map:
                time_arg = p.lower()
                break
        
        minutes = time_map.get(time_arg, 15)
        until = datetime.now() + timedelta(minutes=minutes)
        dur_labels = {15: "15 минут", 60: "1 час", 1440: "24 часа", 10080: "7 дней"}
        dur_label = dur_labels.get(minutes, "15 минут")
        
        try:
            await context.bot.restrict_chat_member(
                chat_id, target_id, permissions=ChatPermissionsHelper.no_permissions(), until_date=until
            )
            await msg.reply_text(f"🔇 {target_name or target_id} замучен на {dur_label}.")
        except Exception as e:
            await msg.reply_text(f"❌ Ошибка: {e}")
    
    async def cmd_unmute(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /unmute"""
        from handlers import UserResolver, ChatPermissionsHelper
        
        msg = update.message
        chat_id = msg.chat_id
        
        if not await self.permissions.is_group_admin(context.bot, msg.from_user.id, chat_id):
            await msg.reply_text("❌ Только администраторы могут снимать мут.")
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
            await msg.reply_text("❌ Ответь на сообщение или укажи ID.")
            return
        
        try:
            await context.bot.restrict_chat_member(chat_id, target_id, permissions=ChatPermissionsHelper.full_permissions())
            await msg.reply_text(f"🔊 Мут снят с {target_name or target_id}.")
        except Exception as e:
            await msg.reply_text(f"❌ Ошибка: {e}")
    
    async def cmd_unwarn(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /unwarn"""
        from handlers import UserResolver
        
        msg = update.message
        chat_id = msg.chat_id
        
        if not await self.permissions.is_group_admin(context.bot, msg.from_user.id, chat_id):
            await msg.reply_text("❌ Только администраторы могут снимать варны.")
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
            await msg.reply_text("❌ Ответь на сообщение или укажи ID.")
            return
        
        remaining = self.db.remove_warn(chat_id, target_id)
        await msg.reply_text(
            f"✅ Один варн снят с {target_name or target_id}. Осталось: {remaining}/{Config.MAX_WARNS}."
        )
    
    async def cmd_warns(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /warns"""
        from handlers import UserResolver
        
        msg = update.message
        chat_id = msg.chat_id
        
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
            target_id = msg.from_user.id
            target_name = msg.from_user.first_name or str(target_id)
        
        row = self.db.get_warns(chat_id, target_id)
        count = row["count"] if row else 0
        reasons = row["reasons"] if row else ""
        
        text = f"📋 Варны {target_name or target_id}: {count}/{Config.MAX_WARNS}\n"
        if reasons:
            text += "\nПричины:\n"
            for i, r in enumerate(reasons.strip().split("\n"), 1):
                if r.strip():
                    text += f"{i}. {r}\n"
        
        await msg.reply_text(text)
    
    async def cmd_clearwarns(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /clearwarns"""
        from handlers import UserResolver
        
        msg = update.message
        chat_id = msg.chat_id
        
        if not await self.permissions.is_group_admin(context.bot, msg.from_user.id, chat_id):
            await msg.reply_text("❌ Только администраторы могут сбрасывать варны.")
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
            await msg.reply_text("❌ Ответь на сообщение или укажи ID.")
            return
        
        self.db.clear_warns(chat_id, target_id)
        await msg.reply_text(f"✅ Все варны сняты с {target_name or target_id}.")
    
    def run(self):
        """Запуск бота"""
        logger.info("✅ Бот запущен")
        self.app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    bot = BotApplication()
    bot.run()