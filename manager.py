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

# Load environment variables
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

# Configuration file paths
CONFIG_FILE = "config.json"

class BotManager(commands.Bot):
    def __init__(self):
        # Load initial configuration
        self.config = self.load_json(CONFIG_FILE)
        
        settings = self.config.get("settings", {})
        bot_settings = self.config.get("bot_settings", {})
        
        # Initialize Localization Service
        self.language = bot_settings.get("language", "hu")
        self.i18n = LocalizationService(self.language)
        
        prefix = bot_settings.get("command_prefix", "!")
        intents = discord.Intents.default()
        intents.members = True
        intents.message_content = True
        
        super().__init__(command_prefix=prefix, intents=intents)
        
        # Services
        self.process_manager = ProcessManager(self.config, self.i18n.translations)
        self.git_service = GitService(self.config, self.i18n.translations)
        
        self.guild_id = settings.get("guild_id")
        self.admin_channel_id = settings.get("admin_channel_id")
        
        self.check_interval = bot_settings.get("check_interval_seconds", 60)
        self.git_branch = bot_settings.get("git_branch", "origin/main")
        
        # Parse bots into a dictionary of BotConfig objects
        default_log = bot_settings.get("bot_log_default", "bot.log")
        raw_bots = self.config.get("bots", {})
        self.bots = {bid: BotConfig.from_dict(bid, bdata, default_log) for bid, bdata in raw_bots.items()}

    @property
    def manager_name(self):
        """Returns the bot's name on the current server if available, else its username."""
        if self.guild_id and self.guilds:
            guild = self.get_guild(int(self.guild_id))
            if guild and guild.me:
                return guild.me.display_name
        return self.user.name if self.user else self.i18n.get("default_manager_name", "Bot Manager")

    def load_json(self, file_path):
        if os.path.exists(file_path):
            with open(file_path, "r", encoding="utf-8") as f:
                return json.load(f)
        return {}

    def save_config(self, config):
        self.config = config # Update in-memory copy too
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=4)

    async def setup_hook(self):
        # Clear global commands from this bot identity to prevent crossover
        self.tree.clear_commands(guild=None)

        # Load extensions from cogs directory
        base_dir = os.path.dirname(os.path.abspath(__file__))
        cogs_dir = os.path.join(base_dir, "cogs")
        
        if os.path.exists(cogs_dir):
            for filename in os.listdir(cogs_dir):
                if filename.endswith(".py") and not filename.startswith("__"):
                    try:
                        await self.load_extension(f"cogs.{filename[:-3]}")
                        log.info(f"Loaded extension: {filename}")
                    except Exception as e:
                        log.error(f"Failed to load extension {filename}: {e}")
        
        # Sync Slash Commands
        if self.guild_id:
            guild = discord.Object(id=int(self.guild_id))
            self.tree.copy_global_to(guild=guild)
            self.i18n.localize_commands(self.tree, guild)
            await self.tree.sync(guild=guild)
            log.info(f"Bot Manager: Slash commands synced to guild {self.guild_id}.")
        else:
            self.i18n.localize_commands(self.tree)
            await self.tree.sync()
            log.info("Bot Manager: Slash commands synced globally.")
        
        # Discover already running bots
        self.process_manager.discover_processes()
        self.check_processes.change_interval(seconds=self.check_interval)
        self.check_processes.start()

    async def on_ready(self):
        # Set Presence
        count = len(self.bots)
        activity_msg = self.i18n.get("activity_text", "Watching {count} bots...", count=count)
        
        activity = discord.Activity(
            type=discord.ActivityType.watching, 
            name=activity_msg
        )
        await self.change_presence(activity=activity)
        log.info(f"Bot Manager online. Neural-link active. {self.user} ({self.manager_name})")

        # Check for pending restart notification
        restart_info_path = os.path.join("tmp", "manager_restart.json")
        if os.path.exists(restart_info_path):
            try:
                if self.admin_channel_id:
                    channel = self.get_channel(int(self.admin_channel_id))
                    if channel:
                        msg = self.i18n.get("manager_online_log", "Manager {name} is back online.", name=self.manager_name)
                        await channel.send(msg)
                os.remove(restart_info_path)
            except Exception as e:
                log.error(f"Failed to send restart notification: {e}")

    async def notify_admin(self, msg):
        """Helper to send a message to the admin channel."""
        if self.admin_channel_id:
            channel = self.get_channel(int(self.admin_channel_id))
            if channel:
                await channel.send(msg)

    @tasks.loop(seconds=60)
    async def check_processes(self):
        stopped_bots = self.process_manager.fetch_unexpected_stops()
        for bot_id, _ in stopped_bots:
            bot = self.bots.get(bot_id)
            if not bot: continue
            
            log.warning(f"ALERT: Bot {bot.name} ({bot_id}) stopped unexpectedly.")
            if self.admin_channel_id:
                channel = self.get_channel(int(self.admin_channel_id))
                if channel:
                    alert_msg = self.i18n.get("bot_stopped_alert", "", name=bot.name, id=bot_id)
                    await channel.send(alert_msg)

    async def run_restart(self, bot_id):
        """Restarts a bot, or a group of bots if they share the same path."""
        if bot_id not in self.bots:
            return self.i18n.get("error_id_not_found", "Bot ID not found in config.")

        bot = self.bots[bot_id]
        related_bots = [b for b in self.bots.values() if b.path == bot.path]
        
        results = []
        for b in related_bots:
            try:
                # 1. Stop
                await self.process_manager.stop_process(b.id)

                # 2. Restart (Clean Env)
                bot_env = os.environ.copy()
                for key in ["DISCORD_TOKEN", "GUILD_ID", "ADMIN_CHANNEL_ID"]:
                    bot_env.pop(key, None)
                
                bot_env["MANAGED_LOGGING"] = "1"
                bot_env["INSTANCE_NAME"] = b.cmd.split()[-1]

                # Start process via service
                new_pid = self.process_manager.start_process(b.id, b, bot_env)
                
                success_msg = self.i18n.get("bot_restarted_simple", "", name=b.name, pid=new_pid)
                results.append(success_msg)
                await self.notify_admin(self.i18n.get("bot_restarted_log", "Bot {name} ({id}) restarted.", name=b.name, id=b.id))
            except Exception as e:
                error_msg = self.i18n.get("restart_error", "", name=b.name, error=str(e))
                results.append(error_msg)

        return "\n".join(results)

    async def run_update(self, bot_id):
        """Updates and restarts all bots sharing the same path."""
        if bot_id not in self.bots:
            return self.i18n.get("error_id_not_found", "Bot ID not found in config.")

        bot = self.bots[bot_id]
        related_bots = [b for b in self.bots.values() if b.path == bot.path]
        
        # 1. Stop all related bots
        for b in related_bots:
            await self.process_manager.stop_process(b.id)
        
        results = []
        try:
            # 2. Update code via GitService (Run in thread)
            log.info(f"Updating code at: {bot.path}")
            up_success, up_msg = await asyncio.to_thread(self.git_service.update_repo, bot.path, self.git_branch)
            results.append(up_msg)
            
            if not up_success:
                results.append(self.i18n.get("error_git_update_failed", "Git update failed."))
            else:
                # 3. Install requirements (Run in thread)
                pip_success, pip_msg = await asyncio.to_thread(self.git_service.install_dependencies, bot.path)
                results.append(pip_msg)

            # 4. Restart all related bots
            for b in related_bots:
                bot_env = os.environ.copy()
                for key in ["DISCORD_TOKEN", "GUILD_ID", "ADMIN_CHANNEL_ID"]:
                    bot_env.pop(key, None)

                bot_env["MANAGED_LOGGING"] = "1"
                bot_env["INSTANCE_NAME"] = b.cmd.split()[-1]

                new_pid = self.process_manager.start_process(b.id, b, bot_env)
                restart_msg = self.i18n.get("bot_restarted_simple", "", name=b.name, pid=new_pid)
                results.append(restart_msg)
                await self.notify_admin(self.i18n.get("bot_restarted_log", "Bot {name} ({id}) restarted.", name=b.name, id=b.id))
            
            return "\n".join(results)
        except Exception as e:
            log.error(f"Update error: {e}")
            return self.i18n.get("error_update_general", "Error during update: {error}", error=str(e))

if __name__ == "__main__":
    bot = BotManager()
    if TOKEN:
        bot.run(TOKEN)
    else:
        log.error(bot.i18n.get("error_no_token", "Error: DISCORD_TOKEN not found in .env!"))
