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
        # We start by logging that someone asked for status
        log.info(f"User {interaction.user} (ID: {interaction.user.id}) requested /status")
        
        # We 'defer' the response so the interaction doesn't time out while we gather data
        await interaction.response.defer(ephemeral=False)
        
        if not self.bot.bots:
            await interaction.followup.send(self.bot.i18n.get("error_no_bots_configured", "No bots configured."), ephemeral=False)
            return

        # 1. We gather statistics for the Manager itself
        current_proc = psutil.Process()
        with current_proc.oneshot():
            self_cpu = current_proc.cpu_percent()
            self_ram_mb = current_proc.memory_info().rss / 1024 / 1024
            uptime_sec = datetime.datetime.now().timestamp() - current_proc.create_time()
            
            # Formatting uptime into a human-readable string
            if uptime_sec > 86400:
                uptime_str = self.bot.i18n.get("uptime_days", "{d} days ago", d=int(uptime_sec / 86400))
            elif uptime_sec > 3600:
                uptime_str = self.bot.i18n.get("uptime_hours", "{h} hours ago", h=int(uptime_sec / 3600))
            else:
                uptime_str = self.bot.i18n.get("uptime_minutes", "{m} minutes ago", m=int(uptime_sec / 60))
        
        manager_stats = {
            "cpu": self_cpu,
            "ram": self_ram_mb,
            "uptime": uptime_str,
            "branch": self.bot.config.get("bot_settings", {}).get("git_branch", "origin/main")
        }
        
        # 2. We gather statistics for every Managed Bot
        bots_stats = {}
        for bot_id, bot in self.bot.bots.items():
            stats = self.bot.process_manager.get_stats(bot_id)
            
            bot_entry = {
                "name": bot.name,
                "path": bot.path,
                "is_running": False
            }

            if stats:
                bot_entry["is_running"] = True
                # Uptime calculation for the bot
                b_uptime_sec = stats["uptime_sec"]
                if b_uptime_sec > 86400:
                    b_uptime_str = self.bot.i18n.get("uptime_days", "{d} days ago", d=int(b_uptime_sec / 86400))
                elif b_uptime_sec > 3600:
                    b_uptime_str = self.bot.i18n.get("uptime_hours", "{h} hours ago", h=int(b_uptime_sec / 3600))
                else:
                    b_uptime_str = self.bot.i18n.get("uptime_minutes", "{m} minutes ago", m=int(b_uptime_sec / 60))
                
                bot_entry.update({
                    "status": self.bot.i18n.get("status_running", "Running"),
                    "uptime": b_uptime_str,
                    "pid": stats["pid"],
                    "cpu": stats['cpu'],
                    "ram": stats['ram_mb']
                })
            else:
                # If the bot is not running, we check if it was stopped on purpose
                if bot_id in self.bot.process_manager.manual_stop:
                    bot_entry["status"] = self.bot.i18n.get("status_stopped", "Stopped")
                else:
                    # If it's not running but we didn't stop it, something might be wrong
                    if self.bot.process_manager.managed_processes.get(bot_id):
                        bot_entry["status"] = self.bot.i18n.get("status_uncertain", "Status Uncertain (Access Denied)")
                    else:
                        bot_entry["status"] = self.bot.i18n.get("status_stopped", "Stopped")
            
            bots_stats[bot_id] = bot_entry
        
        # 3. We send everything to the ModernStatusView
        try:
            from core.views import ModernStatusView
            layout = ModernStatusView(self.bot, self.bot.i18n, manager_stats, bots_stats)
            await interaction.followup.send(view=layout)
        except Exception as e:
            log.error(f"Error in /status modern layout: {e}", exc_info=True)
            # Fallback to simple message if the modern layout fails
            msg = self.bot.i18n.get("status_error", "Status Error: {error}", error=str(e))
            await interaction.followup.send(msg, ephemeral=False)

async def setup(bot):
    await bot.add_cog(MonitoringCog(bot))
