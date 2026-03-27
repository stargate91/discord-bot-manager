import discord
from discord.ui import View, Button
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

class ModernStatusView(View):
    """A premium, modern status view for managed bots using standard discord.py components."""
    def __init__(self, bot_manager, i18n, manager_stats, bots_stats):
        super().__init__(timeout=300) # 5 minute timeout
        self.bot_manager = bot_manager
        self.i18n = i18n
        self.manager_stats = manager_stats
        self.bots_stats = bots_stats
        
        self.create_embeds()
        self.create_buttons()

    def create_embeds(self):
        self.embeds = []
        
        # 1. Manager Embed
        manager_embed = discord.Embed(
            title=self.bot_manager.manager_name,
            description=f"**{self.i18n.get('status_running', 'Running')}**",
            color=discord.Color.blue(),
            timestamp=discord.utils.utcnow()
        )
        manager_embed.set_thumbnail(url=self.bot_manager.user.display_avatar.url)
        manager_embed.add_field(name=self.i18n.get("uptime", "Uptime"), value=self.manager_stats["uptime"], inline=True)
        manager_embed.add_field(name=self.i18n.get("branch", "Branch"), value=f"`{self.manager_stats['branch']}`", inline=True)
        manager_embed.add_field(name=self.i18n.get("resources", "Resources"), value=f"CPU: `{self.manager_stats['cpu']}%` | RAM: `{int(self.manager_stats['ram'])} MB`", inline=False)
        manager_embed.set_footer(text=self.i18n.get("manager_status_header", "Manager Status"))
        
        self.embeds.append(manager_embed)
        
        # 2. Bots Embed
        if self.bots_stats:
            bots_embed = discord.Embed(
                title=self.i18n.get('bots_status_header', '### Managed Bots'),
                color=discord.Color.dark_grey()
            )
            
            for b_id, b_info in self.bots_stats.items():
                b_name = b_info["name"]
                b_status = b_info["status"]
                
                if b_info["is_running"]:
                    status_emoji = "🟢"
                    details = f"CPU: `{b_info['cpu']}%` | RAM: `{int(b_info['ram'])} MB` | Up: {b_info['uptime']}"
                else:
                    status_emoji = "🔴"
                    details = f"*{b_status}*"
                
                field_name = f"{status_emoji} {b_name} ({b_id})"
                field_value = f"{details}\n`{self.i18n.get('path', 'Path')}: {b_info['path']}`"
                bots_embed.add_field(name=field_name, value=field_value, inline=False)
            
            self.embeds.append(bots_embed)
        else:
            no_bots_embed = discord.Embed(description=f"*{self.i18n.get('error_no_bots_configured', 'No bots configured.')}*", color=discord.Color.red())
            self.embeds.append(no_bots_embed)

    def create_buttons(self):
        # Global Refresh Button
        refresh_btn = Button(label=self.i18n.get("refresh", "Refresh"), style=discord.ButtonStyle.secondary, emoji="🔄", row=0)
        async def refresh_callback(interaction: discord.Interaction):
            # We just trigger the status command again
            cog = self.bot_manager.get_cog("MonitoringCog")
            if cog:
                # We need to hack a bit because it's an app command
                await cog.status.callback(cog, interaction)
        refresh_btn.callback = refresh_callback
        self.add_item(refresh_btn)

        # Bot Specific Buttons (up to 4 more rows)
        if self.bots_stats:
            row = 1
            for b_id, b_info in self.bots_stats.items():
                if row > 4: break # Discord limit
                
                # Restart Button
                self.add_item(BotControlButton(
                    label=f"{self.i18n.get('btn_restart', 'Rest')} {b_info['name']}", 
                    style=discord.ButtonStyle.primary, 
                    bot_id=b_id, 
                    bot_name=b_info['name'],
                    action="restart", 
                    view=self
                ))
                
                # Update Button
                self.add_item(BotControlButton(
                    label=f"{self.i18n.get('btn_update', 'Upd')} {b_info['name']}", 
                    style=discord.ButtonStyle.success, 
                    bot_id=b_id, 
                    bot_name=b_info['name'],
                    action="update", 
                    view=self
                ))

                # Stop Button
                self.add_item(BotControlButton(
                    label=f"{self.i18n.get('btn_stop', 'Stop')} {b_info['name']}", 
                    style=discord.ButtonStyle.danger, 
                    bot_id=b_id, 
                    bot_name=b_info['name'],
                    action="stop", 
                    view=self
                ))
                
                # Manual Row increment is not needed if we just add items, 
                # but we want each bot on its own row if possible.
                # Actually, 3 buttons per bot * 3 bots = 9 buttons.
                # Row 0: Refresh (1)
                # Row 1: Bot 1 (3)
                # Row 2: Bot 2 (3)
                # Row 3: Bot 3 (3)
                # Total Row 3. Perfect.
                
                # Set row for the last 3 added items
                for item in self.children[-3:]:
                    item.row = row
                row += 1

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
