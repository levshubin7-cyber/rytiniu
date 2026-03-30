from dataclasses import dataclass
from typing import Optional


@dataclass
class User:
    """Модель пользователя"""
    user_id: int
    username: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    
    @property
    def full_name(self) -> str:
        """Полное имя пользователя"""
        if self.first_name:
            return self.first_name
        return self.username or str(self.user_id)
    
    @property
    def mention(self) -> str:
        """Упоминание пользователя"""
        return f"[{self.full_name}](tg://user?id={self.user_id})"
    
    @classmethod
    def from_telegram_user(cls, user) -> 'User':
        """Создание из объекта Telegram User"""
        return cls(
            user_id=user.id,
            username=user.username,
            first_name=user.first_name,
            last_name=user.last_name
        )