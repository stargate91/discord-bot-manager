from dataclasses import dataclass
from typing import Optional

@dataclass
class BotConfig:
    id: str
    name: str
    path: str
    cmd: str
    log: Optional[str] = None
    description: Optional[str] = None

    @classmethod
    def from_dict(cls, bot_id: str, data: dict, default_log: str = "bot.log") -> 'BotConfig':
        return cls(
            id=bot_id,
            name=data.get("name", "Unknown"),
            path=data.get("path", "."),
            cmd=data.get("cmd", ""),
            log=data.get("log", default_log),
            description=data.get("description")
        )
