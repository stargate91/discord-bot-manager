import discord

class Icons:
    RESTART: discord.PartialEmoji = None
    UPDATE: discord.PartialEmoji = None
    STOP: discord.PartialEmoji = None
    
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

        cls.RESTART = get("restart", "<:arrowclockwise:1487098935787917394>")
        cls.UPDATE = get("update", "<:arrowsclockwise:1487098937256181866>")
        cls.STOP = get("stop", "<:power:1487098947272048811>")

# Default initialization
class DefaultConfig: emojis = {}
Icons.setup(DefaultConfig())
