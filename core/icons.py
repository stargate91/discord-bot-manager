import discord

class Icons:
    RESTART: discord.PartialEmoji = None
    UPDATE: discord.PartialEmoji = None
    STOP: discord.PartialEmoji = None
    
    # Standard UI Icons (consistent with Watcher Bot)
    CHART: discord.PartialEmoji = None
    ROCKET: discord.PartialEmoji = None
    SUCCESS: discord.PartialEmoji = None
    TRASH: discord.PartialEmoji = None
    CONTROLLER: discord.PartialEmoji = None
    STATS: discord.PartialEmoji = None
    COMMUNITY: discord.PartialEmoji = None
    ERROR: discord.PartialEmoji = None
    WARNING: discord.PartialEmoji = None
    TOOLS: discord.PartialEmoji = None
    LIGHTNING: discord.PartialEmoji = None
    COOLDOWN: discord.PartialEmoji = None
    HELP: discord.PartialEmoji = None
    
    # New Visual Elements
    ALERT: discord.PartialEmoji = None
    LOG: discord.PartialEmoji = None
    PACKAGE: discord.PartialEmoji = None
    SHIELD: discord.PartialEmoji = None
    ROLLBACK: discord.PartialEmoji = None
    DOT_GREEN: discord.PartialEmoji = None
    DOT_RED: discord.PartialEmoji = None
    DOT_YELLOW: discord.PartialEmoji = None
    UP: discord.PartialEmoji = None
    DOWN: discord.PartialEmoji = None
    CHAIN: discord.PartialEmoji = None
    
    @classmethod
    async def setup_async(cls, bot: discord.Client):
        """Asynchronously fetches application emojis to ensure they are in cache and mapped."""
        from core.logger import log
        try:
            # Application emojis are available via fetch_application_emojis
            app_emojis = await bot.fetch_application_emojis()
            log.info(f"[Icons] Fetched {len(app_emojis)} application emojis.")
            
            # Map them by name if they are in our expected set
            for e in app_emojis:
                if e.name == "arrowclockwise":
                    cls.RESTART = e
                    log.info(f"[Icons]   Mapped {e.name} as RESTART icon (Full Emoji)")
                elif e.name == "arrowsclockwise":
                    cls.UPDATE = e
                    log.info(f"[Icons]   Mapped {e.name} as UPDATE icon (Full Emoji)")
                elif e.name == "power":
                    cls.STOP = e
                    log.info(f"[Icons]   Mapped {e.name} as STOP icon (Full Emoji)")
                    
        except Exception as e:
            log.error(f"[Icons] Failed to fetch/map application emojis: {e}")

    @classmethod
    def setup(cls, config):
        """Initializes all icons from config or defaults."""
        from core.logger import log
        
        # Default emojis (consistent with Watcher Bot where applicable)
        defaults = {
            "restart": "🔄", 
            "update": "🆙", 
            "stop": "⏹️",
            "CHART": "📊", "ROCKET": "🚀", "SUCCESS": "✅", "TRASH": "🗑️",
            "CONTROLLER": "🎮", "STATS": "📈", "COMMUNITY": "🤝", "ERROR": "❌",
            "WARNING": "⚠️", "TOOLS": "🛠️", "LIGHTNING": "⚡", 
            "COOLDOWN": "⏳", "HELP": "🆘",
            "ALERT": "🚨", "LOG": "📄", "PACKAGE": "📦", "SHIELD": "🛡️", "ROLLBACK": "⏮️",
            "DOT_GREEN": "🟢", "DOT_RED": "🔴", "DOT_YELLOW": "🟡",
            "UP": "⬆️", "DOWN": "⬇️", "CHAIN": "⛓️"
        }

        # Extract provided data from config object or dict
        provided_data = {}
        if hasattr(config, "emojis"):
            provided_data = config.emojis
        elif isinstance(config, dict):
            provided_data = config.get("emojis", {})

        # Normalize provided data to uppercase keys for easier mapping
        normalized_data = {k.upper(): v for k, v in provided_data.items()}
        
        log.info(f"[Icons] Setting up with {len(normalized_data)} custom emojis.")
        
        def parse_emoji(name, val):
            # Manual parse for custom emojis if from_str is failing in some environments
            if isinstance(val, str) and val.startswith("<") and ":" in val:
                try:
                    parts = val.strip("<>").split(":")
                    if len(parts) >= 3:
                        # Format is <:name:id> or <a:name:id>
                        eid = int(parts[-1])
                        ename = parts[-2]
                        eanim = parts[0] == "a"
                        pe = discord.PartialEmoji(name=ename, id=eid, animated=eanim)
                        return pe
                except Exception as e:
                    log.error(f"[Icons] Manual parse failed for {val}: {e}")
            
            try:
                return discord.PartialEmoji.from_str(val)
            except Exception as e:
                log.error(f"[Icons] discord.py failed to parse {val}: {e}")
                return discord.PartialEmoji.from_str("❓")

        # Define all supported icon keys (mapping to class attributes)
        # We handle the legacy lowercase ones (restart, update, stop) by mapping them to their uppercase counterparts
        legacy_map = {"RESTART": "RESTART", "UPDATE": "UPDATE", "STOP": "STOP"}
        all_keys = [
            "RESTART", "UPDATE", "STOP", "CHART", "ROCKET", "SUCCESS", "TRASH", 
            "CONTROLLER", "STATS", "COMMUNITY", "ERROR", "WARNING", "TOOLS", 
            "LIGHTNING", "COOLDOWN", "HELP", "ALERT", "LOG", "PACKAGE", "SHIELD", 
            "ROLLBACK", "DOT_GREEN", "DOT_RED", "DOT_YELLOW", "UP", "DOWN", "CHAIN"
        ]
        
        for key in all_keys:
            # We check normalized_data (uppercase) first
            val = normalized_data.get(key) or defaults.get(key.lower()) or defaults.get(key)
            if not val:
                val = "❓"
            
            setattr(cls, key, parse_emoji(key, val))
            # log.debug(f"[Icons]   {key} -> {getattr(cls, key)}")

# Default initialization
class DefaultConfig: emojis = {}
Icons.setup(DefaultConfig())
