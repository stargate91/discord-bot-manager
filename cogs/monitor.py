import discord
from discord import app_commands
from discord.ext import commands
import os
import json
from core.logger import log

from core.utils import is_admin_context

class MonitoringCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="status", description="Megmutatja a kezelt botok állapotát és erőforrás-használatát.")
    @is_admin_context()
    async def status(self, interaction: discord.Interaction):
        log.info(f"User {interaction.user} (ID: {interaction.user_id}) requested /status")
        # We assume the bot restricted it to the right guild/channel already or we add the check
        # But for now we just implement the logic
        config = self.bot.load_config()
        if not config:
            await interaction.response.send_message("Nincsenek konfigurált botok.", ephemeral=True)
            return

        import psutil
        import datetime
        
        # Manager saját statisztikái
        current_proc = psutil.Process()
        with current_proc.oneshot():
            self_cpu = current_proc.cpu_percent()
            self_ram_mb = current_proc.memory_info().rss / 1024 / 1024
            self_uptime_sec = datetime.datetime.now().timestamp() - current_proc.create_time()
            if self_uptime_sec > 86400:
                self_uptime_str = f"{int(self_uptime_sec / 86400)} napja"
            elif self_uptime_sec > 3600:
                self_uptime_str = f"{int(self_uptime_sec / 3600)} órája"
            else:
                self_uptime_str = f"{int(self_uptime_sec / 60)} perce"
        
        msg = "### 🛡️ Manager Állapot\n"
        msg += f"- **FixItFixa**: 🟢 Fut ({self_uptime_str}) | 💻 CPU: `{self_cpu}%` | 🧠 RAM: `{self_ram_mb:.1f} MB`\n\n"
        msg += "### 🤖 Kezelt Botok\n"
        for bot_id, info in config.items():
            proc = self.bot.managed_processes.get(bot_id)
            
            if proc and proc.is_running():
                try:
                    # Get metrics
                    cpu = proc.cpu_percent(interval=None)
                    ram_mb = proc.memory_info().rss / 1024 / 1024
                    
                    # Uptime calculation
                    create_time = proc.create_time()
                    uptime_sec = datetime.datetime.now().timestamp() - create_time
                    if uptime_sec > 86400:
                        uptime_str = f"{int(uptime_sec / 86400)} napja"
                    elif uptime_sec > 3600:
                        uptime_str = f"{int(uptime_sec / 3600)} órája"
                    else:
                        uptime_str = f"{int(uptime_sec / 60)} perce"
                    
                    status_text = f"🟢 Fut ({uptime_str}) | PID: {proc.pid} | 💻 CPU: `{cpu}%` | 🧠 RAM: `{ram_mb:.1f} MB`"
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    status_text = "🟡 Állapot bizonytalan (Access Denied)"
            else:
                status_text = "🔴 Nem fut"
                
            msg += f"- **{info['name']}** ({bot_id}):\n  ╰ {status_text}\n  ╰ `Path: {info['path']}`\n"
        
        await interaction.response.send_message(msg, ephemeral=True)

async def setup(bot):
    await bot.add_cog(MonitoringCog(bot))
