import discord
from discord import app_commands
from discord.ext import commands
import os
import json
import asyncio
import subprocess
import sys
import psutil
from collections import deque
from core.utils import is_admin_context
from core.logger import log

async def bot_id_autocomplete(
    interaction: discord.Interaction,
    current: str,
) -> list[app_commands.Choice[str]]:
    # Simple relative path based on Cwd
    config_file = "config.json"
    if os.path.exists(config_file):
        with open(config_file, "r", encoding="utf-8") as f:
            config = json.load(f)
        return [
            app_commands.Choice(name=info["name"], value=bot_id)
            for bot_id, info in config.items() if current.lower() in info["name"].lower()
        ][:25]
    return []

class ManagementCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="update", description="Git pull és újraindítás egy botnál ID alapján.")
    @app_commands.describe(bot_id="Válassz egy botot a listából")
    @is_admin_context()
    @app_commands.autocomplete(bot_id=bot_id_autocomplete)
    async def update(self, interaction: discord.Interaction, bot_id: str):
        log.info(f"User {interaction.user} (ID: {interaction.user_id}) requested /update for bot: {bot_id}")
        await interaction.response.defer(ephemeral=True)
        result = await self.bot.run_update(bot_id)
        await interaction.followup.send(result, ephemeral=True)

    @app_commands.command(name="restart", description="Bot újraindítása frissítés nélkül.")
    @app_commands.describe(bot_id="Válassz egy botot a listából")
    @is_admin_context()
    @app_commands.autocomplete(bot_id=bot_id_autocomplete)
    async def restart(self, interaction: discord.Interaction, bot_id: str):
        log.info(f"User {interaction.user} (ID: {interaction.user_id}) requested /restart for bot: {bot_id}")
        await interaction.response.defer(ephemeral=True)
        
        config = self.bot.load_config()
        if bot_id not in config:
            await interaction.followup.send("❌ Ismeretlen Bot ID.", ephemeral=True)
            return
            
        info = config[bot_id]
        path = info["path"]
        
        try:
            existing_proc = self.bot.managed_processes.get(bot_id)
            if existing_proc and existing_proc.is_running():
                self.bot.manual_stop.add(bot_id)
                existing_proc.terminate()
            
            new_proc = subprocess.Popen(
                info["cmd"].split(), 
                cwd=path, 
                creationflags=0x08000000 if os.name == 'nt' else 0
            )
            self.bot.managed_processes[bot_id] = psutil.Process(new_proc.pid)
            await interaction.followup.send(f"✅ **{info['name']}** újraindítva (PID: {new_proc.pid}).", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"❌ Hiba: {str(e)}", ephemeral=True)

    @app_commands.command(name="rollback", description="Visszaállítja a botot az előző Git állapotra (HEAD@{1}).")
    @app_commands.describe(bot_id="Válassz egy botot a listából")
    @is_admin_context()
    @app_commands.autocomplete(bot_id=bot_id_autocomplete)
    async def rollback(self, interaction: discord.Interaction, bot_id: str):
        log.info(f"User {interaction.user} (ID: {interaction.user_id}) requested /rollback for bot: {bot_id}")
        await interaction.response.defer(ephemeral=True)
        
        config = self.bot.load_config()
        if bot_id not in config:
            await interaction.followup.send("❌ Ismeretlen Bot ID.", ephemeral=True)
            return
            
        info = config[bot_id]
        path = info["path"]
        
        try:
            reset_result = subprocess.check_output(
                ["git", "reset", "--hard", "HEAD@{1}"], 
                cwd=path, 
                stderr=subprocess.STDOUT
            ).decode('utf-8')
            
            existing_proc = self.bot.managed_processes.get(bot_id)
            if existing_proc and existing_proc.is_running():
                self.bot.manual_stop.add(bot_id)
                existing_proc.terminate()
                
            new_proc = subprocess.Popen(
                info["cmd"].split(), 
                cwd=path, 
                creationflags=0x08000000 if os.name == 'nt' else 0
            )
            self.bot.managed_processes[bot_id] = psutil.Process(new_proc.pid)
            
            await interaction.followup.send(
                f"✅ **Visszaállítás sikeres!**\n\n**Git kimenet:**\n```\n{reset_result}\n```\nBot újraindítva a régi verzióval (PID: {new_proc.pid}).",
                ephemeral=True
            )
        except Exception as e:
            await interaction.followup.send(f"❌ Hiba a visszaállítás során: {str(e)}", ephemeral=True)

    @app_commands.command(name="logs", description="Lekéri egy bot log fájljának utolsó N sorát.")
    @app_commands.describe(bot_id="Válassz egy botot a listából", lines="Lekérendő sorok száma (alapértelmezett: 50, összes: 0)")
    @is_admin_context()
    @app_commands.autocomplete(bot_id=bot_id_autocomplete)
    async def logs(self, interaction: discord.Interaction, bot_id: str, lines: int = 50):
        log.info(f"User {interaction.user} (ID: {interaction.user_id}) requested /logs ({lines} lines) for bot: {bot_id}")
        await interaction.response.defer(ephemeral=True)
        
        config = self.bot.load_config()
        if bot_id not in config:
            await interaction.followup.send("❌ Ismeretlen Bot ID.", ephemeral=True)
            return
            
        info = config[bot_id]
        log_name = info.get("log", "bot.log")
        log_path = os.path.join(info["path"], log_name)
        
        if os.path.exists(log_path):
            try:
                if lines > 0:
                    with open(log_path, "r", encoding="utf-8", errors="replace") as f:
                        last_lines = deque(f, maxlen=lines)
                    
                    content = "".join(last_lines)
                    if not content:
                        await interaction.followup.send("ℹ️ A log fájl üres.", ephemeral=True)
                        return

                    temp_file = "temp_logs.txt"
                    with open(temp_file, "w", encoding="utf-8") as f:
                        f.write(content)
                    
                    file = discord.File(temp_file, filename=f"{info['name']}_last_{lines}_lines.txt")
                    await interaction.followup.send(f"📄 **{info['name']}** utolsó {lines} sora:", file=file, ephemeral=True)
                    os.remove(temp_file)
                else:
                    file = discord.File(log_path, filename=f"{info['name']}_full_logs.txt")
                    await interaction.followup.send(f"📄 **{info['name']}** teljes logja:", file=file, ephemeral=True)
            except Exception as e:
                await interaction.followup.send(f"❌ Hiba a logok lekérésekor: {str(e)}", ephemeral=True)
        else:
            await interaction.followup.send(f"❌ Nem található log fájl itt: `{log_path}`", ephemeral=True)

    @app_commands.command(name="manager-logs", description="Lekéri a Bot Manager saját log fájljának utolsó N sorát.")
    @app_commands.describe(lines="Lekérendő sorok száma (alapértelmezett: 50, összes: 0)")
    @is_admin_context()
    async def manager_logs(self, interaction: discord.Interaction, lines: int = 50):
        log.info(f"User {interaction.user} (ID: {interaction.user_id}) requested /manager-logs ({lines} lines)")
        await interaction.response.defer(ephemeral=True)
        
        log_path = "manager.log"
        
        if os.path.exists(log_path):
            try:
                if lines > 0:
                    with open(log_path, "r", encoding="utf-8", errors="replace") as f:
                        last_lines = deque(f, maxlen=lines)
                    
                    content = "".join(last_lines)
                    if not content:
                        await interaction.followup.send("ℹ️ A Manager log fájl üres.", ephemeral=True)
                        return

                    temp_file = "temp_manager_logs.txt"
                    with open(temp_file, "w", encoding="utf-8") as f:
                        f.write(content)
                    
                    file = discord.File(temp_file, filename=f"manager_last_{lines}_lines.txt")
                    await interaction.followup.send(f"📄 **Bot Manager** utolsó {lines} sora:", file=file, ephemeral=True)
                    os.remove(temp_file)
                else:
                    file = discord.File(log_path, filename="manager_full_logs.txt")
                    await interaction.followup.send(f"📄 **Bot Manager** teljes logja:", file=file, ephemeral=True)
            except Exception as e:
                await interaction.followup.send(f"❌ Hiba a Manager logok lekérésekor: {str(e)}", ephemeral=True)
        else:
            await interaction.followup.send("❌ Nem található a `manager.log` fájl.", ephemeral=True)

    @app_commands.command(name="manager-restart", description="[Admin] A Bot Manager (FixItFixa) azonnali újraindítása.")
    @is_admin_context()
    async def manager_restart(self, interaction: discord.Interaction):
        log.info(f"User {interaction.user} requested /manager-restart. Restarting FixItFixa...")
        await interaction.response.send_message("🔄 **FixItFixa** újraindítása...", ephemeral=True)
        os.execv(sys.executable, ['python'] + sys.argv)

    @app_commands.command(name="manager-update", description="[Admin] Git pull, pip install és újraindítás a Bot Managerhez.")
    @is_admin_context()
    async def manager_update(self, interaction: discord.Interaction):
        log.info(f"User {interaction.user} requested /manager-update for FixItFixa.")
        await interaction.response.defer(ephemeral=True)
        
        try:
            # 1. Git Pull
            pull_result = subprocess.check_output(["git", "pull"], stderr=subprocess.STDOUT).decode('utf-8')
            
            # 2. Pip Install
            pip_msg = ""
            if os.path.exists("requirements.txt"):
                try:
                    subprocess.check_output(
                        [sys.executable, "-m", "pip", "install", "-r", "requirements.txt"], 
                        stderr=subprocess.STDOUT
                    ).decode('utf-8')
                    pip_msg = "\n📦 **Pip frissítve.**"
                except Exception as pip_err:
                    pip_msg = f"\n⚠️ **Pip hiba:** `{str(pip_err)}`"

            await interaction.followup.send(
                f"✅ **FixItFixa frissítve!**\n```\n{pull_result}\n```" + pip_msg + "\n🚀 Újraindítás...", 
                ephemeral=True
            )
            
            log.info("Self-update successful. Restarting...")
            # Give Discord a moment to send the message before we kill the process
            await asyncio.sleep(1)
            os.execv(sys.executable, ['python'] + sys.argv)
        except Exception as e:
            log.error(f"Manager self-update failed: {e}")
            await interaction.followup.send(f"❌ Hiba a frissítés során: {str(e)}", ephemeral=True)

async def setup(bot):
    await bot.add_cog(ManagementCog(bot))
