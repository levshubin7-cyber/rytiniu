from database import Database

def fix_admin():
    """Быстрое добавление администратора бота"""
    db = Database()
    
    print("🔧 ДОБАВЛЕНИЕ АДМИНИСТРАТОРА БОТА")
    print("=" * 50)
    
    # Получаем список чатов
    chats = db.get_all_chats()
    
    if not chats:
        print("❌ Чаты не найдены!")
        print("Сначала добавьте бота в чат")
        return
    
    print("\nДоступные чаты:")
    for i, chat in enumerate(chats, 1):
        print(f"{i}. {chat['title']} (ID: {chat['chat_id']})")
    
    # Выбираем чат
    choice = input("\nВыберите номер чата: ").strip()
    try:
        chat_idx = int(choice) - 1
        if chat_idx < 0 or chat_idx >= len(chats):
            print("❌ Неверный выбор!")
            return
        chat = chats[chat_idx]
    except ValueError:
        print("❌ Введите число!")
        return
    
    # Вводим ID пользователя
    user_id = input(f"Введите ID пользователя для чата {chat['title']}: ").strip()
    
    try:
        user_id = int(user_id)
        # Добавляем администратора
        db.add_bot_admin(user_id, chat['chat_id'], user_id)
        print(f"\n✅ Пользователь {user_id} добавлен как администратор бота в чате {chat['title']}")
        
        # Проверяем
        if db.is_bot_admin(user_id, chat['chat_id']):
            print("✅ Проверка пройдена: пользователь теперь администратор бота")
        else:
            print("❌ Ошибка: пользователь не добавлен")
            
    except ValueError:
        print("❌ ID должен быть числом!")
    except Exception as e:
        print(f"❌ Ошибка: {e}")

if __name__ == "__main__":
    fix_admin()