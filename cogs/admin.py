import discord
from discord import app_commands
from discord.ext import commands
import os
import json
import asyncio
import subprocess
import sys
from collections import deque
from core.utils import is_admin_context, is_admin_prefix_context, is_monitor_context, is_monitor_prefix_context, get_feedback
from core.logger import log

async def bot_id_autocomplete(
    interaction: discord.Interaction,
    current: str,
) -> list[app_commands.Choice[str]]:
    bot_manager = interaction.client # The main bot instance (BotManager)
    
    choices = []
    # Identify context: Logs usually want individual bots, updates might want groups
    # We check the command name or even just the provided options to be safe
    cmd_name = interaction.command.name if interaction.command else ""
    is_logs_command = "logs" in cmd_name.lower()
    
    # Access the BotConfig objects directly from bot_manager.bots
    bots_data = bot_manager.bots

    if is_logs_command:
        # For logs, return individual bots
        for bot_id, bot_config in bots_data.items():
            name = bot_config.name
            if current.lower() in name.lower():
                choices.append(app_commands.Choice(name=name, value=bot_id))
    else:
        # For update/restart/rollback, group bots by path
        path_groups = {}
        for bot_id, bot_config in bots_data.items():
            path = bot_config.path
            if path not in path_groups:
                path_groups[path] = []
            path_groups[path].append((bot_id, bot_config.name))
        
        for path, bots_in_group in path_groups.items():
            if len(bots_in_group) > 1:
                combined_name = " + ".join([b[1] for b in bots_in_group])
                # Use the ID of the first bot in the group as the representative value
                representative_id = bots_in_group[0][0] 
                if current.lower() in combined_name.lower():
                    choices.append(app_commands.Choice(name=combined_name, value=representative_id))
            else:
                bot_id, name = bots_in_group[0]
                if current.lower() in name.lower():
                    choices.append(app_commands.Choice(name=name, value=bot_id))
    
    return choices[:25]

class ManagementCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="ping")
    async def ping_prefix(self, ctx: commands.Context):
        """[Bot Dev] Simple connectivity check."""
        await ctx.send(f"🏓 Pong! (Latency: {round(self.bot.latency * 1000)}ms)")

    @app_commands.command(name="update", description="[Bot Dev] Update and restart a bot by ID.")
    @app_commands.describe(bot_id="The ID of the bot to update")
    @is_admin_context()
    @app_commands.autocomplete(bot_id=bot_id_autocomplete)
    async def update(self, interaction: discord.Interaction, bot_id: str):
        log.info(f"User {interaction.user} (ID: {interaction.user.id}) requested /update for bot: {bot_id}")
        await interaction.response.defer(ephemeral=False)
        result_msg, details = await self.bot.management_service.run_update(bot_id)
        
        if details:
            from core.views import UpdateResultEmbed
            title = get_feedback(self.bot.i18n, "bot_updated_title")
            embed = UpdateResultEmbed(self.bot.i18n, title, details, ui_settings=self.bot.ui_settings)
            await interaction.followup.send(embed=embed, ephemeral=False)
        else:
            if len(result_msg) > 1900:
                result_msg = result_msg[:1000] + "\n\n... [TRUNCATED] ...\n\n" + result_msg[-800:]
            await interaction.followup.send(result_msg, ephemeral=False)

    @app_commands.command(name="restart", description="[Bot Dev] Restart a bot without update.")
    @app_commands.describe(bot_id="The ID of the bot to restart")
    @is_admin_context()
    @app_commands.autocomplete(bot_id=bot_id_autocomplete)
    async def restart(self, interaction: discord.Interaction, bot_id: str):
        log.info(f"User {interaction.user} (ID: {interaction.user.id}) requested /restart for bot: {bot_id}")
        await interaction.response.defer(ephemeral=False)
        
        result = await self.bot.management_service.run_restart(bot_id)
        await interaction.followup.send(result, ephemeral=False)

    @app_commands.command(name="rollback", description="[Bot Dev] Rollback bot to previous Git state (HEAD@{1}).")
    @app_commands.describe(bot_id="The ID of the bot to rollback")
    @is_admin_context()
    @app_commands.autocomplete(bot_id=bot_id_autocomplete)
    async def rollback(self, interaction: discord.Interaction, bot_id: str):
        log.info(f"User {interaction.user} (ID: {interaction.user.id}) requested /rollback for bot: {bot_id}")
        await interaction.response.defer(ephemeral=False)
        
        result_msg, details = await self.bot.management_service.run_rollback(bot_id)
        
        if details:
            from core.views import UpdateResultEmbed
            title = get_feedback(self.bot.i18n, "bot_rollback_title")
            embed = UpdateResultEmbed(self.bot.i18n, title, details, ui_settings=self.bot.ui_settings, is_rollback=True)
            await interaction.followup.send(embed=embed, ephemeral=False)
        else:
            await interaction.followup.send(result_msg, ephemeral=False)

    @app_commands.command(name="logs", description="[Bot Dev] Get last N lines of a bot log file.")
    @app_commands.describe(bot_id="The ID of the bot", lines="Number of lines")
    @is_monitor_context()
    @app_commands.autocomplete(bot_id=bot_id_autocomplete)
    async def logs(self, interaction: discord.Interaction, bot_id: str, lines: int | None = None):
        if lines is None:
            lines = self.bot.config.get("bot_settings", {}).get("log_default_lines", 50)
            
        log.info(f"User {interaction.user} (ID: {interaction.user.id}) requested /logs ({lines} lines) for bot: {bot_id}")
        await interaction.response.defer(ephemeral=False)
        
        if bot_id not in self.bot.bots:
            await interaction.followup.send(get_feedback(self.bot.i18n, "error_unknown_bot"), ephemeral=True)
            return
            
        bot = self.bot.bots[bot_id]
        default_log_name = self.bot.config.get("bot_settings", {}).get("bot_log_default", "bot.log")
        log_name = bot.log if bot.log else default_log_name
        log_path = os.path.join(bot.path, log_name)
        
        if os.path.exists(log_path):
            try:
                if lines > 0:
                    with open(log_path, "r", encoding="utf-8", errors="replace") as f:
                        last_lines = deque(f, maxlen=lines)
                    
                    content = "".join(last_lines)
                    if not content:
                        await interaction.followup.send(get_feedback(self.bot.i18n, "error_log_empty"), ephemeral=True)
                        return

                    temp_file = "temp_logs.txt"
                    with open(temp_file, "w", encoding="utf-8") as f:
                        f.write(content)
                    
                    file = discord.File(temp_file, filename=f"{bot.name}_logs.txt")
                    header = get_feedback(self.bot.i18n, "log_fetch_header", name=bot.name, count=lines)
                    await interaction.followup.send(header, file=file, ephemeral=True)
                    
                    # Cleanup temp file
                    os.remove(temp_file)
                else:
                    file = discord.File(log_path, filename=f"{bot.name}_full_logs.txt")
                    header = get_feedback(self.bot.i18n, "logs_full_header", name=bot.name)
                    await interaction.followup.send(header, file=file, ephemeral=True)
            except Exception as e:
                await interaction.followup.send(get_feedback(self.bot.i18n, "error_log_fetch", error=str(e)), ephemeral=True)
        else:
            await interaction.followup.send(get_feedback(self.bot.i18n, "error_log_not_found", path=log_path), ephemeral=True)

    @app_commands.command(name="manager-logs", description="[Bot Dev] Get last N lines of the Bot Manager log.")
    @app_commands.describe(lines="Number of lines")
    @is_admin_context()
    async def manager_logs(self, interaction: discord.Interaction, lines: int | None = None):
        if lines is None:
            lines = self.bot.config.get("bot_settings", {}).get("log_default_lines", 50)
            
        log.info(f"User {interaction.user} (ID: {interaction.user.id}) requested /manager-logs ({lines} lines)")
        await interaction.response.defer(ephemeral=False)
        
        log_path = self.bot.config.get("bot_settings", {}).get("manager_log_file", "manager.log")
        
        if os.path.exists(log_path):
            try:
                if lines > 0:
                    with open(log_path, "r", encoding="utf-8", errors="replace") as f:
                        last_lines = deque(f, maxlen=lines)
                    
                    content = "".join(last_lines)
                    if not content:
                        await interaction.followup.send(get_feedback(self.bot.i18n, "error_manager_log_empty"), ephemeral=True)
                        return

                    temp_file = "temp_manager_logs.txt"
                    with open(temp_file, "w", encoding="utf-8") as f:
                        f.write(content)
                    
                    file = discord.File(temp_file, filename=f"manager_last_{lines}_lines.txt")
                    header = get_feedback(self.bot.i18n, "manager_logs_header", lines=lines)
                    await interaction.followup.send(header, file=file, ephemeral=False)
                    os.remove(temp_file)
                else:
                    file = discord.File(log_path, filename="manager_full_logs.txt")
                    header = get_feedback(self.bot.i18n, "manager_logs_full_header")
                    await interaction.followup.send(header, file=file, ephemeral=False)
            except Exception as e:
                await interaction.followup.send(self.bot.i18n.get("error_log_fetch", "Error fetching logs: {error}", error=str(e)), ephemeral=True)
        else:
            await interaction.followup.send(get_feedback(self.bot.i18n, "error_manager_log_not_found"), ephemeral=True)

    @app_commands.command(name="manager-restart", description="[Bot Dev] Immediate restart of Bot Manager.")
    @is_admin_context()
    async def manager_restart(self, interaction: discord.Interaction):
        log.info(f"User {interaction.user} requested /manager-restart. Restarting {self.bot.manager_name}...")
        msg = get_feedback(self.bot.i18n, "manager_restart_msg", name=self.bot.manager_name, pid=os.getpid())
        await interaction.response.send_message(msg, ephemeral=False)
        
        self.bot.management_service.prepare_manager_restart()
        await asyncio.sleep(2) # Give Discord time to finish delivery
        
        # Manual panel cleanup BEFORE restart to prevent ghost panels
        try:
            monitor = self.bot.get_cog('MonitoringCog')
            if monitor and monitor.status_message_id:
                log.info(f"[CleanRestart] Deleting old panel {monitor.status_message_id} before restart...")
                channel = self.bot.get_channel(int(monitor.status_channel_id))
                if not channel:
                    channel = await self.bot.fetch_channel(int(monitor.status_channel_id))
                if channel:
                    try:
                        old_msg = await channel.fetch_message(int(monitor.status_message_id))
                        await old_msg.delete()
                        log.info("[CleanRestart] Old panel deleted successfully.")
                    except discord.NotFound:
                        pass
        except Exception as e:
            log.warning(f"[CleanRestart] Failed to delete panel before restart: {e}")

        # Robust restart logic
        try:
            os.execv(sys.executable, [sys.executable] + sys.argv)
        except Exception as e:
            log.error(f"os.execv failed during manual restart, trying subprocess fallback: {e}")
            import subprocess
            subprocess.Popen([sys.executable] + sys.argv)
            sys.exit(0)


    @app_commands.command(name="manager-update", description="[Bot Dev] Git pull, pip install and restart Bot Manager.")
    @is_admin_context()
    async def manager_update(self, interaction: discord.Interaction):
        log.info(f"User {interaction.user} requested /manager-update for {self.bot.manager_name}.")
        await interaction.response.defer(ephemeral=False)
        
        # Immediate feedback so the user knows it's doing something
        updating_msg = get_feedback(self.bot.i18n, "manager_updating", name=self.bot.manager_name)
        await interaction.followup.send(updating_msg, ephemeral=False)

        
        try:
            success, output, changed, details = await self.bot.management_service.run_manager_update()
            
            if not success:
                msg = get_feedback(self.bot.i18n, "error_update_failed_output", output=output)
                await interaction.followup.send(msg, ephemeral=True)
                return

            if not changed:
                # No changes found, skip restart
                await interaction.followup.send(get_feedback(self.bot.i18n, "update_no_changes"), ephemeral=False)
                return

            # Final response and restart
            if details:
                from core.views import UpdateResultEmbed
                title = get_feedback(self.bot.i18n, "manager_updated_title")
                embed = UpdateResultEmbed(self.bot.i18n, title, details, ui_settings=self.bot.ui_settings)
                await interaction.followup.send(embed=embed, ephemeral=False)
            else:
                msg = get_feedback(self.bot.i18n, "manager_update_success", name=self.bot.manager_name, output=output)
                if len(msg) > 1900:
                    msg = msg[:1000] + "\n... [TRUNCATED] ...\n" + msg[-800:]
                await interaction.followup.send(msg, ephemeral=False)
            
            log.info("Manager updated, restarting process...")
            self.bot.management_service.prepare_manager_restart()
            
            await asyncio.sleep(2) # Give Discord more time to finish delivery
            
            # Manual panel cleanup BEFORE restart to prevent ghost panels
            try:
                monitor = self.bot.get_cog('MonitoringCog')
                if monitor and monitor.status_message_id:
                    log.info(f"[CleanRestart] Deleting old panel {monitor.status_message_id} before restart...")
                    channel = self.bot.get_channel(int(monitor.status_channel_id))
                    if not channel:
                        channel = await self.bot.fetch_channel(int(monitor.status_channel_id))
                    if channel:
                        try:
                            old_msg = await channel.fetch_message(int(monitor.status_message_id))
                            await old_msg.delete()
                            log.info("[CleanRestart] Old panel deleted successfully.")
                        except discord.NotFound:
                            pass
            except Exception as e:
                log.warning(f"[CleanRestart] Failed to delete panel before restart: {e}")

            # Robust restart logic
            try:
                os.execv(sys.executable, [sys.executable] + sys.argv)
            except Exception as e:
                log.error(f"os.execv failed during update restart, trying subprocess fallback: {e}")
                import subprocess
                subprocess.Popen([sys.executable] + sys.argv)
                sys.exit(0)


        except Exception as e:
            log.error(f"Manager update failed: {e}")
            await interaction.followup.send(get_feedback(self.bot.i18n, "error_update_general", error=str(e)), ephemeral=True)

    @commands.command(name="sync")
    @commands.guild_only()
    @is_admin_prefix_context()
    async def sync_prefix(self, ctx: commands.Context, spec: str | None = None):
        """[Admin] Sync slash commands manually (guild/global/copy)."""
        # 1. Always localize GLOBAL commands first (they are the source for copy_global_to)
        self.bot.i18n.localize_commands(self.bot.tree, guild=None)
        
        # 2. Localize any guild-specific commands separately if they exist
        if ctx.guild:
            self.bot.i18n.localize_commands(self.bot.tree, guild=ctx.guild)

        if spec == "global":
            synced = await self.bot.tree.sync()
            msg = get_feedback(self.bot.i18n, "sync_success_global", count=len(synced))
            await ctx.send(msg)
        elif spec == "copy":
            self.bot.tree.copy_global_to(guild=ctx.guild)
            synced = await self.bot.tree.sync(guild=ctx.guild)
            msg = get_feedback(self.bot.i18n, "sync_success_copy", count=len(synced))
            await ctx.send(msg)
        else:
            # Sync only to this guild (instant)
            log.info(f"[Sync] Attempting guild sync for {ctx.guild.id}...")
            await ctx.send(f"{Icons.WRENCH} Szinkronizálás folyamatban...")
            synced = await self.bot.tree.sync(guild=ctx.guild)
            msg = get_feedback(self.bot.i18n, "sync_success_guild", count=len(synced))
            await ctx.send(msg)

    @commands.command(name="clear_commands")
    @commands.guild_only()
    @is_admin_prefix_context()
    async def clear_commands_prefix(self, ctx: commands.Context):
        """[Admin] Emergency clear of all slash commands."""
        log.info(f"[Clear] User {ctx.author} requested slash command purge.")
        await ctx.send(f"{Icons.WRENCH} Parancsok törlése folyamatban... Ez eltarthat egy ideig.")
        
        # Clear Global
        self.bot.tree.clear_commands(guild=None)
        await self.bot.tree.sync(guild=None)
        # Clear Guild
        self.bot.tree.clear_commands(guild=ctx.guild)
        await self.bot.tree.sync(guild=ctx.guild)
        
        log.info("[Clear] Slash commands cleared successfully.")
        await ctx.send(get_feedback(self.bot.i18n, "clear_commands_success"))

    @app_commands.command(name="sync", description="[Bot Dev] Sync slash commands manually.")
    @app_commands.describe(mode="guild (instant), global (slow), or copy")
    @is_admin_context()
    async def sync_slash(self, interaction: discord.Interaction, mode: str = "guild"):
        log.info(f"User {interaction.user} requested /sync mode={mode}")
        await interaction.response.defer(ephemeral=True)

        # 1. Localize commands before syncing
        self.bot.i18n.localize_commands(self.bot.tree, guild=interaction.guild if mode != "global" else None)

        if mode == "global":
            synced = await self.bot.tree.sync()
            msg = get_feedback(self.bot.i18n, "sync_success_global", count=len(synced))
            await interaction.followup.send(msg, ephemeral=True)
        elif mode == "copy":
            self.bot.tree.copy_global_to(guild=interaction.guild)
            synced = await self.bot.tree.sync(guild=interaction.guild)
            msg = get_feedback(self.bot.i18n, "sync_success_copy", count=len(synced))
            await interaction.followup.send(msg, ephemeral=True)
        else:
            # Sync only to this guild (immediate)
            synced = await self.bot.tree.sync(guild=interaction.guild)
            msg = get_feedback(self.bot.i18n, "sync_success_guild", count=len(synced))
            await interaction.followup.send(msg, ephemeral=True)

    @app_commands.command(name="purge", description="[Bot Dev] Deletes all messages in the current channel.")
    @is_monitor_context()
    async def purge(self, interaction: discord.Interaction):
        """Törli az összes üzenetet a csatornában (Adminoknak/Mechanicoknak)."""
        await interaction.response.defer(ephemeral=True)
        
        from core.utils import AccessLevel, get_user_level
        level = get_user_level(interaction.user, self.bot)
        if level < AccessLevel.MECHANIC:
            await interaction.followup.send("🛡️ Ebhez a művelethez nincs jogosultságod, ellenőr úr!", ephemeral=True)
            return
        
        try:
            # Purge deletes messages
            purge_limit = self.bot.config.get("bot_settings", {}).get("purge_limit", 1000)
            deleted = await interaction.channel.purge(limit=purge_limit)
            
            count = len(deleted)
            msg = get_feedback(self.bot.i18n, "purge_success", count=count)
            await interaction.followup.send(msg, ephemeral=True)
            log.info(f"User {interaction.user} purged {count} messages in channel {interaction.channel.name}")
            
        except discord.Forbidden:
            msg = get_feedback(self.bot.i18n, "purge_error", error="Forbidden")
            await interaction.followup.send(msg, ephemeral=True)
        except Exception as e:
            log.error(f"Error during purge: {e}")
            msg = get_feedback(self.bot.i18n, "purge_error", error=str(e))
            await interaction.followup.send(msg, ephemeral=True)

async def setup(bot):
    cog = ManagementCog(bot)
    suffix = getattr(bot, 'command_suffix', '')
    if suffix:
        # We set aliases on the command objects before adding the cog to the bot.
        # This ensures discord.py registers them correctly in its internal map.
        cog.sync_prefix.aliases = [f"sync{suffix}"]
        cog.clear_commands_prefix.aliases = [f"clear_commands{suffix}"]
        cog.ping_prefix.aliases = [f"ping{suffix}"]
        log.info(f"[Admin] Dynamic aliases prepared for suffix: {suffix}")
        
    await bot.add_cog(cog)
