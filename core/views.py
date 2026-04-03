import discord
from discord.ui import LayoutView, ActionRow, Container, TextDisplay, Separator, Section, Thumbnail
import os
import sys
import asyncio
import subprocess


from core.logger import log

from core.icons import Icons
from core.utils import get_feedback

class BotControlButton(discord.ui.Button):
    def __init__(self, style=discord.ButtonStyle.secondary, emoji=None, bot_id=None, bot_name=None, action=None, view=None):
        # Debug: log the emoji object
        log.debug(f"[UI] Creating button for {bot_id}:{action} with emoji: {emoji} (Type: {type(emoji)})")
        # Custom IDs for state persistence and clean emoji-only buttons
        cid = f"status:{bot_id}:{action}"
        super().__init__(style=style, label=None, emoji=emoji, custom_id=cid)
        self.bot_id = bot_id
        self.bot_name = bot_name
        self.action = action # 'restart', 'stop', 'update'
        self.parent_view = view

    async def callback(self, interaction: discord.Interaction):
        # We simply pass the request to our helper function
        await handle_status_interaction(interaction, self.bot_id, self.action, self.bot_name)

async def handle_status_interaction(interaction: discord.Interaction, bot_id: str, action: str, bot_name: str = None):
    """Core logic for handling status panel interactions (buttons)."""
    bot = interaction.client
    i18n = getattr(bot, 'i18n', None)
    
    from core.utils import AccessLevel, get_user_level
    
    # 1. Determine User Level
    level = get_user_level(interaction.user, bot)
    
    # 2. Determine Required Level for Action
    required_level = AccessLevel.MECHANIC
    if action == "update" or action.endswith("-update"):
        required_level = AccessLevel.BOSS
    elif action == "restart" or action.endswith("-restart"):
        required_level = AccessLevel.INSPECTOR
    elif action == "stop" or action.endswith("-stop"):
        required_level = AccessLevel.MECHANIC
    
    # 3. Check Level Permissions
    if level < required_level:
        msg = get_feedback(i18n, "error_admin_only") if level < AccessLevel.INSPECTOR else "🛡️ Ehhez a művelethez nincs jogosultságod, ellenőr úr!"
        await interaction.response.send_message(msg, ephemeral=True)
        return
        
    # 4. Context (Channel) check
    # BOSS can do anything anywhere (e.g. from an ephemeral snapshot in another channel)
    # Others MUST be in the Admin Workshop
    is_admin_channel = bot.admin_channel_id and str(interaction.channel_id) == str(bot.admin_channel_id)
    if level < AccessLevel.BOSS and not is_admin_channel:
        await interaction.response.send_message(get_feedback(i18n, "error_admin_channel_only"), ephemeral=True)
        return
        
    # All checks passed
    await interaction.response.defer(ephemeral=not is_admin_channel)
    
    # Resolve bot name if not provided (needed for global handler)
    if not bot_name:
        if bot_id == "manager":
            bot_name = getattr(bot, 'manager_name', 'Bot Manager')
        elif hasattr(bot, 'bots') and bot_id in bot.bots:
            bot_name = bot.bots[bot_id].name
        else:
            bot_name = bot_id
            
    service = getattr(bot, 'management_service', None)
    if not service:
        # Fallback for dynamic access if needed
        from core.management_service import ManagementService
        service = ManagementService(bot)
        
    result = ""
    
    # SPECIAL HANDLING FOR MANAGER SELF-CONTROLS
    if bot_id == "manager":
        if action == "restart":
            log.info(f"User {interaction.user} clicked SELF-RESTART for Manager")
            service.prepare_manager_restart()
            await interaction.followup.send(get_feedback(i18n, "status_restarting"), ephemeral=False)
            await asyncio.sleep(2)
            
            # Robust restart logic
            try:
                os.execv(sys.executable, [sys.executable] + sys.argv)
            except Exception as e:
                log.error(f"os.execv failed, trying subprocess fallback: {e}")
                subprocess.Popen([sys.executable] + sys.argv)
                sys.exit(0)

            return

        elif action == "stop":
            log.info(f"User {interaction.user} clicked SELF-STOP for Manager")
            await interaction.followup.send(get_feedback(i18n, "status_stopping"), ephemeral=False)
            await asyncio.sleep(1)
            sys.exit(0)
            return
        elif action == "update":
            log.info(f"User {interaction.user} clicked SELF-UPDATE for Manager")
            
            # Immediate feedback
            updating_msg = get_feedback(i18n, "manager_updating", name="Manager")
            await interaction.followup.send(updating_msg, ephemeral=False)
            
            success, output, changed, details = await service.run_manager_update()

            if not success:
                if len(output) > 1500:
                    output = output[:700] + "\n... [TRUNCATED] ...\n" + output[-700:]
                msg = get_feedback(i18n, "error_update_failed_output", output=output)
                await interaction.followup.send(msg, ephemeral=False)
                return
            if not changed:
                await interaction.followup.send(get_feedback(i18n, "update_no_changes"), ephemeral=False)
                return
            # If changed and success, trigger restart
            service.prepare_manager_restart()
            
            if details:
                title = get_feedback(i18n, "update_result_title", name="Manager")
                embed = UpdateResultEmbed(i18n, title, details, ui_settings=getattr(bot, 'ui_settings', None))
                await interaction.followup.send(embed=embed, ephemeral=False)
            else:
                msg = get_feedback(i18n, "manager_update_success", name="Manager", output=output)
                if len(msg) > 1900:
                    msg = msg[:1000] + "\n... [TRUNCATED] ...\n" + msg[-800:]
                await interaction.followup.send(msg, ephemeral=False)
            
            await asyncio.sleep(2)
            
            # Manual panel cleanup BEFORE restart to prevent ghost panels
            try:
                monitor = bot.get_cog('MonitoringCog')
                if monitor and monitor.status_message_id:
                    log.debug(f"[CleanRestart] Deleting old panel {monitor.status_message_id} before restart...")
                    channel = bot.get_channel(int(monitor.status_channel_id))
                    if not channel:
                        channel = await bot.fetch_channel(int(monitor.status_channel_id))
                    if channel:
                        try:
                            old_msg = await channel.fetch_message(int(monitor.status_message_id))
                            await old_msg.delete()
                            log.debug("[CleanRestart] Old panel deleted successfully.")
                        except discord.NotFound:
                            pass
            except Exception as e:
                log.warning(f"[CleanRestart] Failed to delete panel before restart: {e}")

            # Robust restart logic
            try:
                os.execv(sys.executable, [sys.executable] + sys.argv)
            except Exception as e:
                log.error(f"os.execv failed during update, trying subprocess fallback: {e}")
                subprocess.Popen([sys.executable] + sys.argv)
                sys.exit(0)

            return

    # STANDARD BOT CONTROLS
    if action == "restart":
        log.info(f"User {interaction.user} clicked RESTART for {bot_name} ({bot_id})")
        result = await service.run_restart(bot_id)
    elif action == "stop":
        log.info(f"User {interaction.user} clicked STOP for {bot_name} ({bot_id})")
        await service.process_manager.stop_process(bot_id)
        result = get_feedback(i18n, "status_stopped")
    elif action == "update":
        log.info(f"User {interaction.user} clicked UPDATE for {bot_name} ({bot_id})")
        result_msg, details = await service.run_update(bot_id)
        
        # Clear the "update available" flag immediately on success
        if details:
            monitor = bot.get_cog('MonitoringCog')
            if monitor:
                # Clear for this bot AND all related bots sharing the same path
                updated_path = bot.bots[bot_id].path if bot_id in bot.bots else None
                monitor.git_behind_status[bot_id] = False
                if updated_path:
                    for bid, bcfg in bot.bots.items():
                        if bcfg.path == updated_path:
                            monitor.git_behind_status[bid] = False
                log.info(f"[Update] Cleared git_behind_status for {bot_id} and related bots")
                
                # Schedule a delayed panel refresh so the callback can finish first
                async def _delayed_panel_refresh(monitor_ref, bot_ref, i18n_ref):
                    await asyncio.sleep(3)
                    try:
                        if monitor_ref.status_channel_id and monitor_ref.status_message_id:
                            ch = bot_ref.get_channel(int(monitor_ref.status_channel_id))
                            if not ch:
                                ch = await bot_ref.fetch_channel(int(monitor_ref.status_channel_id))
                            if ch:
                                panel_msg = await ch.fetch_message(int(monitor_ref.status_message_id))
                                if panel_msg:
                                    ms, bs = monitor_ref.get_status_data()
                                    new_view = ModernStatusView(bot_ref, i18n_ref, ms, bs)
                                    await panel_msg.edit(view=new_view)
                                    log.info("[Update] Panel refreshed after delay.")
                    except Exception as ex:
                        log.warning(f"[Update] Delayed panel refresh failed: {ex}")
                
                bot.loop.create_task(_delayed_panel_refresh(monitor, bot, i18n))

            title = get_feedback(i18n, "update_result_title", name=bot_name)
            embed = UpdateResultEmbed(i18n, title, details)
            await interaction.followup.send(embed=embed, ephemeral=False)
            return
        else:
            result = result_msg
        
    if len(result) > 1900:
        result = result[:1000] + "\n... [TRUNCATED] ...\n" + result[-800:]
        
    await interaction.followup.send(result, ephemeral=False)
        # We don't refresh the whole status message automatically here to avoid rate limits,
        # the user can click the Global Refresh button if they want.

