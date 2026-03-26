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

    def is_running(self, bot_id):
        """Check if a bot is currently running."""
        process = self.managed_processes.get(bot_id)
        # If we have a process and psutil says it's alive, then it's running
        return process and process.is_running()

    async def stop_process(self, bot_id):
        """Try to stop a bot nicely, but kill it if it takes too long."""
        process = self.managed_processes.get(bot_id)
        if process is not None and process.is_running():
            # We add it to manual_stop so it doesn't restart automatically
            self.manual_stop.add(bot_id)
            # Ask the process to stop nicely
            process.terminate()
            try:
                # We wait a little bit to see if it stops by itself
                for _ in range(int(self.stop_timeout * 10)):
                    if not process.is_running():
                        break
                    await asyncio.sleep(0.1)
                
                # If it's still running after the wait, we force it to stop
                if process.is_running():
                    process.kill()
                    log.warning(f"Bot {bot_id} did not stop gracefully, killed.")
            except psutil.NoSuchProcess:
                # If the process is already gone, that's fine too
                pass
            
            # Stop tracking this process
            self.managed_processes.pop(bot_id, None)
            # Give it a tiny bit of time to fully exit
            await asyncio.sleep(self.restart_wait)
            return True
        return False

    def start_process(self, bot_id: str, bot_config, env: dict):
        """This function starts a new bot process."""
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

    def get_stats(self, bot_id):
        """Returns CPU, RAM, and Uptime stats for a tracked bot."""
        process = self.managed_processes.get(bot_id)
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
        """This function finds bots that stopped by themselves (crashed)."""
        bots = self.config.get("bots", {})
        stopped_bots = []
        
        for bot_id, info in bots.items():
            process = self.managed_processes.get(bot_id)
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
