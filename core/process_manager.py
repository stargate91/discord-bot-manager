import os
import sys
import asyncio
import subprocess
import psutil
import datetime
from core.logger import log

class ProcessManager:
    def __init__(self, config, messages):
        self.config = config
        self.messages = messages
        self.managed_processes = {} # bot_id -> psutil.Process
        self.manual_stop = set() # bot_id
        
        # Pull settings from config
        bot_settings = self.config.get("bot_settings", {})
        self.stop_timeout = bot_settings.get("stop_timeout", 5)
        self.restart_wait = bot_settings.get("restart_wait", 2.0)

    def discover_processes(self):
        """Scans the system for already running bot processes based on the configuration."""
        bots = self.config.get("bots", {})
        found_count = 0
        
        for proc in psutil.process_iter(['pid', 'name', 'cmdline', 'cwd']):
            try:
                cmdline = proc.info.get('cmdline')
                cwd = proc.info.get('cwd')
                if not cmdline or not cwd or len(cmdline) < 2:
                    continue
                
                cmd_str = " ".join(cmdline).lower()
                norm_cwd = os.path.normpath(cwd).lower()

                for bot_id, info in bots.items():
                    if bot_id in self.managed_processes:
                        continue
                    
                    target_parts = info['cmd'].lower().split()
                    target_args = " ".join(target_parts[1:]) if len(target_parts) > 1 else target_parts[0]
                    target_path = os.path.normpath(info['path']).lower()
                    
                    path_match = (target_path == norm_cwd) or (norm_cwd.endswith(target_path.split(":")[-1].replace("\\", "/").strip("/").lower()))
                    cmd_match = target_args in cmd_str
                    
                    if cmd_match and path_match:
                        self.managed_processes[bot_id] = psutil.Process(proc.info['pid'])
                        log.info(f"Connected to existing bot: {info['name']} (PID: {proc.info['pid']})")
                        found_count += 1
                        break
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue
        return found_count

    def is_running(self, bot_id):
        """Checks if a bot is currently running and tracked."""
        process = self.managed_processes.get(bot_id)
        return process and process.is_running()

    async def stop_process(self, bot_id):
        """Gracefully stops a bot process with a timeout fallback."""
        process = self.managed_processes.get(bot_id)
        if process is not None and process.is_running():
            self.manual_stop.add(bot_id)
            process.terminate()
            try:
                # We use a primitive wait loop to stay async-friendly
                for _ in range(int(self.stop_timeout * 10)):
                    if not process.is_running():
                        break
                    await asyncio.sleep(0.1)
                
                if process.is_running():
                    process.kill()
                    log.warning(f"Bot {bot_id} did not stop gracefully, killed.")
            except psutil.NoSuchProcess:
                pass
            
            self.managed_processes.pop(bot_id, None)
            await asyncio.sleep(self.restart_wait)
            return True
        return False

    def start_process(self, bot_id: str, bot_config, env: dict):
        """Starts a bot process if it's not already running."""
        if bot_id in self.managed_processes and self.managed_processes[bot_id].is_running():
            log.info(f"Bot {bot_id} is already running.")
            return self.managed_processes[bot_id].pid

        try:
            # Use bot_config attributes
            # The bot_config object is expected to have 'path', 'cmd', and 'log' attributes
            log_file_path = os.path.join(bot_config.path, bot_config.log)
            os.makedirs(os.path.dirname(log_file_path), exist_ok=True)
            
            with open(log_file_path, "a", encoding="utf-8") as log_file:
                new_proc = subprocess.Popen(
                    bot_config.cmd.split(),
                    cwd=bot_config.path,
                    env=env,
                    stdout=log_file,
                    stderr=subprocess.STDOUT,
                    creationflags=0x00000200 if os.name == 'nt' else 0 # CREATE_NEW_PROCESS_GROUP
                )
            
            self.managed_processes[bot_id] = psutil.Process(new_proc.pid)
            log.info(f"Started bot {bot_id} (PID: {new_proc.pid})")
            return new_proc.pid
        except Exception as e:
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
        """Identifies bots that stopped without a manual command."""
        bots = self.config.get("bots", {})
        stopped_bots = []
        
        for bot_id, info in bots.items():
            process = self.managed_processes.get(bot_id)
            if process:
                if not process.is_running():
                    if bot_id not in self.manual_stop:
                        stopped_bots.append((bot_id, info))
                    self.managed_processes.pop(bot_id, None)
            
            # Reset manual stop flag if process is gone
            if bot_id in self.manual_stop:
                if not process or not process.is_running():
                    self.manual_stop.remove(bot_id)
                    
        return stopped_bots
