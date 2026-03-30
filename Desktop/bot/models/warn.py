from dataclasses import dataclass, field
from typing import List


@dataclass
class Warn:
    """Модель варна"""
    chat_id: int
    user_id: int
    count: int = 0
    reasons: List[str] = field(default_factory=list)
    
    def add_reason(self, reason: str):
        """Добавление причины"""
        if reason:
            self.reasons.append(reason)
            self.count += 1
    
    def remove_warn(self) -> int:
        """Удаление варна"""
        if self.count > 0:
            self.count -= 1
            if self.reasons:
                self.reasons.pop()
        return self.count
    
    def clear(self):
        """Очистка варнов"""
        self.count = 0
        self.reasons = []


@dataclass
class MuteDuration:
    """Длительность мута"""
    minutes: int
    
    @property
    def label(self) -> str:
        """Человекочитаемая метка"""
        from config import Config
        return Config.MUTE_LABELS.get(self.minutes, f"{self.minutes} минут")
    
    @property
    def is_permanent(self) -> bool:
        """Бессрочный ли мут"""
        return self.minutes == 0