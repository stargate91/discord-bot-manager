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

# We load our secrets from the .env file
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

# This is the name of our configuration file
CONFIG_FILE = "config.json"

# This is our main 'Bot Manager' - it's like a boss that controls other bots
class BotManager(commands.Bot):
    def __init__(self):
        # First, we load the configuration from the config.json file
        self.config = self.load_json(CONFIG_FILE)
        
        # We separate the settings into smaller groups for easier access
        settings = self.config.get("settings", {})
        bot_settings = self.config.get("bot_settings", {})
        
        # We start the 'Localization Service' so the bot can speak different languages
        self.language = bot_settings.get("language", "hu")
        self.i18n = LocalizationService(self.language)
        
        # We set up the prefix (like '!') and the 'intents' (permissions)
        prefix = bot_settings.get("command_prefix", "!")
        intents = discord.Intents.default()
        intents.members = True
        intents.message_content = True
        
        # We call the 'super' init to finish setting up the Discord bot
        super().__init__(command_prefix=prefix, intents=intents)
        
        # We initialize our helper services (ProcessManager and GitService)
        self.process_manager = ProcessManager(self.config, self.i18n.translations)
        self.git_service = GitService(self.config, self.i18n.translations)
        
        # We save the IDs for the server and the admin channel
        self.guild_id = settings.get("guild_id")
        self.admin_channel_id = settings.get("admin_channel_id")
        
        # How often we should check if bots are still running
        self.check_interval = bot_settings.get("check_interval_seconds", 60)
        # Which Git branch we should use for updates
        self.git_branch = bot_settings.get("git_branch", "origin/main")
        
        # We turn all our bots into 'BotConfig' objects
        default_log = bot_settings.get("bot_log_default", "bot.log")
        raw_bots = self.config.get("bots", {})
        self.bots = {bid: BotConfig.from_dict(bid, bdata, default_log) for bid, bdata in raw_bots.items()}

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
            with open(file_path, "r", encoding="utf-8") as f:
                return json.load(f)
        return {}

    def save_config(self, config):
        """This function saves our changes back to the config.json file."""
        self.config = config # Update our current copy in memory
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=4)

    async def setup_hook(self):
        """This runs once right after the bot connects to Discord."""
        # We clear any old commands to make sure everything is fresh
        self.tree.clear_commands(guild=None)

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
        
        # We 'sync' the slash commands so they show up in Discord
        if self.guild_id:
            guild = discord.Object(id=int(self.guild_id))
            self.tree.copy_global_to(guild=guild)
            # We translate the commands before syncing
            self.i18n.localize_commands(self.tree, guild)
            await self.tree.sync(guild=guild)
            log.info(f"Bot Manager: Slash commands synced to guild {self.guild_id}.")
        else:
            self.i18n.localize_commands(self.tree)
            await self.tree.sync()
            log.info("Bot Manager: Slash commands synced globally.")
        
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

        # We check if the manager was just restarted and notify the admins
        restart_info_path = os.path.join("tmp", "manager_restart.json")
        if os.path.exists(restart_info_path):
            try:
                if self.admin_channel_id:
                    channel = self.get_channel(int(self.admin_channel_id))
                    if channel:
                        msg = self.i18n.get("manager_online_log", "Manager {name} is back online.", name=self.manager_name)
                        await channel.send(msg)
                # We delete the temporary file after we're done
                os.remove(restart_info_path)
            except Exception as e:
                log.error(f"Failed to send restart notification: {e}")

    async def notify_admin(self, msg):
        """This is a helper function to send messages to our admin channel."""
        if self.admin_channel_id:
            channel = self.get_channel(int(self.admin_channel_id))
            if channel:
                await channel.send(msg)

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

    async def run_restart(self, bot_id):
        """This function restarts a bot (or several if they are in the same folder)."""
        if bot_id not in self.bots:
            return self.i18n.get("error_id_not_found", "Bot ID not found in config.")

        bot = self.bots[bot_id]
        # We find other bots that share the same folder, because they usually use the same code
        related_bots = [b for b in self.bots.values() if b.path == bot.path]
        
        results = []
        for b in related_bots:
            try:
                # 1. Stop the bot carefully
                await self.process_manager.stop_process(b.id)

                # 2. We prepare the 'environment' (variables) for the new bot process
                bot_env = os.environ.copy()
                # We don't want the manager's secret tokens to leak to the other bots
                for key in ["DISCORD_TOKEN", "GUILD_ID", "ADMIN_CHANNEL_ID"]:
                    bot_env.pop(key, None)
                
                # Tell the bot it's being managed
                bot_env["MANAGED_LOGGING"] = "1"
                bot_env["INSTANCE_NAME"] = b.cmd.split()[-1]

                # 3. Start the process using our service
                new_pid = self.process_manager.start_process(b.id, b, bot_env)
                
                success_msg = self.i18n.get("bot_restarted_simple", "", name=b.name, pid=new_pid)
                results.append(success_msg)
                # Log it in the admin channel too
                await self.notify_admin(self.i18n.get("bot_restarted_log", "Bot {name} ({id}) restarted.", name=b.name, id=b.id))
            except Exception as e:
                # If something fails, we catch the error here
                error_msg = self.i18n.get("restart_error", "", name=b.name, error=str(e))
                results.append(error_msg)

        return "\n".join(results)

    async def run_update(self, bot_id):
        """This function downloads the latest code and then restarts the bots."""
        if bot_id not in self.bots:
            return self.i18n.get("error_id_not_found", "Bot ID not found in config.")

        bot = self.bots[bot_id]
        related_bots = [b for b in self.bots.values() if b.path == bot.path]
        
        # 1. Stop all the bots that use this folder first
        for b in related_bots:
            await self.process_manager.stop_process(b.id)
        
        results = []
        try:
            # 2. We use GitService to update the code (this runs in a separate 'thread' to stay fast)
            log.info(f"Updating code at: {bot.path}")
            up_success, up_msg = await asyncio.to_thread(self.git_service.update_repo, bot.path, self.git_branch)
            results.append(up_msg)
            
            if not up_success:
                results.append(self.i18n.get("error_git_update_failed", "Git update failed."))
            else:
                # 3. We install any new libraries the bot might need
                pip_success, pip_msg = await asyncio.to_thread(self.git_service.install_dependencies, bot.path)
                results.append(pip_msg)

            # 4. Now we start all the bots back up
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
            # If the update process crashes, we log the error here
            log.error(f"Update error: {e}")
            return self.i18n.get("error_update_general", "Error during update: {error}", error=str(e))

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
