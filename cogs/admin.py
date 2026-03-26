import discord
from discord import app_commands
from discord.ext import commands
import os
import json
import asyncio
import subprocess
import sys
from collections import deque
from core.utils import is_admin_context
from core.logger import log

async def bot_id_autocomplete(
    interaction: discord.Interaction,
    current: str,
) -> list[app_commands.Choice[str]]:
    bot_manager = interaction.client # The main bot instance (BotManager)
    
    choices = []
    is_logs_command = interaction.command and interaction.command.name == "logs"
    
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
        # We apply the command suffix from config.json to our prefix commands
        suffix = getattr(bot, 'command_suffix', '')
        self.sync_prefix.name = f"sync{suffix}"
        self.clear_commands_prefix.name = f"clear_commands{suffix}"

    @app_commands.command(name="update", description="Update and restart a bot by ID.")
    @app_commands.describe(bot_id="The ID of the bot to update")
    @is_admin_context()
    @app_commands.autocomplete(bot_id=bot_id_autocomplete)
    async def update(self, interaction: discord.Interaction, bot_id: str):
        log.info(f"User {interaction.user} (ID: {interaction.user.id}) requested /update for bot: {bot_id}")
        await interaction.response.defer(ephemeral=True)
        result = await self.bot.management_service.run_update(bot_id)
        if len(result) > 1900:
            result = result[:1000] + "\n\n... [TRUNCATED] ...\n\n" + result[-800:]
        await interaction.followup.send(result, ephemeral=True)

    @app_commands.command(name="restart", description="Restart a bot without update.")
    @app_commands.describe(bot_id="The ID of the bot to restart")
    @is_admin_context()
    @app_commands.autocomplete(bot_id=bot_id_autocomplete)
    async def restart(self, interaction: discord.Interaction, bot_id: str):
        log.info(f"User {interaction.user} (ID: {interaction.user.id}) requested /restart for bot: {bot_id}")
        await interaction.response.defer(ephemeral=True)
        
        result = await self.bot.management_service.run_restart(bot_id)
        await interaction.followup.send(result, ephemeral=True)

    @app_commands.command(name="rollback", description="Rollback bot to previous Git state (HEAD@{1}).")
    @app_commands.describe(bot_id="The ID of the bot to rollback")
    @is_admin_context()
    @app_commands.autocomplete(bot_id=bot_id_autocomplete)
    async def rollback(self, interaction: discord.Interaction, bot_id: str):
        log.info(f"User {interaction.user} (ID: {interaction.user.id}) requested /rollback for bot: {bot_id}")
        await interaction.response.defer(ephemeral=True)
        
        result = await self.bot.management_service.run_rollback(bot_id)
        await interaction.followup.send(result, ephemeral=True)

    @app_commands.command(name="logs", description="Get last N lines of a bot log file.")
    @app_commands.describe(bot_id="The ID of the bot", lines="Number of lines (default: 50, all: 0)")
    @is_admin_context()
    @app_commands.autocomplete(bot_id=bot_id_autocomplete)
    async def logs(self, interaction: discord.Interaction, bot_id: str, lines: int = 50):
        log.info(f"User {interaction.user} (ID: {interaction.user.id}) requested /logs ({lines} lines) for bot: {bot_id}")
        await interaction.response.defer(ephemeral=True)
        
        if bot_id not in self.bot.bots:
            await interaction.followup.send(str(self.bot.i18n.get("error_unknown_bot", "Unknown Bot ID.")), ephemeral=True)
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
                        await interaction.followup.send(self.bot.i18n.get("error_log_empty", "Log file is empty."), ephemeral=True)
                        return

                    temp_file = "temp_logs.txt"
                    with open(temp_file, "w", encoding="utf-8") as f:
                        f.write(content)
                    
                    file = discord.File(temp_file, filename=f"{bot.name}_last_{lines}_lines.txt")
                    header = self.bot.i18n.get("logs_header", "Last {lines} lines of {name}:", name=bot.name, lines=lines)
                    await interaction.followup.send(header, file=file, ephemeral=True)
                    os.remove(temp_file)
                else:
                    file = discord.File(log_path, filename=f"{bot.name}_full_logs.txt")
                    header = self.bot.i18n.get("logs_full_header", "Full log of {name}:", name=bot.name)
                    await interaction.followup.send(header, file=file, ephemeral=True)
            except Exception as e:
                await interaction.followup.send(self.bot.i18n.get("error_log_fetch", "Error fetching logs: {error}", error=str(e)), ephemeral=True)
        else:
            await interaction.followup.send(self.bot.i18n.get("error_log_not_found", "Log file not found at: `{path}`", path=log_path), ephemeral=True)

    @app_commands.command(name="manager-logs", description="Get last N lines of the Bot Manager log.")
    @app_commands.describe(lines="Number of lines (default: 50, all: 0)")
    @is_admin_context()
    async def manager_logs(self, interaction: discord.Interaction, lines: int = 50):
        log.info(f"User {interaction.user} (ID: {interaction.user.id}) requested /manager-logs ({lines} lines)")
        await interaction.response.defer(ephemeral=True)
        
        log_path = self.bot.config.get("bot_settings", {}).get("manager_log_file", "manager.log")
        
        if os.path.exists(log_path):
            try:
                if lines > 0:
                    with open(log_path, "r", encoding="utf-8", errors="replace") as f:
                        last_lines = deque(f, maxlen=lines)
                    
                    content = "".join(last_lines)
                    if not content:
                        await interaction.followup.send(self.bot.i18n.get("error_manager_log_empty", "Manager log is empty."), ephemeral=True)
                        return

                    temp_file = "temp_manager_logs.txt"
                    with open(temp_file, "w", encoding="utf-8") as f:
                        f.write(content)
                    
                    file = discord.File(temp_file, filename=f"manager_last_{lines}_lines.txt")
                    header = self.bot.i18n.get("manager_logs_header", "Last {lines} lines of Bot Manager:", lines=lines)
                    await interaction.followup.send(header, file=file, ephemeral=True)
                    os.remove(temp_file)
                else:
                    file = discord.File(log_path, filename="manager_full_logs.txt")
                    header = self.bot.i18n.get("manager_logs_full_header", "Full log of Bot Manager:")
                    await interaction.followup.send(header, file=file, ephemeral=True)
            except Exception as e:
                await interaction.followup.send(self.bot.i18n.get("error_log_fetch", "Error fetching logs: {error}", error=str(e)), ephemeral=True)
        else:
            await interaction.followup.send(self.bot.i18n.get("error_manager_log_not_found", "Manager log file not found."), ephemeral=True)

    @app_commands.command(name="manager-restart", description="[Admin] Immediate restart of Bot Manager.")
    @is_admin_context()
    async def manager_restart(self, interaction: discord.Interaction):
        log.info(f"User {interaction.user} requested /manager-restart. Restarting {self.bot.manager_name}...")
        msg = self.bot.i18n.get("manager_restart_msg", "Restarting {name}... ", name=self.bot.manager_name)
        await interaction.response.send_message(msg, ephemeral=True)
        
        self.bot.management_service.prepare_manager_restart()
        os.execv(sys.executable, ['python'] + sys.argv)

    @app_commands.command(name="manager-update", description="[Admin] Git pull, pip install and restart Bot Manager.")
    @is_admin_context()
    async def manager_update(self, interaction: discord.Interaction):
        log.info(f"User {interaction.user} requested /manager-update for {self.bot.manager_name}.")
        await interaction.response.defer(ephemeral=True)
        
        manager_path = os.getcwd() # Manager works from its own CWD
        results = []
        
        try:
            success, output = await self.bot.management_service.run_manager_update()
            
            if not success:
                error_prefix = self.bot.i18n.get("error_git_update_failed", "Git update failed.")
                await interaction.followup.send(f"{error_prefix}\n{output}", ephemeral=True)
                return

            # Final response and restart
            update_status = self.bot.i18n.get("manager_update_success", "Manager updated. Restarting...", name=self.bot.manager_name, output=output)
            
            # Truncate if needed
            if len(update_status) > 1900:
                update_status = update_status[:1000] + "\n... [TRUNCATED] ...\n" + update_status[-800:]
                
            await interaction.followup.send(update_status, ephemeral=True)
            
            log.info("Manager updated, restarting process...")
            self.bot.management_service.prepare_manager_restart()
            
            await asyncio.sleep(1) # Wait for message to send
            os.execv(sys.executable, ['python'] + sys.argv)
        except Exception as e:
            log.error(f"Manager update failed: {e}")
            await interaction.followup.send(self.bot.i18n.get("error_update_general", "Error during update: {error}", error=str(e)), ephemeral=True)

    @commands.command(name="sync")
    @commands.guild_only()
    async def sync_prefix(self, ctx: commands.Context, spec: str | None = None):
        """[Admin] Sync slash commands manually (guild/global/copy)."""
        # Safety check: only allow in admin channel if configured
        admin_channel_id = getattr(self.bot, 'admin_channel_id', None)
        if admin_channel_id and str(ctx.channel.id) != str(admin_channel_id):
            return

        # 1. Localize commands before syncing
        self.bot.i18n.localize_commands(self.bot.tree, guild=ctx.guild if spec != "global" else None)

        if spec == "global":
            synced = await self.bot.tree.sync()
            msg = self.bot.i18n.get("sync_success_global", "Synced {count} commands globally.", count=len(synced))
            await ctx.send(msg)
        elif spec == "copy":
            self.bot.tree.copy_global_to(guild=ctx.guild)
            synced = await self.bot.tree.sync(guild=ctx.guild)
            msg = self.bot.i18n.get("sync_success_copy", "Synced {count} commands to guild.", count=len(synced))
            await ctx.send(msg)
        else:
            # Sync only to this guild (immediate)
            synced = await self.bot.tree.sync(guild=ctx.guild)
            msg = self.bot.i18n.get("sync_success_guild", "Synced {count} commands to guild.", count=len(synced))
            await ctx.send(msg)

    @commands.command(name="clear_commands")
    @commands.guild_only()
    async def clear_commands_prefix(self, ctx: commands.Context):
        """[Admin] Emergency clear of all slash commands."""
        admin_channel_id = getattr(self.bot, 'admin_channel_id', None)
        if admin_channel_id and str(ctx.channel.id) != str(admin_channel_id):
            return

        # Clear Global
        self.bot.tree.clear_commands(guild=None)
        await self.bot.tree.sync(guild=None)
        # Clear Guild
        self.bot.tree.clear_commands(guild=ctx.guild)
        await self.bot.tree.sync(guild=ctx.guild)
        
        await ctx.send(self.bot.i18n.get("clear_commands_success", "All commands cleared."))

    @app_commands.command(name="sync", description="[Admin] Sync slash commands manually.")
    @app_commands.describe(mode="guild (instant), global (slow), or copy")
    @is_admin_context()
    async def sync_slash(self, interaction: discord.Interaction, mode: str = "guild"):
        log.info(f"User {interaction.user} requested /sync mode={mode}")
        await interaction.response.defer(ephemeral=True)

        # 1. Localize commands before syncing
        self.bot.i18n.localize_commands(self.bot.tree, guild=interaction.guild if mode != "global" else None)

        if mode == "global":
            synced = await self.bot.tree.sync()
            msg = self.bot.i18n.get("sync_success_global", "Synced {count} commands globally.", count=len(synced))
            await interaction.followup.send(msg, ephemeral=True)
        elif mode == "copy":
            self.bot.tree.copy_global_to(guild=interaction.guild)
            synced = await self.bot.tree.sync(guild=interaction.guild)
            msg = self.bot.i18n.get("sync_success_copy", "Synced {count} commands to guild.", count=len(synced))
            await interaction.followup.send(msg, ephemeral=True)
        else:
            synced = await self.bot.tree.sync(guild=interaction.guild)
            msg = self.bot.i18n.get("sync_success_guild", "Synced {count} commands to guild.", count=len(synced))
            await interaction.followup.send(msg, ephemeral=True)

async def setup(bot):
    await bot.add_cog(ManagementCog(bot))
