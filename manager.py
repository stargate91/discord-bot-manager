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
        # Load extensions from cogs directory
        for filename in os.listdir("./cogs"):
            if filename.endswith(".py") and not filename.startswith("__"):
                try:
                    await self.load_extension(f"cogs.{filename[:-3]}")
                    log.info(f"Loaded extension: {filename}")
                except Exception as e:
                    log.error(f"Failed to load extension {filename}: {e}")

        # Sync Slash Commands
        if GUILD_ID:
            guild = discord.Object(id=int(GUILD_ID))
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)
            log.info(f"Bot Manager: Slash commands synced to guild {GUILD_ID}.")
        else:
            await self.tree.sync()
            log.info("Bot Manager: Slash commands synced globally.")
        
        self.check_processes.start()

    def load_config(self):
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        return {}

    def save_config(self, config):
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=4)

    async def on_ready(self):
        # Set Presence
        count = len(self.load_config())
        activity = discord.Activity(
            type=discord.ActivityType.watching, 
            name=f"pórázon tartok {count} botot... ⛓️"
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

    async def run_update(self, bot_id):
        config = self.load_config()
        if bot_id not in config:
            return "❌ A megadott Bot ID nem szerepel a konfigurációban."

        info = config[bot_id]
        path = info["path"]
        
        try:
            # 1. Kill existing
            existing_proc = self.managed_processes.get(bot_id)
            if existing_proc and existing_proc.is_running():
                self.manual_stop.add(bot_id)
                existing_proc.terminate()
                try:
                    existing_proc.wait(timeout=5)
                except psutil.TimeoutExpired:
                    existing_proc.kill()

            # 2. Git Pull
            pull_result = subprocess.check_output(["git", "pull"], cwd=path, stderr=subprocess.STDOUT).decode('utf-8')
            
            # 3. Auto-pip
            pip_msg = ""
            req_path = os.path.join(path, "requirements.txt")
            if os.path.exists(req_path):
                try:
                    pip_result = subprocess.check_output(
                        [sys.executable, "-m", "pip", "install", "-r", "requirements.txt"], 
                        cwd=path, 
                        stderr=subprocess.STDOUT
                    ).decode('utf-8')
                    pip_msg = "\n\n**📦 Pip Install:**\n```\n" + (pip_result[-500:] if len(pip_result) > 500 else pip_result) + "\n```"
                except Exception as pip_err:
                    pip_msg = f"\n\n**❌ Pip Install Hiba:** `{str(pip_err)}`"

            # 4. Restart
            new_proc = subprocess.Popen(
                info["cmd"].split(), 
                cwd=path, 
                creationflags=0x08000000 if os.name == 'nt' else 0
            )
            self.managed_processes[bot_id] = psutil.Process(new_proc.pid)
            
            return f"✅ **Frissítés sikeres!**\n\n**Git kimenet:**\n```\n{pull_result}\n```" + pip_msg + f"\n\nBot újraindítva (PID: {new_proc.pid})."
        except Exception as e:
            return f"❌ Hiba történt: {str(e)}"

if __name__ == "__main__":
    bot = BotManager()
    if TOKEN:
        bot.run(TOKEN)
    else:
        log.error("Hiba: Nincs DISCORD_TOKEN megadva az .env fájlban!")
