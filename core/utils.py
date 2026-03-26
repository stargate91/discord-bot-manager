import discord
from discord import app_commands
import os

def is_admin_context():
    def predicate(interaction: discord.Interaction) -> bool:
        bot = interaction.client
        guild_id = getattr(bot, 'guild_id', None)
        admin_channel_id = getattr(bot, 'admin_channel_id', None)

        # Check Guild
        if guild_id and str(interaction.guild_id) != str(guild_id):
            return False
        # Check Channel
        if admin_channel_id and str(interaction.channel_id) != str(admin_channel_id):
            return False
        return True
    return app_commands.check(predicate)
