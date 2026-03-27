import discord

class Icons:
    RESTART: discord.PartialEmoji = None
    UPDATE: discord.PartialEmoji = None
    STOP: discord.PartialEmoji = None
    
    @classmethod
    def setup(cls, config):
        """Initializes all icons from config or defaults."""
        from core.logger import log
        if hasattr(config, "emojis"):
            icons_data = config.emojis
        elif isinstance(config, dict):
            icons_data = config.get("emojis", {})
        else:
            icons_data = {}
        
        log.info(f"[Icons] Setting up with {len(icons_data)} custom emojis.")
        
        def get(name, default):
            val = icons_data.get(name, default)
            pe = discord.PartialEmoji.from_str(val)
            log.info(f"[Icons]   {name} -> {pe} (ID: {pe.id})")
            return pe

        cls.RESTART = get("restart", "🔄")
        cls.UPDATE = get("update", "🆙")
        cls.STOP = get("stop", "⏹️")

# Default initialization
class DefaultConfig: emojis = {}
Icons.setup(DefaultConfig())
