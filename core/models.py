from dataclasses import dataclass, field
from typing import Optional, List

# This is a 'Data Class' - it's a simple way to store data in an object
@dataclass
class BotConfig:
    id: str
    name: str    # The name of the bot
    path: str    # Where the bot files are located on the disk
    cmd: str     # The command we run to start it (like 'python bot.py')
    log: Optional[str] = None # Where the bot saves its logs
    systemd_service: Optional[str] = None # The name of the systemd service (if any)
    description: Optional[str] = None # A short text about what the bot does
    git_branch: Optional[str] = None # Specific branch override
    db_files: List[str] = field(default_factory=list) # Optional list of .db files to track sizes

    @classmethod
    def from_dict(cls, bot_id: str, data: dict, default_log: str = "bot.log") -> 'BotConfig':
        """This function takes a dictionary and turns it into a BotConfig object."""
        # We use .get() so the bot doesn't crash if a piece of information is missing
        return cls(
            id=bot_id,
            name=data.get("name", "Unknown"),
            path=data.get("path", "."),
            cmd=data.get("cmd", ""),
            log=data.get("log", default_log),
            systemd_service=data.get("systemd_service"),
            description=data.get("description"),
            git_branch=data.get("git_branch"),
            db_files=data.get("db_files", [])
        )