class StatusContainer(Container):
    """A visual container box for the status content."""
    def __init__(self, bot_manager, i18n, manager_stats, bots_stats, parent_view):
        ui = getattr(bot_manager, 'ui_settings', {})
        accent = ui.get("accent_color", 0x2b2d31)
        super().__init__(accent_color=accent) # Dynamic accent color
        
        # We use the Icons class which was setup in manager.py
        restart_emoji = Icons.RESTART
        update_emoji = Icons.UPDATE
        stop_emoji = Icons.STOP

        # 1. Manager Header & Stats
        cpu_label = get_feedback(i18n, "cpu")
        ram_label = get_feedback(i18n, "ram")
        host_label = get_feedback(i18n, "host_os")
        free_label = get_feedback(i18n, "system_free")
        disk_label = get_feedback(i18n, "disk")
        swap_label = get_feedback(i18n, "swap")
        server_up_label = get_feedback(i18n, "server_uptime")
        log_label = get_feedback(i18n, "log_size")
        update_available_msg = get_feedback(i18n, "update_available")
        
        manager_up_alert = f" **{update_available_msg}**" if manager_stats.get("has_update") else ""
        
        manager_text = (
            f"**{bot_manager.manager_name}**{manager_up_alert}\n"
            f"**{get_feedback(i18n, 'status_running')}**\n"
            f"> {get_feedback(i18n, 'uptime')}: {manager_stats['uptime']} | {server_up_label}: {manager_stats['host_uptime']}\n"
            f"> {get_feedback(i18n, 'branch')}: `{manager_stats['branch']}`\n"
            f"> {host_label}: `{manager_stats['os']}`\n"
            f"> {get_feedback(i18n, 'resources')}: {cpu_label}: `{manager_stats['cpu']}%` | {ram_label}: `{int(manager_stats['ram'])} MB` | Net: `{manager_stats['net']}`\n"
            f"> {free_label}: CPU: `{int(manager_stats['sys_cpu_free'])}%` | {ram_label}: `{int(manager_stats['sys_ram_free'])} MB` | {disk_label}: `{int(manager_stats['sys_disk_free'])} GB` | {swap_label}: `{manager_stats['swap']}%`"
        )
        self.add_item(TextDisplay(manager_text))
        
        # Manager Buttons Row
        mgr_row = ActionRow()

        # Manager Restart
        mgr_row.add_item(BotControlButton(emoji=restart_emoji, bot_id="manager", action="restart", view=parent_view))
        # Manager Update
        mgr_row.add_item(BotControlButton(emoji=update_emoji, bot_id="manager", action="update", view=parent_view))
        # Manager Stop
        mgr_row.add_item(BotControlButton(emoji=stop_emoji, bot_id="manager", action="stop", view=parent_view))
        
        self.add_item(mgr_row)
        self.add_item(Separator(visible=True, spacing=discord.enums.SeparatorSpacing.large))

        # 2. Managed Bots Sections
        if bots_stats:
            self.add_item(TextDisplay(f"**{get_feedback(i18n, 'bots_status_header')}**"))
            
            # We keep track of the indexed for separator logic
            bot_list = list(bots_stats.items())
            for i, (b_id, b_info) in enumerate(bot_list):
                b_name = b_info["name"]
                up_alert = f" **{update_available_msg}**" if b_info.get("has_update") else ""
                
                if b_info["is_running"]:
                    up_label = get_feedback(i18n, "uptime_short")
                    details = f"{cpu_label}: `{b_info['cpu']}%` | {ram_label}: `{int(b_info['ram'])} MB` | {up_label}: {b_info['uptime']} | {log_label}: `{b_info['log_size']}`"
                    bot_text = f"**{b_info['status']} • {b_name}** ({b_id}){up_alert}\n{details}\n`{get_feedback(i18n, 'path')}: {b_info['path']}`"
                else:
                    bot_text = f"**{b_info['status']} • {b_name}** ({b_id}){up_alert}\n{log_label}: `{b_info['log_size']}`\n`{get_feedback(i18n, 'path')}: {b_info['path']}`"
                
                self.add_item(TextDisplay(bot_text))
                
                bot_row = ActionRow()
                bot_row.add_item(BotControlButton(emoji=restart_emoji, bot_id=b_id, bot_name=b_name, action="restart", view=parent_view))
                bot_row.add_item(BotControlButton(emoji=update_emoji, bot_id=b_id, bot_name=b_name, action="update", view=parent_view))
                bot_row.add_item(BotControlButton(emoji=stop_emoji, bot_id=b_id, bot_name=b_name, action="stop", view=parent_view))
                
                self.add_item(bot_row)
                
                # Only add separator if NOT the last bot
                if i < len(bot_list) - 1:
                    self.add_item(Separator())
        else:
            self.add_item(TextDisplay(f"*{i18n.get('error_no_bots_configured', 'No bots configured.')}*"))

