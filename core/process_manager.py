import os
import sys
import asyncio
import subprocess
import psutil
import datetime
from core.logger import log

# This class helps us manage all the other bot processes
class ProcessManager:
    def __init__(self, config, messages):
        # We store the settings and the translation messages here
        self.config = config
        self.messages = messages
        # This dictionary will keep track of which bots are running (ID -> Process)
        self.managed_processes = {} 
        # This set will remember which bots we stopped on purpose
        self.manual_stop = set() 
        
        # Get some settings from the configuration file
        bot_settings = self.config.get("bot_settings", {})
        # How many seconds to wait when stopping a bot
        self.stop_timeout = bot_settings.get("stop_timeout", 5)
        # How long to wait before starting it again
        self.restart_wait = bot_settings.get("restart_wait", 2.0)

    def discover_processes(self):
        """This function looks at all running programs on the computer to find our bots."""
        bots = self.config.get("bots", {})
        found_count = 0
        
        # We loop through every process that is currently running
        for proc in psutil.process_iter(['pid', 'name', 'cmdline', 'cwd']):
            try:
                cmdline = proc.info.get('cmdline')
                cwd = proc.info.get('cwd')
                # If there's no command or no folder, it's not our bot
                if not cmdline or not cwd or len(cmdline) < 2:
                    continue
                
                # We turn the command list into a single string to compare it easily
                cmd_str = " ".join(cmdline).lower()
                norm_cwd = os.path.normpath(cwd).lower()

                # Check if this process matches any of our configured bots
                for bot_id, info in bots.items():
                    if bot_id in self.managed_processes:
                        continue
                    
                    # We check if the command and the folder match
                    target_parts = info['cmd'].lower().split()
                    target_args = " ".join(target_parts[1:]) if len(target_parts) > 1 else target_parts[0]
                    target_path = os.path.normpath(info['path']).lower()
                    
                    # This part is a bit tricky, we check if the path is the same
                    path_match = (target_path == norm_cwd) or (norm_cwd.endswith(target_path.split(":")[-1].replace("\\", "/").strip("/").lower()))
                    cmd_match = target_args in cmd_str
                    
                    if cmd_match and path_match:
                        # If it matches, we start tracking it!
                        self.managed_processes[bot_id] = psutil.Process(proc.info['pid'])
                        log.info(f"Connected to existing bot: {info['name']} (PID: {proc.info['pid']})")
                        found_count += 1
                        break
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                # If we can't access a process, we just skip it
                continue
        return found_count

    def find_all_processes_in_path(self, bot_path):
        """Scans the entire OS to find any process running from the bot's folder."""
        found_pids = []
        target_path = os.path.normpath(bot_path).lower()
        
        for proc in psutil.process_iter(['pid', 'name', 'cwd', 'cmdline']):
            try:
                cwd = proc.info.get('cwd')
                if not cwd: continue
                
                norm_cwd = os.path.normpath(cwd).lower()
                # Check if it's running in that folder or a subfolder
                if norm_cwd.startswith(target_path):
                    # We also want to verify it’s likely a python process
                    cmdline = proc.info.get('cmdline')
                    if cmdline and any('python' in arg.lower() for arg in cmdline):
                         found_pids.append(proc.info['pid'])
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        return found_pids

    def is_running(self, bot_id):
        """Check if a bot is currently running."""
        process = self.managed_processes.get(bot_id)
        # If we have a process and psutil says it's alive, then it's running
        return process and process.is_running()

    async def stop_process(self, bot_id):
        """Try to stop a bot nicely, but kill it if it takes too long."""
        self.manual_stop.add(bot_id)
        
        bot_config = self.config.get("bots", {}).get(bot_id)
        systemd_service = bot_config.get("systemd_service") if bot_config else None

        # 1. Try systemd if available (only on Linux)
        if systemd_service and os.name == 'posix':
            # Run blocking systemctl command in a thread
            await asyncio.to_thread(self.stop_service, systemd_service)
        
        # 2. Rogue cleanup: Kill ANY process still running from that bot's folder
        bot_path = bot_config.get("path") if bot_config else None
        if bot_path:
            rogue_pids = await asyncio.to_thread(self.find_all_processes_in_path, bot_path)
            for pid in rogue_pids:
                try:
                    p = psutil.Process(pid)
                    if p.is_running():
                        log.info(f"Force-killing rogue process {pid} in {bot_path}")
                        p.kill() # Direct kill for rogues
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass

        # 3. Standard cleanup: the tracked process
        process = self.managed_processes.get(bot_id)
        if process is not None and process.is_running():
            log.info(f"Terminating tracked process for {bot_id} (PID: {process.pid})")
            process.terminate()
            try:
                for _ in range(int(self.stop_timeout * 10)):
                    if not process.is_running():
                        break
                    await asyncio.sleep(0.1)
                if process.is_running():
                    process.kill()
                    log.warning(f"Bot {bot_id} killed.")
            except psutil.NoSuchProcess:
                pass
            
            self.managed_processes.pop(bot_id, None)
            await asyncio.sleep(self.restart_wait)
            return True
        
        self.managed_processes.pop(bot_id, None)
        return True

    async def start_process(self, bot_id: str, bot_config, env: dict):
        """This function starts a new bot process or systemd service."""
        systemd_service = bot_config.systemd_service if hasattr(bot_config, 'systemd_service') else bot_config.get("systemd_service")
        
        if systemd_service and os.name == 'posix':
            success = self.start_service(systemd_service)
            if success:
                # For systemd, wait a bit for the PID to be assigned
                await asyncio.sleep(self.restart_wait)
                pid = await self.get_systemd_pid_async(systemd_service)
                return pid if pid else "systemd"
            return None

        # If the bot is already running, we don't need to do anything
        if bot_id in self.managed_processes and self.managed_processes[bot_id].is_running():
            log.info(f"Bot {bot_id} is already running.")
            return self.managed_processes[bot_id].pid

        try:
            # We figure out where the log file should go
            log_file_path = os.path.join(bot_config.path, bot_config.log)
            # Create the folder for logs if it doesn't exist yet
            os.makedirs(os.path.dirname(log_file_path), exist_ok=True)
            
            # We open the log file in 'append' mode ('a') so we don't delete old logs
            with open(log_file_path, "a", encoding="utf-8") as log_file:
                # subprocess.Popen starts the program in the background
                new_proc = subprocess.Popen(
                    bot_config.cmd.split(), # We split the command string into a list
                    cwd=bot_config.path, # Run it inside the bot's folder
                    env=env, # Pass it the environment variables
                    stdout=log_file, # Save normal output to the log file
                    stderr=subprocess.STDOUT, # Save error output to the same log file
                    # This flag is for Windows to keep the processes separate
                    creationflags=0x00000200 if os.name == 'nt' else 0 
                )
            
            # Now we use psutil to keep track of it using its PID (Process ID)
            self.managed_processes[bot_id] = psutil.Process(new_proc.pid)
            log.info(f"Started bot {bot_id} (PID: {new_proc.pid})")
            return new_proc.pid
        except Exception as e:
            # If something goes wrong, we log the error and return None
            log.error(f"Failed to start bot {bot_id}: {e}")
            return None

    async def restart_process(self, bot_id: str, bot_config, env: dict):
        """Unified restart logic: uses systemctl restart for Linux services if available."""
        # Handle bot_config being either an object (BotConfig) or a raw dictionary
        if hasattr(bot_config, 'systemd_service'):
            systemd_service = bot_config.systemd_service
        else:
            systemd_service = bot_config.get("systemd_service")
        
        if systemd_service and os.name == 'posix':
            # 1. First, tell the manager to expect a manual stop (to prevent alerts)
            self.manual_stop.add(bot_id)
            # 2. Force-clean any existing matching PIDs before starting
            await self.stop_process(bot_id)
            # 3. Use systemctl restart
            success = await asyncio.to_thread(self.restart_service, systemd_service)
            if success:
                # Give it a moment to stabilize
                await asyncio.sleep(self.restart_wait)
                # Ensure we track the new PID (with retries)
                pid = await self.get_systemd_pid_async(systemd_service)
                if pid:
                    try:
                        self.managed_processes[bot_id] = psutil.Process(pid)
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        pass
                return pid if pid else "systemd"
            return None

        # Fallback: stop then start
        await self.stop_process(bot_id)
        return await self.start_process(bot_id, bot_config, env)

    def start_service(self, service_name):
        """Starts a systemd service."""
        try:
            log.info(f"Starting systemd service: {service_name}")
            subprocess.run(['sudo', 'systemctl', 'start', service_name], check=True)
            return True
        except Exception as e:
            log.error(f"Failed to start systemd service {service_name}: {e}")
            return False

    def stop_service(self, service_name):
        """Stops a systemd service."""
        try:
            log.info(f"Stopping systemd service: {service_name}")
            subprocess.run(['sudo', 'systemctl', 'stop', service_name], check=True)
            return True
        except Exception as e:
            log.error(f"Failed to stop systemd service {service_name}: {e}")
            return False

    def restart_service(self, service_name):
        """Restarts a systemd service (better for applying updates)."""
        try:
            log.info(f"Restarting systemd service: {service_name}")
            subprocess.run(['sudo', 'systemctl', 'restart', service_name], check=True)
            return True
        except Exception as e:
            log.error(f"Failed to restart systemd service {service_name}: {e}")
            return False

    def get_systemd_state(self, service_name):
        """Checks the status of a systemd service on Linux."""
        if os.name != 'posix':
            return "unknown"
        
        try:
            # Check if the service is active
            result = subprocess.run(
                ['systemctl', 'is-active', service_name],
                capture_output=True, text=True, check=False
            )
            status = result.stdout.strip()
            return status # active, inactive, failed, etc.
        except Exception as e:
            log.error(f"Error checking systemd service {service_name}: {e}")
            return "error"

    async def get_systemd_pid_async(self, service_name, retries=3):
        """Async version of get_systemd_pid with retries."""
        for i in range(retries):
            pid = self.get_systemd_pid(service_name)
            if pid: return pid
            if i < retries - 1:
                await asyncio.sleep(1.0) # Wait for systemd to assign PID
        return None

    def get_systemd_pid(self, service_name):
        """Gets the MainPID of a systemd service."""
        if os.name != 'posix':
            return None
            
        try:
            result = subprocess.run(
                ['systemctl', 'show', '-p', 'MainPID', '--value', service_name],
                capture_output=True, text=True, check=False
            )
            pid_str = result.stdout.strip()
            if pid_str and pid_str != '0':
                return int(pid_str)
        except Exception as e:
            log.error(f"Error getting PID for systemd service {service_name}: {e}")
        return None

    def get_stats(self, bot_id):
        """Returns CPU, RAM, and Uptime stats for a tracked bot."""
        process = self.managed_processes.get(bot_id)
        bot_config = self.config.get("bots", {}).get(bot_id)
        systemd_service = bot_config.get("systemd_service") if bot_config else None

        # Proactive Re-discovery: If we lost the process (e.g. after a manager restart), 
        # try to find it one last time before reporting it as 'Stopped'.
        if not process or not process.is_running():
            # 1. Try systemd if applicable
            if systemd_service:
                pid = self.get_systemd_pid(systemd_service)
                if pid:
                    try:
                        process = psutil.Process(pid)
                        self.managed_processes[bot_id] = process
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        process = None
            
            # 2. If still not found, try a general discovery (e.g. for standalone bots)
            if not process or not process.is_running():
                log.info(f"[Stats] Bot {bot_id} not running or stalely tracked. Running discovery...")
                self.discover_processes()
                process = self.managed_processes.get(bot_id)
                if process and process.is_running():
                    log.info(f"[Stats] Bot {bot_id} re-discovered during stats check (PID: {process.pid})")
                else:
                    log.debug(f"[Stats] Bot {bot_id} discovery failed.")

        if not process or not process.is_running():
            return None
            
        try:
            with process.oneshot():
                cpu = process.cpu_percent()
                ram_mb = process.memory_info().rss / (1024 * 1024)
                create_time = process.create_time()
                uptime_sec = datetime.datetime.now().timestamp() - create_time
                
                # Disk I/O
                try:
                    io = process.io_counters()
                    disk_mb = (io.read_bytes + io.write_bytes) / (1024 * 1024)
                except (psutil.AccessDenied, AttributeError):
                    disk_mb = None

            return {
                "cpu": cpu,
                "ram_mb": ram_mb,
                "uptime_sec": uptime_sec,
                "pid": process.pid,
                "disk_mb": disk_mb
            }
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            return None

    def fetch_unexpected_stops(self):
        """This function finds bots that stopped by themselves (crashed or service failed)."""
        bots = self.config.get("bots", {})
        stopped_bots = []
        
        for bot_id, info in bots.items():
            process = self.managed_processes.get(bot_id)
            systemd_service = info.get("systemd_service")
            
            # If it's a systemd service, we check its official state
            if systemd_service and os.name == 'posix':
                state = self.get_systemd_state(systemd_service)
                # If it's active but we don't have a PID, try to find it
                if state == "active":
                    if not process or not process.is_running():
                        pid = self.get_systemd_pid(systemd_service)
                        if pid:
                            try:
                                process = psutil.Process(pid)
                                self.managed_processes[bot_id] = process
                            except (psutil.NoSuchProcess, psutil.AccessDenied):
                                pass
                elif state in ["inactive", "failed"]:
                    # If it's inactive/failed and we didn't stop it ourselves
                    if bot_id not in self.manual_stop:
                        stopped_bots.append((bot_id, info))
                    self.managed_processes.pop(bot_id, None)
                continue

            # Standard process check
            if process:
                # If psutil says it's not running anymore...
                if not process.is_running():
                    # ...and we didn't stop it ourselves...
                    if bot_id not in self.manual_stop:
                        # ...then it must have crashed!
                        stopped_bots.append((bot_id, info))
                    # Stop tracking it since it's dead
                    self.managed_processes.pop(bot_id, None)
            
            # If a bot was manually stopped, and it's really gone now, we reset the flag
            if bot_id in self.manual_stop:
                if not process or not process.is_running():
                    self.manual_stop.remove(bot_id)
                    
        return stopped_bots
