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

        # --- Success (🚀/✅) : Positive feedback ---
        "success_generic": Icons.SUCCESS,
        "update_success": Icons.ROCKET,
        "restart_success": Icons.ROCKET,
        "status_ok": Icons.SUCCESS,
        "sync_success_global": Icons.SUCCESS,
        "sync_success_copy": Icons.SUCCESS,
        "sync_success_guild": Icons.SUCCESS,
        "clear_commands_success": Icons.SUCCESS,
        "purge_success": Icons.SUCCESS,
        "manager_update_success": Icons.SUCCESS,
        # --- Headers & UI Labels ---
        "manager_status_header": "",
        "bots_status_header": "",
        "logs_header": Icons.LOG,
        "logs_full_header": Icons.LOG,
        "manager_logs_header": Icons.LOG,
        "manager_logs_full_header": Icons.LOG,
        "update_result_title": Icons.SUCCESS,
        "manager_updated_title": Icons.SUCCESS,
        "bot_updated_title": Icons.SUCCESS,
        "bot_rollback_title": Icons.ROLLBACK,
        "update_footer": Icons.SUCCESS,

        # --- Administrative (🛡️) : Permissions / Protection ---
        "error_admin_only": Icons.SHIELD_LIGHT,
        "error_admin_context": Icons.SHIELD_LIGHT,
        "error_admin_channel_only": Icons.SHIELD_LIGHT,
        "manager_online_log": Icons.SHIELD_LIGHT,
        "activity_status": Icons.SHIELD,

        # --- Functional Icons (Buttons / System) ---
        "RESTART": Icons.RESTART,
        "UPDATE": Icons.UPDATE,
        "STOP": Icons.STOP,
        "UP": Icons.UP,
        "DOWN": Icons.DOWN,
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

        # --- Bot & Manager States ---
        "manager_restart_msg": Icons.SHIELD_LIGHT,
        "manager_updating": Icons.UPDATE,
        "pip_updated": Icons.PACKAGE,
        "pip_deps": "",
        "bot_restarted_log": Icons.ROCKET,
        "bot_online_log": Icons.ROCKET,
        "status_restarting": Icons.RESTART,
        "status_stopping": Icons.STOP,
        "status_running": Icons.DOT_GREEN,
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
class AccessLevel:
    EVERYONE = 0
    INSPECTOR = 1 # Tester Role
    MECHANIC = 2 # Admin Role
    BOSS = 3     # Administrator Permission

def get_user_level(user, bot) -> int:
    """Determine the highest access level of a user."""
    # BOSS: Actual Discord Administrator
    if hasattr(user, 'guild_permissions') and user.guild_permissions.administrator:
        return AccessLevel.BOSS
        
    # Check roles for MECHANIC or INSPECTOR
    if hasattr(user, 'roles'):
        role_ids = [str(r.id) for r in user.roles]
        
        # Use getattr to be safe during migration/initialization
        admin_role_id = getattr(bot, 'admin_role_id', None)
        tester_role_id = getattr(bot, 'tester_role_id', None)
        
        # MECHANIC: Has the admin role
        if admin_role_id and str(admin_role_id) in role_ids:
            return AccessLevel.MECHANIC
            
        # INSPECTOR: Has the tester role
        if tester_role_id and str(tester_role_id) in role_ids:
            return AccessLevel.INSPECTOR
            
    return AccessLevel.EVERYONE

def is_in_valid_channel(interaction_or_ctx, bot, level: int) -> bool:
    """Check if the current channel is allowed for the given access level."""
    channel_id = str(interaction_or_ctx.channel_id if hasattr(interaction_or_ctx, 'channel_id') else interaction_or_ctx.channel.id)
    
    # Workshop (Admin Channel): BOSS and MECHANIC can do everything here
    if bot.admin_channel_id and channel_id == str(bot.admin_channel_id):
        return level >= AccessLevel.MECHANIC
        
    # Lounge (Public/Tester Channel): INSPECTOR and above can use it
    if bot.public_channel_id and channel_id == str(bot.public_channel_id):
        return level >= AccessLevel.INSPECTOR
        
    # Global: Only very basic things or BOSS everywhere
    return level == AccessLevel.BOSS

# Decorators
def is_admin_context():
    """Slash command decorator: Requires MECHANIC level in Workshop or BOSS anywhere."""
    def predicate(interaction: discord.Interaction) -> bool:
        bot = interaction.client
        level = get_user_level(interaction.user, bot)
        
        # Boss can do anything anywhere
        if level == AccessLevel.BOSS:
            return True
            
        # Mechanic can only do admin things in the Workshop
        if bot.admin_channel_id and str(interaction.channel_id) == str(bot.admin_channel_id):
            return level >= AccessLevel.MECHANIC
            
        return False
    return app_commands.check(predicate)

def is_monitor_context():
    """Slash command decorator: Allows INSPECTOR level in either Admin or Public channels."""
    def predicate(interaction: discord.Interaction) -> bool:
        bot = interaction.client
        level = get_user_level(interaction.user, bot)
        
        if level == AccessLevel.BOSS:
            return True
            
        channel_id = str(interaction.channel_id)
        if (bot.admin_channel_id and channel_id == str(bot.admin_channel_id)) or \
           (bot.public_channel_id and channel_id == str(bot.public_channel_id)):
            return level >= AccessLevel.INSPECTOR
            
        return False
    return app_commands.check(predicate)

def is_admin_prefix_context():
    """Prefix command decorator equivalent to is_admin_context."""
    async def predicate(ctx: commands.Context) -> bool:
        bot = ctx.bot
        level = get_user_level(ctx.author, bot)
        log.debug(f"[Prefix] Check for user {ctx.author} (Level: {level}) in channel {ctx.channel.id}")
        
        if level == AccessLevel.BOSS: return True
        
        if bot.admin_channel_id and str(ctx.channel.id) == str(bot.admin_channel_id):
            res = level >= AccessLevel.MECHANIC
            if not res: log.debug(f"[Prefix] Denied: Level {level} < MECHANIC in Admin channel.")
            return res
            
        log.debug(f"[Prefix] Denied: Invalid channel or level for Admin command.")
        return False
    return commands.check(predicate)

def is_monitor_prefix_context():
    """Prefix command decorator equivalent to is_monitor_context."""
    async def predicate(ctx: commands.Context) -> bool:
        bot = ctx.bot
        level = get_user_level(ctx.author, bot)
        log.debug(f"[Prefix-Mon] Check for user {ctx.author} (Level: {level}) in channel {ctx.channel.id}")
        
        if level == AccessLevel.BOSS: return True
        
        channel_id = str(ctx.channel.id)
        if (bot.admin_channel_id and channel_id == str(bot.admin_channel_id)) or \
           (bot.public_channel_id and channel_id == str(bot.public_channel_id)):
            res = level >= AccessLevel.INSPECTOR
            if not res: log.debug(f"[Prefix-Mon] Denied: Level {level} < INSPECTOR.")
            return res
            
        log.debug(f"[Prefix-Mon] Denied: Invalid channel.")
        return False
    return commands.check(predicate)