class ModernInfoView(LayoutView):
    """A premium, modern intro view for FixItFixa using Components V2 layout."""
    def __init__(self, bot, i18n, guild):
        ui = getattr(bot, 'ui_settings', {})
        accent = ui.get("accent_color", 0x2b2d31)
        super().__init__(timeout=None)
        
        container = Container(accent_color=accent)
        
        # Header with bot name and avatar
        container.add_item(Section(
            f"# {get_feedback(i18n, 'INFO_TITLE', bot_name=bot.manager_name)}",
            accessory=Thumbnail(bot.user.display_avatar.url)
        ))
        
        container.add_item(Separator())
        
        # Description
        container.add_item(TextDisplay(get_feedback(i18n, "INFO_DESC", bot_name=bot.manager_name)))
        
        container.add_item(Separator())
        
        # Features
        container.add_item(TextDisplay(
            f"**{get_feedback(i18n, 'INFO_FEATURES_TITLE')}**\n" + 
            get_feedback(i18n, "INFO_FEATURES_DESC")
        ))
        
        container.add_item(Separator())
        
        # Footer
        container.add_item(TextDisplay(f"*{get_feedback(i18n, 'INFO_FOOTER')}*"))
        
        self.add_item(container)

class ModernStatusView(LayoutView):
    """A premium, modern status view for managed bots using Components V2 layout."""
    def __init__(self, bot_manager, i18n, manager_stats, bots_stats):
        ui = getattr(bot_manager, 'ui_settings', {})
        timeout = ui.get("view_timeout", 300)
        # If timeout is 0 or None in config, or explicitly passed as None, we disable it
        super().__init__(timeout=timeout if timeout else None)
        self.bot_manager = bot_manager
        self.i18n = i18n
        
        # Build layout using a Container
        container = StatusContainer(bot_manager, i18n, manager_stats, bots_stats, self)
        self.add_item(container)

