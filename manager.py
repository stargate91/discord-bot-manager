import os
import sys
import json
import asyncio
import discord
from discord.ext import commands, tasks
from dotenv import load_dotenv
from core.logger import log
from core.process_manager import ProcessManager
from core.git_service import GitService
from core.models import BotConfig
from core.i18n import LocalizationService
from core.management_service import ManagementService

# We load our secrets from the .env file
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

# This is the name of our configuration file
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(BASE_DIR, "config.json")

# This is our main 'Bot Manager' - it's like a boss that controls other bots
class BotManager(commands.Bot):
    def __init__(self):
        # First, we load the configuration from the config.json file
        log.info(f"Loading configuration from: {CONFIG_FILE}")
        self.config = self.load_json(CONFIG_FILE)
        
        # Initialize UI Icons
        from core.icons import Icons
        Icons.setup(self.config.get("bot_settings", {}))
        
        if not self.config:
            log.error(f"CRITICAL: Configuration file not found or empty at {CONFIG_FILE}")
        
        # We separate the settings into smaller groups for easier access
        settings = self.config.get("settings", {})
        bot_settings = self.config.get("bot_settings", {})
        
        # Apply log configuration from config.json
        from core.logger import reconfigure_log
        log_file = bot_settings.get("manager_log_file", "manager.log")
        max_bytes = bot_settings.get("log_max_bytes", 5*1024*1024)
        backup_count = bot_settings.get("log_backup_count", 3)
        reconfigure_log(log_file, max_bytes, backup_count)
        
        # We start the 'Localization Service' so the bot can speak different languages
        self.language = bot_settings.get("language", "hu")
        self.i18n = LocalizationService(self.language)
        
        # We load UI settings for accent colors and timeouts
        self.ui_settings = self.config.get("ui_settings", {})
        
        # We set up the prefix (like '!') and the 'intents' (permissions)
        self.command_prefix = bot_settings.get("command_prefix", "!")
        self.command_suffix = bot_settings.get("command_suffix", "")
        intents = discord.Intents.default()
        intents.members = True
        intents.message_content = True
        
        # We call the 'super' init to finish setting up the Discord bot
        super().__init__(command_prefix=self.command_prefix, intents=intents)
        
        # We initialize our helper services (ProcessManager and GitService)
        self.process_manager = ProcessManager(self.config, self.i18n.translations)
        self.git_service = GitService(self.config, self.i18n.translations)
        
        # We save the IDs for the server and the admin channel
        self.guild_id = settings.get("guild_id")
        self.admin_channel_id = settings.get("admin_channel_id")
        self.admin_role_id = settings.get("admin_role_id")
        
        # How often we should check if bots are still running
        self.check_interval = bot_settings.get("check_interval_seconds", 60)
        # Which Git branch we should use for updates
        self.git_branch = bot_settings.get("git_branch", "origin/main")
        
        # Define missing variables needed for bot configuration
        raw_bots = self.config.get("bots", {})
        default_log = bot_settings.get("bot_log_default", "bot.log")

        self.bots = {bid: BotConfig.from_dict(bid, bdata, default_log) for bid, bdata in raw_bots.items()}
        log.info(f"Initialized manager with {len(self.bots)} bots. Guild ID: {self.guild_id}")

        # We initialize the ManagementService to handle high-level logic (Update & Restart)
        self.management_service = ManagementService(
            self.config, 
            self.i18n, 
            self.process_manager, 
            self.git_service, 
            self.bots,
            notify_admin_cb=self.notify_admin
        )

    @property
    def manager_name(self):
        """This function returns the name of this manager bot."""
        if self.guild_id and self.guilds:
            guild = self.get_guild(int(self.guild_id))
            if guild and guild.me:
                # Use the nickname on the server if it has one
                return guild.me.display_name
        # Otherwise, just use its username or a default name
        return self.user.name if self.user else self.i18n.get("default_manager_name", "Bot Manager")

    def load_json(self, file_path):
        """This helper function loads a JSON file and returns a dictionary."""
        if os.path.exists(file_path):
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                log.error(f"Error reading JSON from {file_path}: {e}")
                return {}
        log.warning(f"File not found: {file_path}")
        return {}

    def save_config(self, config):
        """This function saves our changes back to the config.json file."""
        self.config = config # Update our current copy in memory
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=4)

    async def setup_hook(self):
        """This runs once right after the bot connects to Discord."""
        # (We no longer clear commands on every startup to prevent sync issues)

        # We look for all the files in the 'cogs' folder to load extra features
        base_dir = os.path.dirname(os.path.abspath(__file__))
        cogs_dir = os.path.join(base_dir, "cogs")
        
        if os.path.exists(cogs_dir):
            for filename in os.listdir(cogs_dir):
                # We skip files that are not python scripts or are hidden
                if filename.endswith(".py") and not filename.startswith("__"):
                    try:
                        # We load the extension (e.g., 'cogs.admin')
                        await self.load_extension(f"cogs.{filename[:-3]}")
                        log.info(f"Loaded extension: {filename}")
                    except Exception as e:
                        log.error(f"Failed to load extension {filename}: {e}")
        
        # Log how many commands we have in the tree
        log.info(f"Total commands in tree: {len(self.tree.get_commands())}")
        for cmd in self.tree.get_commands():
            log.info(f"  - /{cmd.name}")
        
        # Synchronizing slash commands can take a long time on startup.
        # Instead, we now use the manual '!sync' or '/sync' commands in the admin channel.
        log.info(f"Extensions loaded. Use {self.command_prefix}sync to propagate slash commands to Discord.")
        
        # Setup icons asynchronously (fetch application emojis)
        from core.icons import Icons
        await Icons.setup_async(self)
        
        # We check if any bots are already running on the computer
        self.process_manager.discover_processes()
        # We start the background loop to keep checking them
        self.check_processes.change_interval(seconds=self.check_interval)
        self.check_processes.start()

    async def on_ready(self):
        """This runs when the bot is fully online and ready to go."""
        # We set the bot's activity (what it is 'watching')
        count = len(self.bots)
        activity_msg = self.i18n.get("activity_text", "Watching {count} bots...", count=count)
        
        activity = discord.Activity(
            type=discord.ActivityType.watching, 
            name=activity_msg
        )
        await self.change_presence(activity=activity)
        log.info(f"Bot Manager online. Neural-link active. {self.user} ({self.manager_name})")

        # Notify admins that the manager is online (always)
        try:
            if self.admin_channel_id:
                channel = self.get_channel(int(self.admin_channel_id))
                if channel:
                    msg = self.i18n.get("manager_online_log", "Manager {name} is back online.", name=self.manager_name)
                    await channel.send(msg)
            
            # We 2026-03-27 18:59:09,915 - BotManager - INFO - [Message] From climaxim in #bot-fejlesztés🤖: !clear_commands_bup the temporary file if it exists
            temp_dir = self.config.get("bot_settings", {}).get("temp_dir", "tmp")
            restart_info_path = os.path.join(temp_dir, "manager_restart.json")
            if os.path.exists(restart_info_path):
                os.remove(restart_info_path)
        except Exception as e:
            log.error(f"Failed to send startup notification: {e}")

    async def notify_admin(self, msg):
        """This is a helper function to send messages to our admin channel."""
        if self.admin_channel_id:
            channel = self.get_channel(int(self.admin_channel_id))
            if channel:
                await channel.send(msg)

    async def on_message(self, message):
        """Log incoming messages to debug prefix commands."""
        if message.author.bot:
            return
            
        log.info(f"[Message] From {message.author} in #{message.channel} (ID: {message.channel.id}): {message.content}")
        await self.process_commands(message)

    async def on_command_error(self, ctx, error):
        """Global error handler for prefix commands."""
        if isinstance(error, commands.CommandNotFound):
            return # Ignore unknown commands
            
        if isinstance(error, commands.CheckFailure):
            log.warning(f"Check failed for user {ctx.author} on command {ctx.command}: {error}")
            return

        log.error(f"Error in prefix command {ctx.command}: {error}")

    @tasks.loop(seconds=60)
    async def check_processes(self):
        """This runs every minute to make sure all our bots are still running."""
        stopped_bots = self.process_manager.fetch_unexpected_stops()
        for bot_id, _ in stopped_bots:
            bot = self.bots.get(bot_id)
            if not bot: continue
            
            # If a bot stopped when it wasn't supposed to, we alert the admins
            log.warning(f"ALERT: Bot {bot.name} ({bot_id}) stopped unexpectedly.")
            if self.admin_channel_id:
                channel = self.get_channel(int(self.admin_channel_id))
                if channel:
                    alert_msg = self.i18n.get("bot_stopped_alert", "", name=bot.name, id=bot_id)
                    await channel.send(alert_msg)


# This is where the program starts!
if __name__ == "__main__":
    # We create our Bot Manager object
    bot = BotManager()
    if TOKEN:
        # If we found the Discord token, we start the bot!
        bot.run(TOKEN)
    else:
        # If the token is missing, we log an error message
        log.error(bot.i18n.get("error_no_token", "Error: DISCORD_TOKEN not found in .env!"))
