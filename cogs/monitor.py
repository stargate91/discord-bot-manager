import discord
from discord import app_commands
from discord.ext import commands, tasks
import os
import json
import psutil
import datetime
import asyncio
import platform
import shutil
from core.logger import log
from core.utils import is_admin_context, is_monitor_context

class MonitoringCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.status_message_id = self.bot.state.get("status_message_id")
        self.status_channel_id = self.bot.state.get("status_channel_id")
        
        # Load settings from config
        bot_settings = self.bot.config.get("bot_settings", {})
        self.refresh_interval = bot_settings.get("status_refresh_seconds", 60)
        self.recreate_interval = bot_settings.get("status_recreate_minutes", 58)

    async def cog_load(self):
        """Called when the cog is loaded."""
        log.info("[Status] MonitoringCog loaded. Starting tasks...")
        self.update_status_task.change_interval(seconds=self.refresh_interval)
        self.recreate_status_task.change_interval(minutes=self.recreate_interval)
        
        # We don't start the tasks here because the bot might not be ready.
        # We instead wait for on_ready in a separate listener or just use the tasks' before_loop.

    @commands.Cog.listener()
    async def on_ready(self):
        """Called when the bot is ready."""
        log.info("[Status] Bot ready. Initializing persistent status panel...")
        # Small delay to ensure all guilds/channels are cached
        await asyncio.sleep(2)
        
        await self.cleanup_and_recreate_panel()
        
        if not self.update_status_task.is_running():
            self.update_status_task.start()
        if not self.recreate_status_task.is_running():
            self.recreate_status_task.start()

    def cog_unload(self):
        """Stop tasks when the cog is unloaded."""
        self.update_status_task.cancel()
        self.recreate_status_task.cancel()

    async def cleanup_and_recreate_panel(self):
        """Deletes the old status panel (if any) and creates a new one."""
        log.info("[Status] Cleaning up old status panel and creating a new one...")
        
        # 1. Try to delete the old message
        if self.status_channel_id and self.status_message_id:
            try:
                channel = self.bot.get_channel(int(self.status_channel_id))
                if not channel:
                    channel = await self.bot.fetch_channel(int(self.status_channel_id))
                
                if channel:
                    try:
                        old_msg = await channel.fetch_message(int(self.status_message_id))
                        await old_msg.delete()
                        log.info(f"[Status] Deleted old status message: {self.status_message_id}")
                    except discord.NotFound:
                        log.info("[Status] Old status message not found (already deleted).")
            except Exception as e:
                log.warning(f"[Status] Failed to cleanup old status message: {e}")

        # 2. Create the new panel
        admin_channel_id = self.bot.config.get("settings", {}).get("admin_channel_id")
        if not admin_channel_id:
            log.error("[Status] No admin_channel_id found in config. Cannot create status panel.")
            return

        try:
            channel = self.bot.get_channel(int(admin_channel_id))
            if not channel:
                channel = await self.bot.fetch_channel(int(admin_channel_id))
            
            if channel:
                manager_stats, bots_stats = self.get_status_data()
                from core.views import ModernStatusView
                layout = ModernStatusView(self.bot, self.bot.i18n, manager_stats, bots_stats)
                
                # IMPORTANT: Use a placeholder or initial content
                new_msg = await channel.send(view=layout)
                
                # 3. Save the new IDs
                self.status_message_id = str(new_msg.id)
                self.status_channel_id = str(channel.id)
                self.bot.save_state("status_message_id", self.status_message_id)
                self.bot.save_state("status_channel_id", self.status_channel_id)
                log.info(f"[Status] New status panel created: {self.status_message_id} in {self.status_channel_id}")
        except Exception as e:
            log.error(f"[Status] Failed to create new status panel: {e}", exc_info=True)

    def get_status_data(self):
        """Gathers statistics for the Manager and all Managed Bots."""
        # 1. Manager Statistics
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
        
        # 1.5 System-wide Statistics
        try:
            # OS details
            if os.name == 'posix':
                # Try to get a nicer name like "Debian 12" instead of generic Linux
                try:
                    with open("/etc/os-release") as f:
                        lines = f.readlines()
                        os_info = {}
                        for line in lines:
                            if "=" in line:
                                k, v = line.rstrip().split("=", 1)
                                os_info[k] = v.strip('"')
                        os_name = os_info.get("PRETTY_NAME", platform.system())
                except:
                    os_name = f"{platform.system()} {platform.release()}"
            else:
                os_name = f"{platform.system()} {platform.release()}"

            # Resources
            # Note: cpu_percent(interval=None) might return 0 on the first call, 
            # but since this runs in a loop, it should stabilize.
            sys_cpu_usage = psutil.cpu_percent(interval=None)
            sys_cpu_free = max(0, 100 - sys_cpu_usage)
            
            vm = psutil.virtual_memory()
            sys_ram_free = vm.available / (1024 * 1024)
            
            # Disk Usage for the root partition
            du = shutil.disk_usage("/")
            sys_disk_free = du.free / (1024 * 1024 * 1024)
        except Exception as e:
            log.warning(f"Failed to gather system stats: {e}")
            os_name = "Unknown"
            sys_cpu_free = 0
            sys_ram_free = 0
            sys_disk_free = 0

        manager_stats = {
            "cpu": self_cpu,
            "ram": self_ram_mb,
            "uptime": uptime_str,
            "branch": self.bot.config.get("bot_settings", {}).get("git_branch", "origin/main"),
            "os": os_name,
            "sys_cpu_free": sys_cpu_free,
            "sys_ram_free": sys_ram_free,
            "sys_disk_free": sys_disk_free
        }
        
        # 2. Managed Bot Statistics
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
                b_uptime_sec = stats["uptime_sec"]
                if b_uptime_sec > 86400:
                    b_uptime_str = self.bot.i18n.get("uptime_days", "{d} days ago", d=int(b_uptime_sec / 86400))
                elif b_uptime_sec > 3600:
                    b_uptime_str = self.bot.i18n.get("uptime_hours", "{h} hours ago", h=int(b_uptime_sec / 3600))
                else:
                    b_uptime_str = self.bot.i18n.get("uptime_minutes", "{m} minutes ago", m=int(b_uptime_sec / 60))
                
                bot_config = self.bot.config.get("bots", {}).get(bot_id, {})
                if bot_config.get("systemd_service"):
                    status_text = self.bot.i18n.get("status_running_systemd", "Running (Systemd)")
                else:
                    status_text = self.bot.i18n.get("status_running", "Running")

                bot_entry.update({
                    "status": status_text,
                    "uptime": b_uptime_str,
                    "pid": stats["pid"],
                    "cpu": stats['cpu'],
                    "ram": stats['ram_mb']
                })
            else:
                if bot_id in self.bot.process_manager.manual_stop:
                    bot_entry["status"] = self.bot.i18n.get("status_stopped", "Stopped")
                else:
                    bot_config = self.bot.config.get("bots", {}).get(bot_id, {})
                    systemd_service = bot_config.get("systemd_service")
                    if systemd_service and os.name == 'posix':
                        state = self.bot.process_manager.get_systemd_state(systemd_service)
                        if state == "failed":
                            bot_entry["status"] = self.bot.i18n.get("status_failed", "Failed")
                        else:
                            bot_entry["status"] = self.bot.i18n.get("status_stopped", "Stopped")
                    else:
                        if self.bot.process_manager.managed_processes.get(bot_id):
                            bot_entry["status"] = self.bot.i18n.get("status_uncertain", "Status Uncertain (Access Denied)")
                        else:
                            bot_entry["status"] = self.bot.i18n.get("status_stopped", "Stopped")
            
            bots_stats[bot_id] = bot_entry
            
        return manager_stats, bots_stats

    @tasks.loop(seconds=60)
    async def update_status_task(self):
        """Update the existing status panel message."""
        if not self.status_channel_id or not self.status_message_id:
            return

        try:
            channel = self.bot.get_channel(int(self.status_channel_id))
            if not channel:
                channel = await self.bot.fetch_channel(int(self.status_channel_id))
            
            if channel:
                msg = await channel.fetch_message(int(self.status_message_id))
                if msg:
                    manager_stats, bots_stats = self.get_status_data()
                    from core.views import ModernStatusView
                    layout = ModernStatusView(self.bot, self.bot.i18n, manager_stats, bots_stats)
                    # We edit the message with the new view. 
                    # Note: We don't send content, the layout container handles everything.
                    await msg.edit(view=layout)
        except discord.NotFound:
            log.warning("[Status] Persistent status message lost. Recreating...")
            await self.cleanup_and_recreate_panel()
        except Exception as e:
            log.error(f"[Status] Error updating status panel: {e}")

    @tasks.loop(minutes=58)
    async def recreate_status_task(self):
        """Periodically recreate the status panel to avoid Discord limitations."""
        log.info("[Status] Periodic recreation of status panel triggered.")
        await self.cleanup_and_recreate_panel()

    @app_commands.command(name="status", description="Manually refresh or recreate the status panel.")
    @is_monitor_context()
    async def status(self, interaction: discord.Interaction):
        """Force a recreation of the status panel."""
        log.info(f"User {interaction.user} requested manual /status recreation.")
        await interaction.response.defer(ephemeral=True)
        
        await self.cleanup_and_recreate_panel()
        await interaction.followup.send("Status panel recreated.", ephemeral=True)

async def setup(bot):
    await bot.add_cog(MonitoringCog(bot))
