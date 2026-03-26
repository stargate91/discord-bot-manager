import discord
from discord import app_commands
from discord.ext import commands
import os
import json
import psutil
import datetime
from core.logger import log
from core.utils import is_admin_context

class MonitoringCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="status", description="Shows the status and resource usage of managed bots.")
    @is_admin_context()
    async def status(self, interaction: discord.Interaction):
        log.info(f"User {interaction.user} (ID: {interaction.user.id}) requested /status")
        
        # Defer to prevent timeout
        await interaction.response.defer(ephemeral=True)
        
        if not self.bot.bots:
            await interaction.followup.send(self.bot.i18n.get("error_no_bots_configured", "No bots configured."), ephemeral=True)
            return

        # Manager own stats
        current_proc = psutil.Process()
        with current_proc.oneshot():
            self_cpu = current_proc.cpu_percent()
            self_ram_mb = current_proc.memory_info().rss / 1024 / 1024
            uptime_sec = datetime.datetime.now().timestamp() - current_proc.create_time()
            
            if uptime_sec > 86400:
                uptime_str = self.bot.i18n.get("uptime_days", "{d} days ago", d=int(uptime_sec / 86400))
            elif uptime_sec > 3600:
                uptime_str = self.bot.i18n.get("uptime_hours", "{h} hours ago", h=int(uptime_sec / 3600))
            else:
                uptime_str = self.bot.i18n.get("uptime_minutes", "{m} minutes ago", m=int(uptime_sec / 60))
        
        msg = self.bot.i18n.get("manager_status_header", "### Manager Status") + "\n"
        msg += self.bot.i18n.get("manager_status_line", "- **{name}**: {status} ({uptime}) | CPU: `{cpu}%` | RAM: `{ram} MB`",
            name=self.bot.manager_name,
            status=self.bot.i18n.get("status_running", "Running"),
            uptime=uptime_str,
            cpu=self_cpu,
            ram=f"{self_ram_mb:.1f}"
        ) + "\n\n"
        
        # Managed Bots
        msg += self.bot.i18n.get("bots_status_header", "### Managed Bots") + "\n"
        for bot_id, bot in self.bot.bots.items():
            stats = self.bot.process_manager.get_stats(bot_id)
            
            if stats:
                # Uptime calculation
                b_uptime_sec = stats["uptime_sec"]
                if b_uptime_sec > 86400:
                    b_uptime_str = self.bot.i18n.get("uptime_days", "{d} days ago", d=int(b_uptime_sec / 86400))
                elif b_uptime_sec > 3600:
                    b_uptime_str = self.bot.i18n.get("uptime_hours", "{h} hours ago", h=int(b_uptime_sec / 3600))
                else:
                    b_uptime_str = self.bot.i18n.get("uptime_minutes", "{m} minutes ago", m=int(b_uptime_sec / 60))
                
                disk_mb = stats.get("disk_mb")
                disk_text = f" | HDD: `{disk_mb:.1f} MB`" if disk_mb is not None else ""
                
                running_template = self.bot.i18n.get("status_running", "Running")
                status_text = self.bot.i18n.get("bot_status_running_detail", "{status} ({uptime}) | PID: {pid} | CPU: `{cpu}%` | RAM: `{ram} MB`{disk}",
                    status=running_template,
                    uptime=b_uptime_str,
                    pid=stats["pid"],
                    cpu=f"{stats['cpu']}",
                    ram=f"{stats['ram_mb']:.1f}",
                    disk=disk_text
                )
            else:
                # Check if it's intentionally stopped
                if bot_id in self.bot.process_manager.manual_stop:
                    status_text = self.bot.i18n.get("status_stopped", "Stopped")
                else:
                    # If tracked but not running/accessible
                    if self.bot.process_manager.managed_processes.get(bot_id):
                        status_text = self.bot.i18n.get("status_uncertain", "Status Uncertain (Access Denied)")
                    else:
                        status_text = self.bot.i18n.get("status_stopped", "Stopped")
                
            msg += self.bot.i18n.get("bot_status_line", "- **{name}** ({id}):\n  ╰ {status_text}\n  ╰ `Path: {path}`",
                name=bot.name,
                id=bot_id,
                status_text=status_text,
                path=bot.path
            ) + "\n"
        
        await interaction.followup.send(msg)

async def setup(bot):
    await bot.add_cog(MonitoringCog(bot))
