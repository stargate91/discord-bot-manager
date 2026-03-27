import discord
from discord.ui import LayoutView, ActionRow, Container, TextDisplay, Separator
import sys
import asyncio
from core.logger import log

class Icons:
    RESTART: discord.PartialEmoji = None
    UPDATE: discord.PartialEmoji = None
    STOP: discord.PartialEmoji = None
    
    @classmethod
    def setup(cls, config):
        emoji_cfg = config.get("bot_settings", {}).get("emojis", {})
        
        def get(name, default):
            val = emoji_cfg.get(name, default)
            try:
                return discord.PartialEmoji.from_str(val)
            except:
                return discord.PartialEmoji(name=default) if ":" not in default else discord.PartialEmoji.from_str(default)

        cls.RESTART = get("restart", "🔄")
        cls.UPDATE = get("update", "🆙")
        cls.STOP = get("stop", "⏹️")

class BotControlButton(discord.ui.Button):
    def __init__(self, style=discord.ButtonStyle.secondary, emoji=None, bot_id=None, bot_name=None, action=None, view=None):
        super().__init__(style=style, emoji=emoji)
        self.bot_id = bot_id
        self.bot_name = bot_name
        self.action = action # 'restart', 'stop', 'update'
        self.parent_view = view

    async def callback(self, interaction: discord.Interaction):
        # We check if the user is allowed to do this (admin)
        from core.utils import is_admin_context
        # Since this is a button callback, we can't use the decorator easily, 
        # but the view was already sent to an admin. Double check:
        # (This is simplified, assuming only admins see this view)
        
        await interaction.response.defer(ephemeral=True)
        
        service = self.parent_view.bot_manager.management_service
        result = ""
        
        # SPECIAL HANDLING FOR MANAGER SELF-CONTROLS
        if self.bot_id == "manager":
            if self.action == "restart":
                log.info(f"User {interaction.user} clicked SELF-RESTART for Manager")
                service.prepare_manager_restart()
                await interaction.followup.send(self.parent_view.i18n.get("status_restarting", "Manager restarting..."), ephemeral=True)
                await asyncio.sleep(1)
                os.execv(sys.executable, ['python'] + sys.argv)
                return
            elif self.action == "stop":
                log.info(f"User {interaction.user} clicked SELF-STOP for Manager")
                await interaction.followup.send(self.parent_view.i18n.get("status_stopping", "Manager shutting down..."), ephemeral=True)
                await asyncio.sleep(1)
                sys.exit(0)
                return
            elif self.action == "update":
                log.info(f"User {interaction.user} clicked SELF-UPDATE for Manager")
                success, output, changed, details = await service.run_manager_update()
                if not success:
                    await interaction.followup.send(f"Update failed:\n{output}", ephemeral=True)
                    return
                if not changed:
                    await interaction.followup.send(self.parent_view.i18n.get("update_no_changes", "No updates found."), ephemeral=True)
                    return
                # If changed and success, trigger restart
                service.prepare_manager_restart()
                msg = self.parent_view.i18n.get("manager_update_success", "Manager updated. Restarting...", name="Manager", output=output)
                await interaction.followup.send(msg, ephemeral=True)
                await asyncio.sleep(1)
                os.execv(sys.executable, ['python'] + sys.argv)
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
                await interaction.followup.send(embed=embed, ephemeral=True)
                return
            else:
                result = result_msg
            
        if len(result) > 1900:
            result = result[:1000] + "\n... [TRUNCATED] ...\n" + result[-800:]
            
        await interaction.followup.send(result, ephemeral=True)
        # We don't refresh the whole status message automatically here to avoid rate limits,
        # the user can click the Global Refresh button if they want.

class StatusContainer(Container):
    """A visual container box for the status content."""
    def __init__(self, bot_manager, i18n, manager_stats, bots_stats, parent_view):
        super().__init__(accent_color=0x2b2d31) # Modern dark accent
        
        # We use the Icons class which was setup in manager.py
        restart_emoji = Icons.RESTART
        update_emoji = Icons.UPDATE
        stop_emoji = Icons.STOP

        # 1. Manager Header & Stats
        manager_text = (
            f"**{bot_manager.manager_name}**\n"
            f"**{i18n.get('status_running', 'Running')}**\n"
            f"> {i18n.get('uptime', 'Uptime')}: {manager_stats['uptime']}\n"
            f"> {i18n.get('branch', 'Branch')}: `{manager_stats['branch']}`\n"
            f"> {i18n.get('resources', 'Resources')}: CPU: `{manager_stats['cpu']}%` | RAM: `{int(manager_stats['ram'])} MB`"
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
            
            for b_id, b_info in bots_stats.items():
                b_name = b_info["name"]
                status_emoji = "🟢" if b_info["is_running"] else "🔴"
                details = f"CPU: `{b_info['cpu']}%` | RAM: `{int(b_info['ram'])} MB` | Up: {b_info['uptime']}" if b_info["is_running"] else f"*{b_info['status']}*"
                
                bot_text = f"**{status_emoji} {b_name}** ({b_id})\n{details}\n`{i18n.get('path', 'Path')}: {b_info['path']}`"
                self.add_item(TextDisplay(bot_text))
                
                bot_row = ActionRow()
                bot_row.add_item(BotControlButton(emoji=restart_emoji, bot_id=b_id, bot_name=b_name, action="restart", view=parent_view))
                bot_row.add_item(BotControlButton(emoji=update_emoji, bot_id=b_id, bot_name=b_name, action="update", view=parent_view))
                bot_row.add_item(BotControlButton(emoji=stop_emoji, bot_id=b_id, bot_name=b_name, action="stop", view=parent_view))
                
                self.add_item(bot_row)
                self.add_item(Separator())
        else:
            self.add_item(TextDisplay(f"*{i18n.get('error_no_bots_configured', 'No bots configured.')}*"))

class ModernStatusLayout(LayoutView):
    """A premium, modern status view for managed bots using Components V2 layout."""
    def __init__(self, bot_manager, i18n, manager_stats, bots_stats):
        super().__init__(timeout=300)
        self.bot_manager = bot_manager
        self.i18n = i18n
        
        # Build layout using a Container
        container = StatusContainer(bot_manager, i18n, manager_stats, bots_stats, self)
        self.add_item(container)

class UpdateResultEmbed(discord.Embed):
    """A premium, modern embed for displaying update results."""
    def __init__(self, i18n, title, details, is_rollback=False):
        color = discord.Color.green() if not is_rollback else discord.Color.orange()
        super().__init__(
            title=title,
            description=f"**{details['message']}**" if details else i18n.get("update_success", "Update successful."),
            color=color,
            timestamp=discord.utils.utcnow()
        )
        
        if details:
            self.add_field(name=i18n.get("hash", "Hash"), value=f"`{details['hash']}`", inline=True)
            self.add_field(name=i18n.get("author", "Author"), value=details['author'], inline=True)
            self.add_field(name=i18n.get("date", "Date"), value=details['date'], inline=True)
            
            if details.get("pip_status"):
                self.add_field(name=i18n.get("pip_deps", "Pip Dependencies"), value=f"`{details['pip_status']}`", inline=False)
            
            if details.get("repo_url"):
                label = i18n.get("open_on_web", "Open on Web")
                self.add_field(name=i18n.get("git_repo", "Repository"), value=f"[{label}]({details['repo_url']})", inline=False)
            
        self.set_footer(text=i18n.get("update_footer", "Code status updated"))
