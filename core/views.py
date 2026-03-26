import discord
from discord.ui import LayoutView, Container, Section, TextDisplay, Thumbnail, Separator, ActionRow, Button

class ModernStatusView(discord.ui.LayoutView):
    """A premium, modern status view for managed bots."""
    def __init__(self, bot_manager, i18n, manager_stats, bots_stats):
        super().__init__()
        self.bot_manager = bot_manager
        self.i18n = i18n
        self.setup_layout(manager_stats, bots_stats)

    def setup_layout(self, manager_stats, bots_stats):
        container = discord.ui.Container(accent_color=discord.Color.blue()) # Manager primary color
        
        # 1. Manager Header
        m_name = self.bot_manager.manager_name
        m_status = self.i18n.get("status_running", "Running")
        m_uptime = manager_stats["uptime"]
        
        m_header = self.i18n.get("manager_status_layout", "# {name}\n{status} • {uptime}", name=m_name, status=m_status, uptime=m_uptime)
        container.add_item(discord.ui.Section(
            m_header,
            accessory=discord.ui.Thumbnail(self.bot_manager.user.display_avatar.url)
        ))
        
        container.add_item(discord.ui.Separator())
        
        # 2. Manager Stats
        m_stats_text = self.i18n.get("manager_resource_usage", "CPU: **{cpu}%** • RAM: **{ram} MB**", cpu=manager_stats['cpu'], ram=manager_stats['ram'])
        container.add_item(discord.ui.TextDisplay(m_stats_text))
        
        container.add_item(discord.ui.Separator())
        
        # 3. Managed Bots Header
        # We use the header directly from i18n since it already contains '###'
        bots_header = self.i18n.get('bots_status_header', '### Managed Bots')
        container.add_item(discord.ui.TextDisplay(bots_header))
        
        if not bots_stats:
            container.add_item(discord.ui.TextDisplay(f"* {self.i18n.get('error_no_bots_configured', 'No bots configured.')}*"))
        else:
            for b_id, b_info in bots_stats.items():
                b_name = b_info["name"]
                b_status = b_info["status"]
                
                # Header for each bot
                b_header = self.i18n.get("bot_header_layout", "**{name}** ({id})", name=b_name, id=b_id)
                
                # Status and resource details
                if b_info["is_running"]:
                    b_details = self.i18n.get("bot_status_running_layout", "{status} • {uptime}", 
                        status=b_status, uptime=b_info['uptime'], pid=b_info['pid'], cpu=b_info['cpu'], ram=b_info['ram'])
                else:
                    b_details = f"*{b_status}*"
                
                container.add_item(discord.ui.TextDisplay(f"{b_header}\n{b_details}"))
                
                # Path info with a simple bullet
                b_path_text = self.i18n.get("bot_path_layout", "╰ Path: `{path}`", path=b_info['path'])
                container.add_item(discord.ui.TextDisplay(b_path_text))
                
                # Add a separator between bots, except the last one
                container.add_item(discord.ui.Separator())

        self.add_item(container)
