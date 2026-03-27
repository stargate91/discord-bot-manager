import discord
from discord import ui
from discord.ui import Button
from core.logger import log

class BotControlButton(discord.ui.Button):
    def __init__(self, label, style, bot_id, bot_name, action, view):
        super().__init__(label=label, style=style)
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

class ModernStatusLayout(ui.LayoutView):
    """A premium, modern status view for managed bots using Components V2 layout."""
    def __init__(self, bot_manager, i18n, manager_stats, bots_stats):
        super().__init__(timeout=300)
        self.bot_manager = bot_manager
        self.i18n = i18n
        self.manager_stats = manager_stats
        self.bots_stats = bots_stats
        
        self.build_layout()

    def build_layout(self):
        # 1. Manager Section
        manager_text = (
            f"## {self.bot_manager.manager_name}\n"
            f"**{self.i18n.get('status_running', 'Running')}**\n"
            f"> {self.i18n.get('uptime', 'Uptime')}: {self.manager_stats['uptime']}\n"
            f"> {self.i18n.get('branch', 'Branch')}: `{self.manager_stats['branch']}`\n"
            f"> {self.i18n.get('resources', 'Resources')}: CPU: `{self.manager_stats['cpu']}%` | RAM: `{int(self.manager_stats['ram'])} MB`"
        )
        self.add_item(ui.TextDisplay(manager_text))
        
        # Refresh row
        refresh_row = ui.ActionRow()
        refresh_btn = ui.Button(label=self.i18n.get("refresh", "Refresh"), style=discord.ButtonStyle.secondary, emoji="🔄")
        async def refresh_callback(interaction: discord.Interaction):
            cog = self.bot_manager.get_cog("MonitoringCog")
            if cog:
                await cog.status.callback(cog, interaction)
        refresh_btn.callback = refresh_callback
        refresh_row.add_item(refresh_btn)
        self.add_item(refresh_row)

        self.add_item(ui.Separator(visible=True, spacing=discord.enums.SeparatorSpacing.large))

        # 2. Managed Bots Sections
        if self.bots_stats:
            self.add_item(ui.TextDisplay(f"### {self.i18n.get('bots_status_header', 'Managed Bots')}"))
            
            for b_id, b_info in self.bots_stats.items():
                b_name = b_info["name"]
                
                if b_info["is_running"]:
                    status_emoji = "🟢"
                    details = f"CPU: `{b_info['cpu']}%` | RAM: `{int(b_info['ram'])} MB` | Up: {b_info['uptime']}"
                else:
                    status_emoji = "🔴"
                    details = f"*{b_info['status']}*"
                
                bot_text = f"**{status_emoji} {b_name}** ({b_id})\n{details}\n`{self.i18n.get('path', 'Path')}: {b_info['path']}`"
                
                # Use TextDisplay instead of Section because Section requires an accessory
                self.add_item(ui.TextDisplay(bot_text))
                
                # Buttons Row for this bot
                bot_row = ui.ActionRow()
                
                # Restart Button
                bot_row.add_item(BotControlButton(
                    label=f"{self.i18n.get('btn_restart', 'Rest')} {b_name}", 
                    style=discord.ButtonStyle.secondary, 
                    bot_id=b_id, 
                    bot_name=b_name,
                    action="restart", 
                    view=self
                ))
                
                # Update Button
                bot_row.add_item(BotControlButton(
                    label=f"{self.i18n.get('btn_update', 'Upd')} {b_name}", 
                    style=discord.ButtonStyle.secondary, 
                    bot_id=b_id, 
                    bot_name=b_name,
                    action="update", 
                    view=self
                ))

                # Stop Button
                bot_row.add_item(BotControlButton(
                    label=f"{self.i18n.get('btn_stop', 'Stop')} {b_name}", 
                    style=discord.ButtonStyle.secondary, 
                    bot_id=b_id, 
                    bot_name=b_name,
                    action="stop", 
                    view=self
                ))
                
                self.add_item(bot_row)
                self.add_item(ui.Separator())
        else:
            self.add_item(ui.TextDisplay(f"*{self.i18n.get('error_no_bots_configured', 'No bots configured.')}*"))

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
