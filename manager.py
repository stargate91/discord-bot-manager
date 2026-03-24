import os
import sys
import subprocess
import json
import asyncio
import discord
from discord.ext import commands, tasks
from dotenv import load_dotenv
import psutil
from core.logger import log

# Load environment variables
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = os.getenv("GUILD_ID")
ADMIN_CHANNEL_ID = os.getenv("ADMIN_CHANNEL_ID")

# Configuration file path
CONFIG_FILE = "config.json"

class BotManager(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.members = True
        intents.message_content = True
        super().__init__(command_prefix="!", intents=intents)
        self.managed_processes = {} # {bot_id: psutil.Process}
        self.manual_stop = set() # {bot_id} to ignore alerts when intentional

    async def setup_hook(self):
        # Clear global commands from this bot identity to prevent crossover
        # DO THIS FIRST before loading extensions/cogs
        self.tree.clear_commands(guild=None)

        # Load extensions from cogs directory (relative to script location)
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
        else:
            log.error(f"Cogs directory NOT FOUND at {cogs_dir}")

        # Sync Slash Commands
        if GUILD_ID:
            guild = discord.Object(id=int(GUILD_ID))
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)
            log.info(f"Bot Manager: Slash commands synced to guild {GUILD_ID}.")
        else:
            await self.tree.sync()
            log.info("Bot Manager: Slash commands synced globally.")
        
        # Discover already running bots
        self.discover_existing_processes()
        self.check_processes.start()

    def load_config(self):
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        return {}

    def discover_existing_processes(self):
        """Scans running processes to find bots defined in config."""
        config = self.load_config()
        if not config:
            return

        log.info("Scanning for existing bot processes...")
        found_count = 0
        
        for proc in psutil.process_iter(['pid', 'name', 'cmdline', 'cwd']):
            try:
                cmdline = proc.info['cmdline']
                if not cmdline or len(cmdline) < 2:
                    continue
                
                # Check if it's a python process
                if 'python' not in cmdline[0].lower():
                    continue
                
                # Full command line as a string for easier matching
                cmd_str = " ".join(cmdline).lower()
                cwd = proc.info['cwd']
                if not cwd:
                    continue
                
                # Normalize CWD for comparison
                norm_cwd = os.path.normpath(cwd).lower()

                for bot_id, info in config.items():
                    if bot_id in self.managed_processes:
                        continue # Already tracking
                    
                    # Instead of matching the entire command (which includes 'python'), 
                    # we match everything EXCEPT the first part (the executable)
                    target_parts = info['cmd'].lower().split()
                    target_args = " ".join(target_parts[1:]) if len(target_parts) > 1 else target_parts[0]
                    target_path = os.path.normpath(info['path']).lower()
                    
                    # Match if the target args are in the cmdline AND (path is exact OR ends with the bot path)
                    path_match = (target_path == norm_cwd) or (norm_cwd.endswith(target_path.split(":")[-1].replace("\\", "/").strip("/").lower()))
                    cmd_match = target_args in cmd_str
                    
                    if cmd_match and path_match:
                        self.managed_processes[bot_id] = psutil.Process(proc.info['pid'])
                        log.info(f"Connected to existing bot: {info['name']} (PID: {proc.info['pid']})")
                        found_count += 1
                        break
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess) as e:
                # log.info(f"DEBUG: Process error for PID {proc.info.get('pid')}: {e}")
                continue
        
        if found_count > 0:
            log.info(f"Discovery complete. Found {found_count} running bots.")
        else:
            log.info("No matching bot processes found.")

    def save_config(self, config):
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=4)

    async def on_ready(self):
        # Set Presence
        count = len(self.load_config())
        activity = discord.Activity(
            type=discord.ActivityType.watching, 
            name=f"Pórázon tartok {count} botot... ⛓️"
        )
        await self.change_presence(activity=activity)
        log.info(f"Bot Manager online. Neural-link active. {self.user}")

    @tasks.loop(seconds=60)
    async def check_processes(self):
        config = self.load_config()
        for bot_id, info in config.items():
            process = self.managed_processes.get(bot_id)
            if process:
                if not process.is_running():
                    if bot_id not in self.manual_stop:
                        log.warning(f"ALERTI: Bot {info['name']} ({bot_id}) stopped unexpectedly.")
                        if ADMIN_CHANNEL_ID:
                            channel = self.get_channel(int(ADMIN_CHANNEL_ID))
                            if channel:
                                await channel.send(
                                    f"🚨 **ALERTI:** A(z) **{info['name']}** ({bot_id}) hirtelen leállt!\n"
                                    f"Szeretnéd, hogy újraindítsam? Használd a `/restart bot_id:{bot_id}` parancsot."
                                )
                    self.managed_processes.pop(bot_id, None)
            
            if bot_id in self.manual_stop:
                if not process or not process.is_running():
                    self.manual_stop.remove(bot_id)

    async def run_restart(self, bot_id):
        """Restarts a bot, or a group of bots if they share the same path."""
        config = self.load_config()
        if bot_id not in config:
            return "❌ A megadott Bot ID nem szerepel a konfigurációban."

        target_path = config[bot_id]["path"]
        related_bots = [bid for bid, info in config.items() if info["path"] == target_path]
        
        results = []
        for bid in related_bots:
            info = config[bid]
            try:
                # 1. Stop
                existing_proc = self.managed_processes.get(bid)
                if existing_proc and existing_proc.is_running():
                    self.manual_stop.add(bid)
                    existing_proc.terminate()
                    try:
                        existing_proc.wait(timeout=5)
                    except psutil.TimeoutExpired:
                        existing_proc.kill()
                    await asyncio.sleep(0.5)

                # 2. Restart (Clean Env)
                bot_env = os.environ.copy()
                for key in ["DISCORD_TOKEN", "GUILD_ID", "ADMIN_CHANNEL_ID"]:
                    bot_env.pop(key, None)

                new_proc = subprocess.Popen(
                    info["cmd"].split(), 
                    cwd=info["path"], 
                    env=bot_env,
                    creationflags=0x08000000 if os.name == 'nt' else 0
                )
                self.managed_processes[bid] = psutil.Process(new_proc.pid)
                results.append(f"✅ **{info['name']}** újraindítva (PID: {new_proc.pid})")
            except Exception as e:
                results.append(f"❌ **{info['name']}** hiba: {str(e)}")

        return "\n".join(results)

    async def run_update(self, bot_id):
        """Updates and restarts all bots sharing the same path."""
        config = self.load_config()
        if bot_id not in config:
            return "❌ A megadott Bot ID nem szerepel a konfigurációban."

        target_path = config[bot_id]["path"]
        related_bots = [bid for bid, info in config.items() if info["path"] == target_path]
        
        # 1. Stop all related bots first
        for bid in related_bots:
            existing_proc = self.managed_processes.get(bid)
            if existing_proc and existing_proc.is_running():
                self.manual_stop.add(bid)
                existing_proc.terminate()
                try:
                    existing_proc.wait(timeout=5)
                except psutil.TimeoutExpired:
                    existing_proc.kill()
        
        await asyncio.sleep(1) # Wait for file handles to release

        try:
            # 2. Update code (once per path)
            log.info(f"Updating shared path {target_path} via fetch + reset...")
            subprocess.run(["git", "fetch", "origin"], cwd=target_path, check=True)
            subprocess.run(["git", "reset", "--hard", "origin/main"], cwd=target_path, check=True)
            
            # 2b. Auto-pip
            pip_msg = ""
            req_path = os.path.join(target_path, "requirements.txt")
            if os.path.exists(req_path):
                try:
                    pip_result = subprocess.check_output(
                        [sys.executable, "-m", "pip", "install", "-r", "requirements.txt"], 
                        cwd=target_path, 
                        stderr=subprocess.STDOUT
                    ).decode('utf-8')
                    pip_msg = "\n\n**📦 Pip Install:**\n```\n" + (pip_result[-300:] if len(pip_result) > 300 else pip_result) + "\n```"
                except Exception as pip_err:
                    pip_msg = f"\n\n**❌ Pip Install Hiba:** `{str(pip_err)}`"

            # 3. Restart all related bots
            results = [f"✅ **Frissítés sikeres a közös mappában!** (FETCH_HEAD)" + pip_msg]
            for bid in related_bots:
                info = config[bid]
                bot_env = os.environ.copy()
                for key in ["DISCORD_TOKEN", "GUILD_ID", "ADMIN_CHANNEL_ID"]:
                    bot_env.pop(key, None)

                new_proc = subprocess.Popen(
                    info["cmd"].split(), 
                    cwd=info["path"], 
                    env=bot_env,
                    creationflags=0x08000000 if os.name == 'nt' else 0
                )
                self.managed_processes[bid] = psutil.Process(new_proc.pid)
                results.append(f"🚀 **{info['name']}** újraindítva (PID: {new_proc.pid})")
            
            return "\n".join(results)
        except Exception as e:
            return f"❌ Hiba történt a frissítés során: {str(e)}"

if __name__ == "__main__":
    bot = BotManager()
    if TOKEN:
        bot.run(TOKEN)
    else:
        log.error("Hiba: Nincs DISCORD_TOKEN megadva az .env fájlban!")
