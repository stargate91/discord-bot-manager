import os
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
        """This function takes a dictionary and turns it into a BotConfig object.
        
        Automatically selects platform-specific 'path_win'/'cmd_win' on Windows,
        falling back to the base 'path'/'cmd' fields if no override exists.
        """
        is_windows = os.name == 'nt'
        
        # Pick the right path and cmd for the current platform
        path = data.get("path_win", data.get("path", ".")) if is_windows else data.get("path", ".")
        cmd = data.get("cmd_win", data.get("cmd", "")) if is_windows else data.get("cmd", "")
        
        # systemd_service is Linux-only, ignore it on Windows
        systemd_service = None if is_windows else data.get("systemd_service")
        
        return cls(
            id=bot_id,
            name=data.get("name", "Unknown"),
            path=path,
            cmd=cmd,
            log=data.get("log", default_log),
            systemd_service=systemd_service,
            description=data.get("description"),
            git_branch=data.get("git_branch"),
            db_files=data.get("db_files", [])
        )
