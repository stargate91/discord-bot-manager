import discord
from discord import app_commands
import os

# This is a 'decorator' - it's a special function that checks something before running a command!
def is_admin_context():
    """This function checks if the user is allowed to use admin commands."""
    def predicate(interaction: discord.Interaction) -> bool:
        bot = interaction.client
        # We try to get the ID settings from the bot object
        guild_id = getattr(bot, 'guild_id', None)
        admin_channel_id = getattr(bot, 'admin_channel_id', None)

        # Check if we are on the right Discord server
        if guild_id and str(interaction.guild_id) != str(guild_id):
            return False
        # Check if we are in the right channel (the admin channel)
        if admin_channel_id and str(interaction.channel_id) != str(admin_channel_id):
            return False
            
        # Check if the user is an administrator
        if not interaction.user.guild_permissions.administrator:
            return False
            
        # If everything is correct, we return True
        return True
    return app_commands.check(predicate)
