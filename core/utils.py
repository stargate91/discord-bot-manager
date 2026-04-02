import discord
from discord import app_commands
from discord.ext import commands
import os
from core.icons import Icons

def get_feedback(i18n, key: str, **kwargs) -> str:
    """
    Returns a translated string prefixed with the appropriate emoji.
    Compatible with the Watcher Bot system.
    """
    # Mapping keys to Icons (consistent with Watcher Bot logic)
    icons_map = {
        # --- Errors (❌) : Critical / Blocking failures ---
        "error_generic": Icons.ERROR,
        "error_git_update_failed": Icons.ERROR,
        "error_update_failed_output": Icons.ERROR,
        "error_update_general": Icons.ERROR,
        "error_no_token": Icons.ERROR,
        "error_rollback": Icons.ERROR,
        "error_log_fetch": Icons.ERROR,
        "error_log_not_found": Icons.ERROR,
        "error_manager_log_not_found": Icons.ERROR,
        "pip_error": Icons.ERROR,
        "purge_error": Icons.ERROR,
        "status_failed": Icons.ERROR,
        "status_error_prefix": Icons.ERROR,
        "status_error": Icons.ERROR,

        # --- Warnings (⚠️) : Non-blocking/User input errors ---
        "warning_generic": Icons.WARNING,
        "update_available": Icons.WARNING,
        "error_no_requirements": Icons.WARNING,
        "error_no_bots_configured": Icons.WARNING,
        "error_log_empty": Icons.WARNING,
        "error_manager_log_empty": Icons.WARNING,
        "error_id_not_found": Icons.WARNING,
        "error_unknown_bot": Icons.WARNING,
        "update_no_changes": Icons.WARNING,
        "status_refreshed": Icons.WARNING, # Notification of refresh

        # --- Alerts (🚨) : Urgent state changes ---
        "bot_stopped_alert": Icons.ALERT,
        "status_uncertain": Icons.ALERT,

        # --- Success (✅) : Positive feedback ---
        "success_generic": Icons.SUCCESS,
        "update_success": Icons.SUCCESS,
        "restart_success": Icons.SUCCESS,
        "status_ok": Icons.SUCCESS,
        "sync_success_global": Icons.SUCCESS,
        "sync_success_copy": Icons.SUCCESS,
        "sync_success_guild": Icons.SUCCESS,
        "clear_commands_success": Icons.SUCCESS,
        "purge_success": Icons.SUCCESS,
        "manager_update_success": Icons.SUCCESS,
        "update_result_title": Icons.SUCCESS,
        "manager_updated_title": Icons.SUCCESS,
        "bot_updated_title": Icons.SUCCESS,

        # --- Administrative (🛡️) : Permissions / Protection ---
        "error_admin_only": Icons.SHIELD,
        "error_admin_context": Icons.SHIELD,
        "error_admin_channel_only": Icons.SHIELD,
        "manager_online_log": Icons.SHIELD,
        "activity_status": Icons.SHIELD,

        # --- Functional Icons (Buttons / System) ---
        "RESTART": Icons.RESTART,
        "UPDATE": Icons.UPDATE,
        "STOP": Icons.STOP,
        "UP": Icons.UP,
        "DOWN": Icons.DOWN,
        "CHART": Icons.CHART,
        "ROCKET": Icons.ROCKET,
        "CONTROLLER": Icons.CONTROLLER,
        "LOG": Icons.LOG,
        "PACKAGE": Icons.PACKAGE,
        "WRENCH": Icons.WRENCH,
        "GEAR": Icons.GEAR,
        "WAVE": Icons.WAVE,
        "ACTIVITY_UP": Icons.ACTIVITY_UP,
        "ACTIVITY_DOWN": Icons.ACTIVITY_DOWN,
        "DOT_GREEN": Icons.DOT_GREEN,
        "DOT_RED": Icons.DOT_RED,
        "DOT_YELLOW": Icons.DOT_YELLOW,

        # --- UI Labels & Mappings ---
        "logs_header": Icons.LOG,
        "logs_full_header": Icons.LOG,
        "manager_logs_header": Icons.LOG,
        "manager_logs_full_header": Icons.LOG,
        "manager_restart_msg": Icons.RESTART,
        "manager_updating": Icons.UPDATE,
        "pip_updated": Icons.PACKAGE,
        "pip_deps": Icons.PACKAGE,
        "bot_restarted_log": Icons.ROCKET,
        "bot_online_log": Icons.ROCKET,
        "bot_rollback_title": Icons.ROLLBACK,
        "status_restarting": Icons.RESTART,
        "status_stopping": Icons.STOP,
        "status_running": Icons.DOT_GREEN,
        "status_running_systemd": Icons.DOT_GREEN,
        "status_stopped": Icons.DOT_RED,
        "activity_text": Icons.CONTROLLER,
        "activity_maintenance": Icons.WRENCH,
        "activity_resource": Icons.GEAR,
        "activity_network": Icons.WAVE,
    }
    
    # Key normalization: try exact match first, then lowercase match
    emoji = icons_map.get(key)
    if not emoji:
        emoji = icons_map.get(key.lower(), "")
    
    # Fallback heuristic: match by keyword if no direct map
    if not emoji:
        lower_key = key.lower()
        if "error" in lower_key: emoji = Icons.ERROR
        elif "success" in lower_key: emoji = Icons.SUCCESS
        elif "warning" in lower_key: emoji = Icons.WARNING
    
    # Inject all icons into kwargs so they can be used as placeholders like {WRENCH} or {UP}
    for attr in dir(Icons):
        if not attr.startswith("__") and not callable(getattr(Icons, attr)):
            icon_val = getattr(Icons, attr)
            if icon_val is not None:
                # We use setdefault so we don't override manual kwargs if they exist
                kwargs.setdefault(attr, str(icon_val))
    
    text = i18n.get(key, **kwargs)
    
    # If emoji is None (failed load), use empty string
    emoji_str = str(emoji) if emoji is not None else ""
    
    # If the text already contains the emoji (manual placeholder in JSON), don't double it
    if emoji_str and emoji_str in text:
        return text
        
    if not text:
        return emoji_str.strip()
        
    return f"{emoji_str} {text}".strip()

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

def is_monitor_context():
    """This function only checks if we are in the right guild/channel, ANYONE in that channel can run it."""
    def predicate(interaction: discord.Interaction) -> bool:
        bot = interaction.client
        guild_id = getattr(bot, 'guild_id', None)
        admin_channel_id = getattr(bot, 'admin_channel_id', None)

        if guild_id and str(interaction.guild_id) != str(guild_id):
            return False
        if admin_channel_id and str(interaction.channel_id) != str(admin_channel_id):
            return False
            
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

def is_monitor_prefix_context():
    """Check for prefix commands (Channel only, no admin role required)."""
    async def predicate(ctx: commands.Context) -> bool:
        bot = ctx.bot
        guild_id = getattr(bot, 'guild_id', None)
        admin_channel_id = getattr(bot, 'admin_channel_id', None)

        if guild_id and str(ctx.guild.id) != str(guild_id):
            return False
        if admin_channel_id and str(ctx.channel.id) != str(admin_channel_id):
            return False
            
        return True
    return commands.check(predicate)