class UpdateResultEmbed(discord.Embed):
    """A premium, modern embed for displaying update results."""
    def __init__(self, i18n, title, details, ui_settings=None, is_rollback=False):
        color_val = 0x2ecc71 # Green default
        if is_rollback:
            color_val = 0xe67e22 # Orange default
            
        if ui_settings:
            if is_rollback:
                color_val = ui_settings.get("update_rollback_color", color_val)
            else:
                color_val = ui_settings.get("update_success_color", color_val)

        super().__init__(
            title=title,
            description=f"**{details['message']}**" if details else get_feedback(i18n, "update_success"),
            color=discord.Color(color_val),
            timestamp=discord.utils.utcnow()
        )
        
        if details:
            self.add_field(name=get_feedback(i18n, "hash"), value=f"`{details['hash']}`", inline=True)
            self.add_field(name=get_feedback(i18n, "date"), value=f"<t:{details['date']}:R>", inline=True)
            
            if details.get("pip_status"):
                self.add_field(name=get_feedback(i18n, "pip_deps"), value=f"`{details['pip_status']}`", inline=False)
            
            if details.get("repo_url"):
                label = get_feedback(i18n, "open_on_web")
                self.add_field(name=get_feedback(i18n, "git_repo"), value=f"[{label}]({details['repo_url']})", inline=False)
            
        self.set_footer(text=get_feedback(i18n, "update_footer"))
