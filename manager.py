import os
import sys
import json
import asyncio
import datetime
import subprocess
import psutil

import discord
from discord import app_commands
from discord.ext import commands, tasks
from dotenv import load_dotenv
from core.logger import log
from core.process_manager import ProcessManager
from core.git_service import GitService
from core.models import BotConfig
from core.i18n import LocalizationService
from core.management_service import ManagementService
from core.utils import get_feedback
from core.icons import Icons

# We load our secrets from the .env file
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

# This is the name of our configuration file
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(BASE_DIR, "config.json")
STATE_FILE = os.path.join(BASE_DIR, "state.json")

# This is our main 'Bot Manager' - it's like a boss that controls other bots
class BotManager(commands.Bot):
    def __init__(self):
        # Move log configuration to the very top to catch early issues
        self.config = self.load_json(CONFIG_FILE)
        bot_settings = self.config.get("bot_settings", {})
        from core.logger import reconfigure_log, setup_discord_logging
        log_file = bot_settings.get("manager_log_file", "manager.log")
        max_bytes = bot_settings.get("log_max_bytes", 5*1024*1024)
        backup_count = bot_settings.get("log_backup_count", 3)
        reconfigure_log(log_file, max_bytes, backup_count)
        # We no longer explicitly set discord logging to DEBUG to avoid interference and noise
        
        # First, we load the configuration from the config.json file
        log.info(f"Loading configuration from: {CONFIG_FILE}")
        
        # Initialize UI Icons
        from core.icons import Icons
        Icons.setup(bot_settings)
        log.info("[DEBUG] Icons setup complete.")
        
        if not self.config:
            log.error(f"CRITICAL: Configuration file not found or empty at {CONFIG_FILE}")
        
        # We separate the settings into smaller groups for easier access
        settings = self.config.get("settings", {})
        
        # We start the 'Localization Service' so the bot can speak different languages
        self.language = bot_settings.get("language", "hu")
        log.info(f"[DEBUG] Initializing LocalizationService for language: {self.language}")
        self.i18n = LocalizationService(self.language)
        log.info("[DEBUG] LocalizationService initialized.")
        
        # We load UI settings for accent colors and timeouts
        self.ui_settings = self.config.get("ui_settings", {})
        self.start_time = datetime.datetime.now()
        self.activity_index = 0
        self.last_net_io = psutil.net_io_counters()
        self.last_net_time = datetime.datetime.now()
        log.info(f"BotManager initialized at {self.start_time} (PID: {os.getpid()})")
        
        # We set up the prefix (like '!') and the 'intents' (permissions)
        self.command_prefix = bot_settings.get("command_prefix", "!")
        self.command_suffix = bot_settings.get("command_suffix", "")
        intents = discord.Intents.default()
        intents.members = True # Restored to True as in commit 16a2529
        intents.message_content = True
        
        # We call the 'super' init to finish setting up the Discord bot
        log.info("[DEBUG] Calling super().__init__")
        super().__init__(command_prefix=self.command_prefix, intents=intents)
        log.info("[DEBUG] super().__init__ complete.")
        
        # We initialize our helper services (ProcessManager and GitService)
        self.process_manager = ProcessManager(self.config, self.i18n.translations)
        self.git_service = GitService(self.config, self.i18n.translations)
        
        # We load the new access control settings (Roles and Channels)
        self.guild_id = settings.get("guild_id")
        self.access_control = settings.get("access_control", {})
        
        ac_roles = self.access_control.get("roles", {})
        ac_channels = self.access_control.get("channels", {})
        
        self.admin_channel_id = ac_channels.get("admin")
        self.public_channel_id = ac_channels.get("public")
        self.admin_role_id = ac_roles.get("admin")
        self.tester_role_id = ac_roles.get("tester")
        
        # How often we should check if bots are still running
        self.check_interval = bot_settings.get("check_interval_seconds", 60)
        # Which Git branch we should use for updates
        self.git_branch = bot_settings.get("git_branch", "origin/main")
        
        # Define missing variables needed for bot configuration
        raw_bots = self.config.get("bots", {})
        default_log = bot_settings.get("bot_log_default", "bot.log")

        self.bots = {bid: BotConfig.from_dict(bid, bdata, default_log) for bid, bdata in raw_bots.items()}
        log.info(f"Initialized manager with {len(self.bots)} bots. Guild ID: {self.guild_id}")

        # Load state
        self.state = self.load_json(STATE_FILE)

        # We initialize the ManagementService to handle high-level logic (Update & Restart)
        self.management_service = ManagementService(
            self.config, 
            self.i18n, 
            self.process_manager, 
            self.git_service, 
            self.bots,
            notify_admin_cb=self.notify_admin,
            manager_root_path=BASE_DIR
        )


    def save_state(self, key, value):
        """Saves a single key-value pair to the state.json file."""
        self.state[key] = value
        try:
            with open(STATE_FILE, "w", encoding="utf-8") as f:
                json.dump(self.state, f, indent=4)
        except Exception as e:
            log.error(f"Error saving state to {STATE_FILE}: {e}")

    @property
    def manager_name(self):
        """This function returns the name of this manager bot."""
        if self.guild_id and self.guilds:
            guild = self.get_guild(int(self.guild_id))
            if guild and guild.me:
                # Use the nickname on the server if it has one
                return guild.me.display_name
        # Otherwise, just use its username or a default name
        return self.user.name if self.user else get_feedback(self.i18n, "default_manager_name")

    @tasks.loop(seconds=30)
    async def update_activity_task(self):
        """Cycles through different mechanic-themed activities for FixItFixa."""
        try:
            activities = [
                "activity_maintenance",
                "activity_resource",
                "activity_network",
                "activity_status"
            ]
            
            key = activities[self.activity_index % len(activities)]
            self.activity_index += 1
            
            kwargs = {}
            if key == "activity_maintenance":
                kwargs["count"] = len(self.bots)
            elif key == "activity_resource":
                kwargs["cpu"] = int(psutil.cpu_percent())
                kwargs["ram"] = int(psutil.virtual_memory().used / (1024 * 1024))
            elif key == "activity_network":
                # Calculate network delta
                now = datetime.datetime.now()
                io = psutil.net_io_counters()
                dt = (now - self.last_net_time).total_seconds()
                
                if dt > 0:
                    down = (io.bytes_recv - self.last_net_io.bytes_recv) / dt
                    up = (io.bytes_sent - self.last_net_io.bytes_sent) / dt
                    
                    def format_bytes(b):
                        for unit in ['B/s', 'KB/s', 'MB/s']:
                            if b < 1024: return f"{b:.1f} {unit}"
                            b /= 1024
                        return f"{b:.1f} GB/s"
                        
                    kwargs["down"] = format_bytes(down)
                    kwargs["up"] = format_bytes(up)
                else:
                    kwargs["down"] = "0 B/s"
                    kwargs["up"] = "0 B/s"
                
                self.last_net_io = io
                self.last_net_time = now
            
            activity_text = get_feedback(self.i18n, key, **kwargs)
            
            # The name field for Activity cannot be too long
            if len(activity_text) > 120:
                activity_text = activity_text[:117] + "..."
                
            await self.change_presence(
                activity=discord.Activity(
                    type=discord.ActivityType.watching,
                    name=activity_text
                )
            )
        except Exception as e:
            log.error(f"[Activity] Error updating presence: {e}")

    @update_activity_task.before_loop
    async def before_update_activity_task(self):
        await self.wait_until_ready()

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
            log.info(f"[DEBUG] Loading extensions from {cogs_dir}...")
            for filename in os.listdir(cogs_dir):
                # We skip files that are not python scripts or are hidden
                if filename.endswith(".py") and not filename.startswith("__"):
                    try:
                        # We load the extension (e.g., 'cogs.admin')
                        log.info(f"[DEBUG] Loading extension: {filename}...")
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
        
        log.info("Starting background check loop...")
        # We start the background loop to keep checking them
        self.check_processes.change_interval(seconds=self.check_interval)
        self.check_processes.start()
        log.info("Background loop started. Waiting for Discord ready event...")

        # Global error handler for slash commands
        @self.tree.error
        async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
            if isinstance(error, app_commands.CheckFailure):
                # Try to get localized error message
                msg = get_feedback(self.i18n, "error_admin_context")
                if not interaction.response.is_done():
                    await interaction.response.send_message(msg, ephemeral=True)
                else:
                    await interaction.followup.send(msg, ephemeral=True)
                return

            log.error(f"Slash command error: {error}")
            if not interaction.response.is_done():
                await interaction.response.send_message(f"An error occurred: {error}", ephemeral=True)

    async def on_interaction(self, interaction: discord.Interaction):
        """Global interaction listener to handle persistent buttons."""
        if interaction.type == discord.InteractionType.component:
            custom_id = interaction.data.get("custom_id", "")
            if custom_id.startswith("status:"):
                # Handle status action via its custom_id (persistent behavior)
                # Format: status:bot_id:action
                parts = custom_id.split(":")
                if len(parts) >= 3:
                    bot_id = parts[1]
                    action = parts[2]
                    from core.views import handle_status_interaction
                    await handle_status_interaction(interaction, bot_id, action)
                    return # Action handled
        
        # Call the default interaction handler for everything else (like active Views)
        await super().on_interaction(interaction)

    async def on_connect(self):
        """Dispatched when the bot has connected to Discord."""
        log.info("[DEBUG] on_connect called. Manager connected to Discord (Gateway). Waiting for cache/ready...")

    async def on_shard_connect(self, shard_id):
        log.info(f"[DEBUG] on_shard_connect called. Shard {shard_id} connected to Gateway.")

    async def on_shard_ready(self, shard_id):
        log.info(f"Shard {shard_id} is ready.")

    async def on_ready(self):
        """This runs when the bot is fully online and ready to go."""
        # 1. IMMEDIATE: Initialize our Icons with custom emojis from config
        # This MUST happen before any UI is generated to prevent race conditions
        log.info("[Manager] Initializing themeable icon system...")
        from core.icons import Icons
        await Icons.setup_async(self)
        
        log.info(f"on_ready event received. Logged in as: {self.user} (ID: {self.user.id if self.user else 'None'})")
        
        # We wait a bit to ensure Discord's cache is fully ready
        await asyncio.sleep(2)
        
        # We set the bot's activity (what it is 'watching')
        count = len(self.bots)
        log.info(f"Bot Manager online. Neural-link active. {self.user} ({self.manager_name})")
        
        # Start the dynamic activity loop
        if not self.update_activity_task.is_running():
            self.update_activity_task.start()

        # Check if this was a planned restart/update
        temp_dir = self.config.get("bot_settings", {}).get("temp_dir", "tmp")
        restart_info_path = os.path.join(temp_dir, "manager_restart.json")
        is_restart = os.path.exists(restart_info_path)

        # Notify admins that the manager is online
        try:
            msg = get_feedback(self.i18n, "manager_online_log", name=self.manager_name, pid=os.getpid())
            await self.notify_admin(msg)
            
            # Clean up the restart flag
            if is_restart:
                if os.path.exists(restart_info_path):
                    os.remove(restart_info_path)
                log.info("Manager restart detected and handled. Cleanup complete.")
        except Exception as e:
            log.error(f"Failed to send startup notification: {e}")


    async def notify_admin(self, msg):
        """This is a helper function to send messages to our admin channel."""
        if self.admin_channel_id:
            channel = self.get_channel(int(self.admin_channel_id))
            if not channel:
                try:
                    channel = await self.fetch_channel(int(self.admin_channel_id))
                except:
                    pass
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
            # Log unrecognized commands to help debug suffix issues
            log.warning(f"Unrecognized command attempted: {ctx.message.content} from {ctx.author}")
            return # Ignore unknown commands visually in Discord, but log locally
            
        if isinstance(error, commands.CheckFailure):
            log.warning(f"Check failed for user {ctx.author} on command {ctx.command}: {error}")
            msg = get_feedback(self.i18n, "error_admin_context")
            await ctx.send(msg)
            return

        log.error(f"Error in prefix command {ctx.command if ctx.command else 'Unknown'}: {error}")
        # Try to send a generic error feedback if it wasn't a recognized check failure
        try:
            msg = f"{Icons.ERROR} Hiba történt: `{str(error)}`"
            await ctx.send(msg)
        except:
            pass

    @tasks.loop(seconds=60)
    async def check_processes(self):
        """This runs every minute to make sure all our bots are still running."""
        log.info("Manager Heartbeat: Checking processes...")
        
        # Track which bots were already alerted to avoid spam
        if not hasattr(self, 'alerted_bots'):
            self.alerted_bots = set()
            
        stopped_bots = self.process_manager.fetch_unexpected_stops()
        
        # 1. Handle Alerting for stopped bots
        for bot_id, _ in stopped_bots:
            bot_cfg = self.bots.get(bot_id)
            if not bot_cfg: continue
            
            # Only alert if we haven't already alerted for this specific failure
            if bot_id not in self.alerted_bots:
                log.warning(f"ALERT: Bot {bot_cfg.name} ({bot_id}) stopped unexpectedly.")
                alert_msg = get_feedback(self.i18n, "bot_stopped_alert", name=bot_cfg.name, id=bot_id)
                await self.notify_admin(alert_msg)
                self.alerted_bots.add(bot_id)
                
        # 2. Clear Alerts for running bots (so we can alert again if they fail later)
        for bot_id in list(self.alerted_bots):
            if self.process_manager.is_running(bot_id):
                self.alerted_bots.remove(bot_id)
                log.info(f"Bot {bot_id} is running again. Alert state cleared.")


# This is where the program starts!
if __name__ == "__main__":
    # Force SelectorEventLoop on Windows to fix Gateway handshake hangs with modern Python (3.12-3.14)
    if os.name == 'nt':
        import asyncio
        import sys
        # Note: In Python 3.14, ProactorEventLoop is the default and sometimes buggy with aiohttp/discord.py
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        log.info("[DEBUG] Event loop policy set to WindowsSelectorEventLoopPolicy.")

    # We create our Bot Manager object
    bot = BotManager()
    if TOKEN:
        # If we found the Discord token, we start the bot!
        bot.run(TOKEN)
    else:
        # If the token is missing, we log an error message
        log.error(get_feedback(bot.i18n, "error_no_token"))
