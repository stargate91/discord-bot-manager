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
            log.warning(f"Slash Check Failed: Wrong Guild (Expected {guild_id}, got {interaction.guild_id})")
            return False
        # Check if we are in the right channel (the admin channel)
        if admin_channel_id and str(interaction.channel_id) != str(admin_channel_id):
            log.warning(f"Slash Check Failed: Wrong Channel (Expected {admin_channel_id}, got {interaction.channel_id})")
            return False
            
        # Check if the user is an administrator OR has the specific admin role
        is_admin_perm = interaction.user.guild_permissions.administrator
        admin_role_id = getattr(bot, 'admin_role_id', None)
        
        has_admin_role = False
        if admin_role_id and hasattr(interaction.user, 'roles'):
            has_admin_role = any(str(role.id) == str(admin_role_id) for role in interaction.user.roles)
            
        if not (is_admin_perm or has_admin_role):
            log.warning(f"Slash Check Failed: No Permission for user {interaction.user} (Role ID: {admin_role_id})")
            return False
            
        # If everything is correct, we return True
        return True
    return app_commands.check(predicate)

def is_admin_prefix_context():
    """Check for prefix commands (Context instead of Interaction)."""
    async def predicate(ctx: commands.Context) -> bool:
        bot = ctx.bot
        guild_id = getattr(bot, 'guild_id', None)
        admin_channel_id = getattr(bot, 'admin_channel_id', None)

        if guild_id and str(ctx.guild.id) != str(guild_id):
            log.warning(f"Prefix Check Failed: Wrong Guild (Expected {guild_id}, got {ctx.guild.id})")
            return False
        if admin_channel_id and str(ctx.channel.id) != str(admin_channel_id):
            log.warning(f"Prefix Check Failed: Wrong Channel (Expected {admin_channel_id}, got {ctx.channel.id})")
            return False
            
        is_admin_perm = ctx.author.guild_permissions.administrator
        admin_role_id = getattr(bot, 'admin_role_id', None)
        has_admin_role = any(str(role.id) == str(admin_role_id) for role in ctx.author.roles) if admin_role_id else False
        
        if not (is_admin_perm or has_admin_role):
            log.warning(f"Prefix Check Failed: No Permission for user {ctx.author} (Role ID: {admin_role_id})")
            return False

        return True
        
    return commands.check(predicate)
