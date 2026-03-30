from dataclasses import dataclass
from typing import Optional


@dataclass
class Chat:
    """Модель чата"""
    chat_id: int
    title: str
    welcome_message: Optional[str] = None
    welcome_enabled: bool = False
    owner_id: Optional[int] = None