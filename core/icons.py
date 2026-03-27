import discord

class Icons:
    RESTART: discord.PartialEmoji = None
    UPDATE: discord.PartialEmoji = None
    STOP: discord.PartialEmoji = None
    
    @classmethod
    def setup(cls, config):
        """Initializes all icons from config or defaults."""
        if hasattr(config, "emojis"):
            icons_data = config.emojis
        elif isinstance(config, dict):
            icons_data = config.get("emojis", {})
        else:
            icons_data = {}
        
        def get(name, default):
            return discord.PartialEmoji.from_str(icons_data.get(name, default))

        cls.RESTART = get("restart", "🔄")
        cls.UPDATE = get("update", "🆙")
        cls.STOP = get("stop", "⏹️")

# Default initialization
class DefaultConfig: emojis = {}
Icons.setup(DefaultConfig())
