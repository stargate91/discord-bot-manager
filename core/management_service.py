import os
import sys
import asyncio
import json
from core.logger import log

class ManagementService:
    """This service handles high-level management tasks like updating and restarting bots."""
    def __init__(self, config, i18n, process_manager, git_service, bots, notify_admin_cb=None):
        self.config = config
        self.i18n = i18n
        self.process_manager = process_manager
        self.git_service = git_service
        self.bots = bots
        self.notify_admin_cb = notify_admin_cb
        
        # Load settings
        bot_settings = self.config.get("bot_settings", {})
        self.git_branch = bot_settings.get("git_branch", "origin/main")
        self.manager_name = bot_settings.get("default_manager_name", "Bot Manager")

    async def notify(self, msg):
        """Helper to send notifications back to the admin interface."""
        if self.notify_admin_cb:
            await self.notify_admin_cb(msg)

    async def run_restart(self, bot_id):
        """Restarts a bot and any related bots in the same directory."""
        if bot_id not in self.bots:
            return self.i18n.get("error_id_not_found", "Bot ID not found in config.")

        bot = self.bots[bot_id]
        related_bots = [b for b in self.bots.values() if b.path == bot.path]
        
        results = []
        for b in related_bots:
            try:
                # 1. Prepare environment
                bot_env = os.environ.copy()
                protected_vars = self.config.get("bot_settings", {}).get("protected_env_vars", ["DISCORD_TOKEN", "GUILD_ID", "ADMIN_CHANNEL_ID"])
                for key in protected_vars:
                    bot_env.pop(key, None)
                
                bot_env["MANAGED_LOGGING"] = "1"
                bot_env["INSTANCE_NAME"] = b.cmd.split()[-1]

                # 2. Restart process using unified logic
                new_pid = await self.process_manager.restart_process(b.id, b, bot_env)
                
                success_msg = self.i18n.get("restart_success", "Bot {name} restarted (PID: {pid})", name=b.name, pid=new_pid)
                results.append(success_msg)
                
                # Notify admin
                await self.notify(self.i18n.get("bot_online_log", "Bot {name} ({id}) is back online.", name=b.name, id=b.id))
            except Exception as e:
                error_msg = self.i18n.get("restart_error", "Error restarting {name}: {error}", name=b.name, error=str(e))
                results.append(error_msg)

        return "\n".join(results)

    async def run_update(self, bot_id):
        """Updates code via Git and then restarts the bots ONLY if changes were found."""
        if bot_id not in self.bots:
            return self.i18n.get("error_id_not_found", "Bot ID not found in config.")

        bot = self.bots[bot_id]
        related_bots = [b for b in self.bots.values() if b.path == bot.path]
        
        results = []
        try:
            # 1. Update via Git first (while bots are running)
            log.info(f"Updating code at: {bot.path}")
            up_success, up_msg, changed, details = await asyncio.to_thread(self.git_service.update_repo, bot.path, self.git_branch)
            results.append(up_msg)
            
            if not up_success:
                results.append(self.i18n.get("error_git_update_failed", "Git update failed."))
                return "\n".join(results), None

            if not changed:
                # No changes found, skip restart
                results.append(self.i18n.get("update_no_changes", "No updates found, restart skipped."))
                return "\n".join(results), None

            # 2. If changed, stop all related bots
            for b in related_bots:
                await self.process_manager.stop_process(b.id)

            # 3. Install dependencies
            pip_success, pip_msg = await asyncio.to_thread(self.git_service.install_dependencies, bot.path, bot.cmd)
            results.append(pip_msg)
            
            if details:
                ok_text = self.i18n.get("status_ok", "✅ OK")
                err_prefix = self.i18n.get("status_error_prefix", "⚠️ Error:")
                details["pip_status"] = ok_text if pip_success else f"{err_prefix} {pip_msg[:100]}"

            # 4. Restart all bots using unified logic
            for b in related_bots:
                bot_env = os.environ.copy()
                for key in ["DISCORD_TOKEN", "GUILD_ID", "ADMIN_CHANNEL_ID"]:
                    bot_env.pop(key, None)

                bot_env["MANAGED_LOGGING"] = "1"
                bot_env["INSTANCE_NAME"] = b.cmd.split()[-1]

                new_pid = await self.process_manager.restart_process(b.id, b, bot_env)
                restart_msg = self.i18n.get("restart_success", "Bot {name} restarted (PID: {pid})", name=b.name, pid=new_pid)
                results.append(restart_msg)
                await self.notify(self.i18n.get("bot_online_log", "Bot {name} ({id}) is back online.", name=b.name, id=b.id))
            
            return "\n".join(results), details
        except Exception as e:
            log.error(f"Update error: {e}")
            return self.i18n.get("error_update_general", "Error during update: {error}", error=str(e)), None

    async def run_rollback(self, bot_id):
        """Rolls back code via Git and restarts all related bots."""
        if bot_id not in self.bots:
            return self.i18n.get("error_unknown_bot", "Unknown Bot ID.")
            
        bot = self.bots[bot_id]
        related_bots = [b for b in self.bots.values() if b.path == bot.path]
        
        try:
            # 1. Rollback via GitService
            success, result_msg, changed, details = await asyncio.to_thread(self.git_service.rollback_repo, bot.path)
            if not success:
                return f"Error: {result_msg}", None

            # 2. Stop all related bots
            for b in related_bots:
                await self.process_manager.stop_process(b.id)

            results = [result_msg]
            # 3. Restart all related bots
            for b in related_bots:
                bot_env = os.environ.copy()
                for key in ["DISCORD_TOKEN", "GUILD_ID", "ADMIN_CHANNEL_ID"]:
                    bot_env.pop(key, None)

                bot_env["MANAGED_LOGGING"] = "1"
                bot_env["INSTANCE_NAME"] = b.cmd.split()[-1]

                new_pid = await self.process_manager.start_process(b.id, b, bot_env)
                restart_msg = self.i18n.get("restart_success", "Bot {name} restarted (PID: {pid})", name=b.name, pid=new_pid)
                results.append(restart_msg)
                await self.notify(self.i18n.get("bot_online_log", "Bot {name} ({id}) is back online.", name=b.name, id=b.id))
            
            return "\n".join(results), details
        except Exception as e:
            return self.i18n.get("error_rollback", "Error during rollback: {error}", error=str(e)), None

    async def run_manager_update(self):
        """Updates the Bot Manager itself."""
        manager_path = os.getcwd()
        results = []
        try:
            # 1. Update via Git
            up_success, up_msg, changed, details = await asyncio.to_thread(self.git_service.update_repo, manager_path, self.git_branch)
            results.append(up_msg)
            if not up_success:
                return False, "\n".join(results), False, None

            if not changed:
                return True, "\n".join(results), False, None

            # 2. Install dependencies
            pip_success, pip_msg = await asyncio.to_thread(self.git_service.install_dependencies, manager_path)
            results.append(pip_msg)
            
            if details:
                ok_text = self.i18n.get("status_ok", "✅ OK")
                err_prefix = self.i18n.get("status_error_prefix", "⚠️ Error:")
                details["pip_status"] = ok_text if pip_success else f"{err_prefix} {pip_msg[:100]}"
            
            return True, "\n".join(results), True, details
        except Exception as e:
            log.error(f"Manager update error: {e}")
            return False, str(e), False, None

    def prepare_manager_restart(self):
        """Saves the restart flag before the process exits."""
        temp_dir = self.config.get("bot_settings", {}).get("temp_dir", "tmp")
        os.makedirs(temp_dir, exist_ok=True)
        with open(os.path.join(temp_dir, "manager_restart.json"), "w") as f:
            json.dump({"restart": True}, f)
