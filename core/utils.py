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
        # --- Common Status / Errors (Functional) ---
        "error_generic": Icons.ERROR,
        "error_admin_only": Icons.ERROR,
        "error_invalid_guild": Icons.ERROR,
        "error_admin_context": Icons.ERROR,
        "error_admin_channel_only": Icons.ERROR,
        "error_update_failed_output": Icons.ERROR,
        "error_git_update_failed": Icons.ERROR,
        "error_id_not_found": Icons.ERROR,
        "error_unknown_bot": Icons.ERROR,
        "error_update_general": Icons.ERROR,
        "error_rollback": Icons.ERROR,
        "error_log_fetch": Icons.ERROR,
        "error_log_not_found": Icons.ERROR,
        "error_manager_log_not_found": Icons.ERROR,
        "error_no_token": Icons.ERROR,
        "error_no_requirements": Icons.WARNING,
        "error_no_bots_configured": Icons.WARNING,
        "error_log_empty": Icons.HELP,
        "error_manager_log_empty": Icons.HELP,

        # --- Success / Positive ---
        "success_generic": Icons.SUCCESS,
        "update_success": Icons.SUCCESS,
        "restart_success": Icons.SUCCESS,
        "status_ok": Icons.SUCCESS,
        "sync_success_global": Icons.SUCCESS,
        "sync_success_copy": Icons.SUCCESS,
        "sync_success_guild": Icons.SUCCESS,
        "clear_commands_success": Icons.SUCCESS,
        "purge_success": Icons.SUCCESS,
        "purge_error": Icons.ERROR,
        "manager_status_header": "",
        "bots_status_header": "",

        # --- Network / System ---
        "UP": Icons.UP,
        "DOWN": Icons.DOWN,
        "manager_update_success": Icons.SUCCESS,
        "manager_restart_msg": Icons.LIGHTNING,
        "manager_updating": Icons.UPDATE,
        "update_result_title": Icons.SUCCESS,
        "manager_updated_title": Icons.SUCCESS,
        "bot_updated_title": Icons.SUCCESS,
        "bot_rollback_title": Icons.ROLLBACK,
        "status_refreshed": Icons.SUCCESS,
        "status_ok": Icons.SUCCESS,
        "status_error_prefix": Icons.ERROR,
        "status_stopping": Icons.WARNING,
        "status_running": Icons.DOT_GREEN,
        "status_running_systemd": Icons.DOT_GREEN,
        "status_uncertain": Icons.DOT_YELLOW,
        "status_stopped": Icons.DOT_RED,
        "status_failed": Icons.DOT_RED,
        "manager_status_header": "",
        "bots_status_header": "",
        "manager_status_line": "",
        "bot_status_line": "",
        
        # --- System & Resources ---
        "cpu": "",
        "ram": "",
        "host_os": "",
        "system_free": "",
        "disk": "",
        "swap": "",
        "server_uptime": "",
        "log_size": "",
        "resources": "",
        "path": "",
        "branch": "",
        "uptime": "",
        "uptime_short": "",
        "uptime_days": "",
        "uptime_hours": "",
        "uptime_minutes": "",
        "pip_deps": "",
        "git_repo": "",
        "hash": "",
        "author": "",
        "date": "",

        # --- Logs & Alerts ---
        "logs_header": Icons.LOG,
        "logs_full_header": Icons.LOG,
        "manager_logs_header": Icons.LOG,
        "manager_logs_full_header": Icons.LOG,
        "error_log_empty": Icons.WARNING,
        "error_manager_log_empty": Icons.WARNING,
        "error_log_fetch": Icons.ERROR,
        "error_log_not_found": Icons.ERROR,
        "error_manager_log_not_found": Icons.ERROR,
        "bot_restarted_log": "",
        "bot_online_log": "",
        "manager_online_log": "",
        "pip_updated": "",
        "pip_error": "",

        # --- Buttons & Actions ---
        "refresh": "",
        "btn_restart": "",
        "btn_update": "",
        "btn_stop": "",
        "open_on_web": "",
        "purge_confirm": "",

        # --- Errors ---
        "error_unknown_bot": Icons.ERROR,
        "error_id_not_found": Icons.ERROR,
        "error_admin_only": Icons.SHIELD,
        "error_invalid_guild": Icons.ERROR,
        "error_admin_channel_only": Icons.SHIELD,
        "error_no_token": Icons.ERROR,
        "error_no_bots_configured": Icons.WARNING,
        "error_admin_context": Icons.SHIELD,

        # --- Alerts / Warnings ---
        "warning_generic": Icons.WARNING,
        "bot_stopped_alert": Icons.ALERT,
        "update_available": Icons.WARNING,
        "update_no_changes": Icons.HELP,

        # --- Actions / Features ---
        "manager_status_header": Icons.CHART,
        "bots_status_header": Icons.CONTROLLER,
        "logs_header": Icons.LOG,
        "logs_full_header": Icons.LOG,
        "manager_logs_header": Icons.LOG,
        "manager_logs_full_header": Icons.LOG,
        "manager_restart_msg": Icons.RESTART,
        "manager_online_log": Icons.SHIELD,
        "manager_updating": Icons.UPDATE,
        "pip_updated": Icons.PACKAGE,
        "bot_restarted_log": Icons.ROCKET,
        "bot_online_log": Icons.ROCKET,
        "status_restarting": Icons.RESTART,
        "status_stopping": Icons.STOP,
        "activity_text": Icons.CONTROLLER,
        "activity_maintenance": Icons.WRENCH,
        "activity_resource": Icons.GEAR,
        "activity_network": Icons.WAVE,
        "activity_status": Icons.SHIELD,
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
