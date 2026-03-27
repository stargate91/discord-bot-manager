import discord

class Icons:
    RESTART: discord.PartialEmoji = None
    UPDATE: discord.PartialEmoji = None
    STOP: discord.PartialEmoji = None
    
    @classmethod
    async def setup_async(cls, bot: discord.Client):
        """Asynchronously fetches application emojis to ensure they are in cache."""
        from core.logger import log
        try:
            # Application emojis are available via fetch_application_emojis
            app_emojis = await bot.fetch_application_emojis()
            log.info(f"[Icons] Fetched {len(app_emojis)} application emojis.")
            # We don't need to do anything else, they are now in the bot's internal cache
            # and PartialEmoji with these IDs will work better.
        except Exception as e:
            log.error(f"[Icons] Failed to fetch application emojis: {e}")

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
                        log.info(f"[Icons]   {name} (Manual Parse) -> {pe} (ID: {pe.id})")
                        return pe
                except Exception as e:
                    log.error(f"[Icons] Manual parse failed for {val}: {e}")
            
            pe = discord.PartialEmoji.from_str(val)
            log.info(f"[Icons]   {name} -> {pe} (ID: {pe.id})")
            return pe

        cls.RESTART = get("restart", "🔄")
        cls.UPDATE = get("update", "🆙")
        cls.STOP = get("stop", "⏹️")

# Default initialization
class DefaultConfig: emojis = {}
Icons.setup(DefaultConfig())
