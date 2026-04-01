import discord
from discord.ui import LayoutView, ActionRow, Container, TextDisplay, Separator
import sys
import asyncio
from core.logger import log

from core.icons import Icons

class BotControlButton(discord.ui.Button):
    def __init__(self, style=discord.ButtonStyle.secondary, emoji=None, bot_id=None, bot_name=None, action=None, view=None):
        # Debug: log the emoji object
        log.info(f"[UI] Creating button for {bot_id}:{action} with emoji: {emoji} (Type: {type(emoji)})")
        # Custom IDs for state persistence and clean emoji-only buttons
        cid = f"status:{bot_id}:{action}"
        super().__init__(style=style, label=None, emoji=emoji, custom_id=cid)
        self.bot_id = bot_id
        self.bot_name = bot_name
        self.action = action # 'restart', 'stop', 'update'
        self.parent_view = view

    async def callback(self, interaction: discord.Interaction):
        # 1. Permission and context check (Buttons should be Admin-only)
        bot = interaction.client
        i18n = self.parent_view.i18n
        
        # Administrator permission OR specific role check
        is_admin_perm = interaction.user.guild_permissions.administrator
        admin_role_id = getattr(bot, 'admin_role_id', None)
        has_admin_role = any(str(role.id) == str(admin_role_id) for role in interaction.user.roles) if admin_role_id else False
        
        if not (is_admin_perm or has_admin_role):
            await interaction.response.send_message(i18n.get("error_admin_only", "❌ Administrator permissions or specific admin role required."), ephemeral=True)
            return
            
        # Context (Guild/Channel) check
        guild_id = getattr(bot, 'guild_id', None)
        admin_channel_id = getattr(bot, 'admin_channel_id', None)
        
        if guild_id and str(interaction.guild_id) != str(guild_id):
            await interaction.response.send_message(i18n.get("error_invalid_guild", "❌ Invalid Server"), ephemeral=True)
            return
        if admin_channel_id and str(interaction.channel_id) != str(admin_channel_id):
            await interaction.response.send_message(i18n.get("error_admin_channel_only", "❌ This can only be used in the admin channel."), ephemeral=True)
            return
            
        await interaction.response.defer(ephemeral=False)
        
        service = self.parent_view.bot_manager.management_service
        result = ""
        
        # SPECIAL HANDLING FOR MANAGER SELF-CONTROLS
        if self.bot_id == "manager":
            if self.action == "restart":
                log.info(f"User {interaction.user} clicked SELF-RESTART for Manager")
                service.prepare_manager_restart()
                await interaction.followup.send(self.parent_view.i18n.get("status_restarting", "Manager restarting..."), ephemeral=False)
                await asyncio.sleep(2)
                os.execv(sys.executable, [sys.executable] + sys.argv)

                return
            elif self.action == "stop":
                log.info(f"User {interaction.user} clicked SELF-STOP for Manager")
                await interaction.followup.send(self.parent_view.i18n.get("status_stopping", "Manager shutting down..."), ephemeral=False)
                await asyncio.sleep(1)
                sys.exit(0)
                return
            elif self.action == "update":
                log.info(f"User {interaction.user} clicked SELF-UPDATE for Manager")
                
                # Immediate feedback
                updating_msg = self.parent_view.i18n.get("manager_updating", "🔄 Manager update in progress...", name="Manager")
                await interaction.followup.send(updating_msg, ephemeral=False)
                
                success, output, changed, details = await service.run_manager_update()

                if not success:
                    msg = i18n.get("error_update_failed_output", "❌ Update failed:\n{output}", output=output)
                    await interaction.followup.send(msg, ephemeral=False)
                    return
                if not changed:
                    await interaction.followup.send(self.parent_view.i18n.get("update_no_changes", "No updates found."), ephemeral=False)
                    return
                # If changed and success, trigger restart
                service.prepare_manager_restart()
                msg = self.parent_view.i18n.get("manager_update_success", "Manager updated. Restarting...", name="Manager", output=output)
                await interaction.followup.send(msg, ephemeral=False)
                await asyncio.sleep(2)
                os.execv(sys.executable, [sys.executable] + sys.argv)

                return

        # STANDARD BOT CONTROLS
        if self.action == "restart":
            log.info(f"User {interaction.user} clicked RESTART for {self.bot_name} ({self.bot_id})")
            result = await service.run_restart(self.bot_id)
        elif self.action == "stop":
            log.info(f"User {interaction.user} clicked STOP for {self.bot_name} ({self.bot_id})")
            await service.process_manager.stop_process(self.bot_id)
            result = self.parent_view.i18n.get("status_stopped", "Stopped")
        elif self.action == "update":
            log.info(f"User {interaction.user} clicked UPDATE for {self.bot_name} ({self.bot_id})")
            result_msg, details = await service.run_update(self.bot_id)
            
            if details:
                from core.views import UpdateResultEmbed
                title = self.parent_view.i18n.get("update_result_title", "✅ {name} updated", name=self.bot_name)
                embed = UpdateResultEmbed(self.parent_view.i18n, title, details)
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
        cpu_label = i18n.get("cpu", "CPU")
        ram_label = i18n.get("ram", "RAM")
        host_label = i18n.get("host_os", "Host OS")
        free_label = i18n.get("system_free", "Free")
        disk_label = i18n.get("disk", "Disk")
        swap_label = i18n.get("swap", "Swap")
        server_up_label = i18n.get("server_uptime", "Server")
        log_label = i18n.get("log_size", "Log")
        update_available_msg = i18n.get("update_available", "UPDATE AVAILABLE")
        
        manager_up_alert = f" ⚠️ **{update_available_msg}**" if manager_stats.get("has_update") else ""
        
        manager_text = (
            f"**{bot_manager.manager_name}**{manager_up_alert}\n"
            f"**{i18n.get('status_running', 'Running')}**\n"
            f"> {i18n.get('uptime', 'Uptime')}: {manager_stats['uptime']} | {server_up_label}: {manager_stats['host_uptime']}\n"
            f"> {i18n.get('branch', 'Branch')}: `{manager_stats['branch']}`\n"
            f"> {host_label}: `{manager_stats['os']}`\n"
            f"> {i18n.get('resources', 'Resources')}: {cpu_label}: `{manager_stats['cpu']}%` | {ram_label}: `{int(manager_stats['ram'])} MB` | Net: `{manager_stats['net']}`\n"
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
            self.add_item(TextDisplay(f"**{i18n.get('bots_status_header', 'Managed Bots')}**"))
            
            # We keep track of the indexed for separator logic
            bot_list = list(bots_stats.items())
            for i, (b_id, b_info) in enumerate(bot_list):
                b_name = b_info["name"]
                up_alert = f" ⚠️ **{update_available_msg}**" if b_info.get("has_update") else ""
                
                if b_info["is_running"]:
                    status_emoji = "🟢"
                    up_label = i18n.get("uptime_short", "Up")
                    details = f"{cpu_label}: `{b_info['cpu']}%` | {ram_label}: `{int(b_info['ram'])} MB` | {up_label}: {b_info['uptime']} | {log_label}: `{b_info['log_size']}`"
                    bot_text = f"**{status_emoji} {b_name}** ({b_id}){up_alert}\n{details}\n`{i18n.get('path', 'Path')}: {b_info['path']}`"
                else:
                    # If not running, b_info['status'] already contains the red dot
                    bot_text = f"**{b_name}** ({b_id}){up_alert}\n*{b_info['status']}* | {log_label}: `{b_info['log_size']}`\n`{i18n.get('path', 'Path')}: {b_info['path']}`"
                
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
            description=f"**{details['message']}**" if details else i18n.get("update_success", "Update successful."),
            color=discord.Color(color_val),
            timestamp=discord.utils.utcnow()
        )
        
        if details:
            self.add_field(name=i18n.get("hash", "Hash"), value=f"`{details['hash']}`", inline=True)
            self.add_field(name=i18n.get("date", "Date"), value=f"<t:{details['date']}:R>", inline=True)
            
            if details.get("pip_status"):
                self.add_field(name=i18n.get("pip_deps", "Pip Dependencies"), value=f"`{details['pip_status']}`", inline=False)
            
            if details.get("repo_url"):
                label = i18n.get("open_on_web", "Open on Web")
                self.add_field(name=i18n.get("git_repo", "Repository"), value=f"[{label}]({details['repo_url']})", inline=False)
            
        self.set_footer(text=i18n.get("update_footer", "Code status updated"))
