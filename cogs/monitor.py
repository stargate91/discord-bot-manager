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
import subprocess
from core.logger import log
from core.utils import is_admin_context, is_monitor_context, get_feedback, format_desc
from core.icons import Icons

class MonitoringCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.status_message_id = self.bot.state.get("status_message_id")
        self.status_channel_id = self.bot.state.get("status_channel_id")
        self._recreate_lock = asyncio.Lock()
        
        # Load settings from config
        bot_settings = self.bot.config.get("bot_settings", {})
        self.refresh_interval = bot_settings.get("status_refresh_seconds", 60)
        self.recreate_interval = bot_settings.get("status_recreate_minutes", 58)
        
        # Network stats tracking
        self.last_net_io = psutil.net_io_counters()
        self.last_net_time = datetime.datetime.now()
        
        # Git Status Tracking (bot_id -> is_behind)
        self.git_behind_status = {}
        
        # Initial format (placeholders to IDs)
        for cmd in self.get_app_commands():
             if not hasattr(cmd, "_raw_desc"):
                 cmd._raw_desc = cmd.description
             cmd.description = format_desc(self.bot, cmd._raw_desc)

    async def cog_load(self):
        """Called when the cog is loaded."""
        log.info("[Status] MonitoringCog loaded. Starting tasks...")
        self.update_status_task.change_interval(seconds=self.refresh_interval)
        self.recreate_status_task.change_interval(minutes=self.recreate_interval)

    @commands.Cog.listener()
    async def on_ready(self):
        """Called when the bot is ready."""
        log.info(f"[Status] Cog on_ready starting for user: {self.bot.user}")
        # Wait for manager to finish its early setup (icons, etc)
        await asyncio.sleep(3)
        
        try:
            # 1. Recreate the panel immediately (with existing/cached data)
            log.info("[Status] Initializing persistent status panel...")
            await self.cleanup_and_recreate_panel()
            
            # 2. Start checking for Git updates in the background
            log.info("[Status] Starting git fetch background task...")
            self.bot.loop.create_task(self.git_fetch_task())
            
            log.info("[Status] Starting task loops...")
            if not self.update_status_task.is_running():
                self.update_status_task.start()
            if not self.recreate_status_task.is_running():
                self.recreate_status_task.start()
            if not self.git_fetch_task.is_running():
                self.git_fetch_task.start()
            log.info("[Status] cog on_ready finished successfully.")
        except Exception as e:
            log.error(f"[Status] Error during cog on_ready: {e}")
            import traceback
            log.error(traceback.format_exc())


        
        if not self.update_status_task.is_running():
            self.update_status_task.start()
        if not self.recreate_status_task.is_running():
            self.recreate_status_task.start()
        if not self.git_fetch_task.is_running():
            self.git_fetch_task.start()

    def cog_unload(self):
        """Stop tasks when the cog is unloaded."""
        self.update_status_task.cancel()
        self.recreate_status_task.cancel()
        self.git_fetch_task.cancel()

    @tasks.loop(minutes=10)
    async def git_fetch_task(self):
        """Periodically runs git fetch for all bots to check for updates."""
        log.info("[Git] Checking for updates...")
        
        # Check Manager itself
        manager_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        branch = self.bot.config.get("bot_settings", {}).get("git_branch", "origin/main")
        self.git_behind_status["manager"] = await self.check_if_behind(manager_path, branch)
        
        # Check Managed Bots
        for bot_id, bot_config in self.bot.bots.items():
            # Use same branch for bots or customize if needed
            self.git_behind_status[bot_id] = await self.check_if_behind(bot_config.path, branch)

    async def check_if_behind(self, path, branch="origin/main"):
        """Checks if a git repo is behind its remote."""
        try:
            # 1. Fetch from remote
            fetch_res = await asyncio.to_thread(subprocess.run, ["git", "fetch", "--all"], cwd=path, check=False, capture_output=True, text=True)
            if fetch_res.returncode != 0:
                log.debug(f"[Git] Fetch failed for {path}: {fetch_res.stderr.strip()}")
                return False

            # 2. Count commits behind
            # git rev-list --count HEAD..origin/main
            result = await asyncio.to_thread(
                subprocess.run, 
                ["git", "rev-list", "--count", f"HEAD..{branch}"], 
                cwd=path, capture_output=True, text=True, check=False
            )
            
            if result.returncode == 0:
                count = int(result.stdout.strip())
                if count > 0:
                    log.info(f"[Git] Update detected for {path}: {count} commit(s) behind {branch}")
                    return True
            else:
                log.debug(f"[Git] rev-list failed for {path}: {result.stderr.strip()}")
        except Exception as e:
            log.error(f"[Git] Error checking updates for {path}: {e}")
        return False

    async def cleanup_and_recreate_panel(self, triggered_by_id=None):
        """Deletes the old status panel (if any) and creates a new one.
        
        :param triggered_by_id: Optional. If provided, recreation only proceeds if current message ID matches this.
        """
        async with self._recreate_lock:
            # 0. Concurrency Check: If we are wait/locked, check if someone else already DID the job
            if triggered_by_id and self.status_message_id != triggered_by_id:
                log.info(f"[Status] Cleanup skipped: message already recreated by another task (current: {self.status_message_id}, triggered by: {triggered_by_id})")
                return

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
            admin_channel_id = self.bot.admin_channel_id
            if not admin_channel_id:
                log.error("[Status] No admin_channel_id found. Cannot create status panel.")
                return

            try:
                channel = self.bot.get_channel(int(admin_channel_id))
                if not channel:
                    channel = await self.bot.fetch_channel(int(admin_channel_id))
                
                if channel:
                    log.info(f"[Status] Creating new panel in #{channel.name}...")
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
            
            # Use the actual start time from the bot instance to ensure it resets on restart
            start_time = getattr(self.bot, 'start_time', datetime.datetime.now())
            delta = datetime.datetime.now() - start_time
            uptime_sec = delta.total_seconds()
            
            if uptime_sec > 86400:
                uptime_str = get_feedback(self.bot.i18n, "uptime_days", d=int(uptime_sec / 86400))
            elif uptime_sec > 3600:
                uptime_str = get_feedback(self.bot.i18n, "uptime_hours", h=int(uptime_sec / 3600))
            else:
                uptime_str = get_feedback(self.bot.i18n, "uptime_minutes", m=int(uptime_sec / 60))
        
        # 1.5 System-wide Statistics
        try:
            # OS details
            if os.name == 'posix':
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
            sys_cpu_usage = psutil.cpu_percent(interval=None)
            sys_cpu_free = max(0, 100 - sys_cpu_usage)
            
            vm = psutil.virtual_memory()
            sys_ram_free = vm.available / (1024 * 1024)
            
            # Swap
            swap = psutil.swap_memory()
            sys_swap_percent = swap.percent
            
            # Host Uptime
            boot_time = psutil.boot_time()
            host_uptime_sec = datetime.datetime.now().timestamp() - boot_time
            if host_uptime_sec > 86400:
                host_uptime_str = get_feedback(self.bot.i18n, "uptime_days", d=int(host_uptime_sec / 86400))
            else:
                host_uptime_str = get_feedback(self.bot.i18n, "uptime_hours", h=int(host_uptime_sec / 3600))

            # Disk Usage
            du = shutil.disk_usage("/")
            sys_disk_free = du.free / (1024 * 1024 * 1024)
            
            # Network Speed
            now = datetime.datetime.now()
            net_now = psutil.net_io_counters()
            dt = (now - self.last_net_time).total_seconds()
            if dt > 0:
                down_speed = (net_now.bytes_recv - self.last_net_io.bytes_recv) / dt
                up_speed = (net_now.bytes_sent - self.last_net_io.bytes_sent) / dt
            else:
                down_speed, up_speed = 0, 0
                
            self.last_net_io = net_now
            self.last_net_time = now
            
            def format_speed(bytes_per_sec):
                if bytes_per_sec > 1024*1024:
                    return f"{bytes_per_sec / (1024*1024):.1f} MB/s"
                return f"{bytes_per_sec / 1024:.1f} KB/s"
            
            up_icon = str(Icons.ACTIVITY_UP) if Icons.ACTIVITY_UP else "↑"
            down_icon = str(Icons.ACTIVITY_DOWN) if Icons.ACTIVITY_DOWN else "↓"
            net_str = f"{down_icon} {format_speed(down_speed)} | {up_icon} {format_speed(up_speed)}"

        except Exception as e:
            log.warning(f"Failed to gather system stats: {e}")
            os_name = "Unknown"
            sys_cpu_free = 0
            sys_ram_free = 0
            sys_disk_free = 0
            sys_swap_percent = 0
            host_uptime_str = "Unknown"
            net_str = "Error"

        manager_stats = {
            "cpu": self_cpu,
            "ram": self_ram_mb,
            "uptime": uptime_str,
            "branch": self.bot.config.get("bot_settings", {}).get("git_branch", "origin/main"),
            "os": os_name,
            "sys_cpu_free": sys_cpu_free,
            "sys_ram_free": sys_ram_free,
            "sys_disk_free": sys_disk_free,
            "swap": sys_swap_percent,
            "host_uptime": host_uptime_str,
            "net": net_str,
            "has_update": self.git_behind_status.get("manager", False)
        }
        
        # 2. Managed Bot Statistics
        bots_stats = {}
        for bot_id, bot in self.bot.bots.items():
            stats = self.bot.process_manager.get_stats(bot_id)
            
            # Log file size
            log_size_str = "N/A"
            try:
                log_file_path = os.path.join(bot.path, bot.log)
                if os.path.exists(log_file_path):
                    size_bytes = os.path.getsize(log_file_path)
                    if size_bytes > 1024*1024:
                        log_size_str = f"{size_bytes / (1024*1024):.1f} MB"
                    else:
                        log_size_str = f"{size_bytes / 1024:.1f} KB"
            except:
                pass

            bot_entry = {
                "name": bot.name,
                "path": bot.path,
                "is_running": False,
                "log_size": log_size_str,
                "has_update": self.git_behind_status.get(bot_id, False)
            }

            if stats:
                bot_entry["is_running"] = True
                b_uptime_sec = stats["uptime_sec"]
                if b_uptime_sec > 86400:
                    b_uptime_str = get_feedback(self.bot.i18n, "uptime_days", d=int(b_uptime_sec / 86400))
                elif b_uptime_sec > 3600:
                    b_uptime_str = get_feedback(self.bot.i18n, "uptime_hours", h=int(b_uptime_sec / 3600))
                else:
                    b_uptime_str = get_feedback(self.bot.i18n, "uptime_minutes", m=int(b_uptime_sec / 60))
                
                # We try to get a more accurate 'Running' label from our process manager
                status_text = get_feedback(self.bot.i18n, "status_running")
                b_proc = self.bot.process_manager.managed_processes.get(bot_id)
                if b_proc and not b_proc.is_running():
                    status_text = get_feedback(self.bot.i18n, "status_uncertain")

                bot_entry.update({
                    "status": status_text,
                    "uptime": b_uptime_str,
                    "pid": stats["pid"],
                    "cpu": stats['cpu'],
                    "ram": stats['ram_mb']
                })
            else:
                if bot_id in self.bot.process_manager.manual_stop:
                    bot_entry["status"] = get_feedback(self.bot.i18n, "status_stopped")
                else:
                    bot_config = self.bot.config.get("bots", {}).get(bot_id, {})
                    systemd_service = bot_config.get("systemd_service")
                    if systemd_service and os.name == 'posix':
                        state = self.bot.process_manager.get_systemd_state(systemd_service)
                        if state == "failed":
                            bot_entry["status"] = get_feedback(self.bot.i18n, "status_failed")
                        else:
                            bot_entry["status"] = get_feedback(self.bot.i18n, "status_stopped")
                    else:
                        if self.bot.process_manager.managed_processes.get(bot_id):
                            bot_entry["status"] = get_feedback(self.bot.i18n, "status_uncertain")
                        else:
                            bot_entry["status"] = get_feedback(self.bot.i18n, "status_stopped")
            
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
            # We pass the lost message ID to ensure we don't recreate twice
            await self.cleanup_and_recreate_panel(triggered_by_id=self.status_message_id)
        except Exception as e:
            log.error(f"[Status] Error updating status panel: {e}")

    @tasks.loop(minutes=58)
    async def recreate_status_task(self):
        """Periodically recreate the status panel to avoid Discord limitations."""
        log.info("[Status] Periodic recreation of status panel triggered.")
        await self.cleanup_and_recreate_panel()

    def refresh_descriptions(self, guild):
        """Re-formats all slash command descriptions using actual names from the guild."""
        for cmd in self.get_app_commands():
             if hasattr(cmd, "_raw_desc"):
                 cmd.description = format_desc(self.bot, cmd._raw_desc, guild)

    @app_commands.command(name="info", description="General information about FixItFixa. (Public option for Admins only)")
    @app_commands.describe(public="Set to True to show the info card to everyone (Admin only).")
    async def info(self, interaction: discord.Interaction, public: bool = False):
        """Displays information about the Bot Manager and its mission."""
        from core.views import ModernInfoView
        
        # Visibility Control: Default ephemeral, optional public for admins/mechanics
        if public:
            from core.utils import AccessLevel, get_user_level
            level = get_user_level(interaction.user, self.bot)
            if level < AccessLevel.MECHANIC:
                public = False # Force ephemeral for non-admins
        
        view = ModernInfoView(self.bot, self.bot.i18n, interaction.guild)
        # We send the interaction using the view's layout
        await interaction.response.send_message(view=view, ephemeral=not public)

    @app_commands.command(name="status", description="Bot status snapshot. Anyone can request a private report; admins refresh the Workshop.")
    async def status(self, interaction: discord.Interaction):
        """Force a recreation of the status panel or send an ephemeral snapshot."""
        log.info(f"User {interaction.user} requested /status snapshot.")
        
        # Check Permissions and Channel
        from core.utils import AccessLevel, get_user_level
        level = get_user_level(interaction.user, self.bot)
        is_admin_channel = str(interaction.channel_id) == str(self.bot.admin_channel_id)
        is_mechanic = level >= AccessLevel.MECHANIC
        
        # We always want fresh Git data for the snapshot/refresh
        # If in admin channel and user is mechanic, refresh the persistent panel
        # Otherwise, send an ephemeral snapshot
        do_refresh = is_admin_channel and is_mechanic
        
        await interaction.response.defer(ephemeral=True)
        await self.git_fetch_task()
        
        if do_refresh:
            # Persistent Refresh (Workshop)
            await self.cleanup_and_recreate_panel()
            await interaction.followup.send(get_feedback(self.bot.i18n, "status_refreshed"), ephemeral=True)
        else:
            # Ephemeral Snapshot (Lounge / Elsewhere)
            from core.views import ModernStatusView
            manager_stats, bots_stats = self.get_status_data()
            layout = ModernStatusView(self.bot, self.bot.i18n, manager_stats, bots_stats)
            await interaction.followup.send(view=layout, ephemeral=True)

async def setup(bot):
    await bot.add_cog(MonitoringCog(bot))
