import discord
from discord import app_commands
import os

GUILD_ID = os.getenv("GUILD_ID")
ADMIN_CHANNEL_ID = os.getenv("ADMIN_CHANNEL_ID")

def is_admin_context():
    def predicate(interaction: discord.Interaction) -> bool:
        # Check Guild
        if GUILD_ID and str(interaction.guild_id) != str(GUILD_ID):
            return False
        # Check Channel
        if ADMIN_CHANNEL_ID and str(interaction.channel_id) != str(ADMIN_CHANNEL_ID):
            return False
        return True
    return app_commands.check(predicate)
