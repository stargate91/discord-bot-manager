import os
import subprocess
import sys
from core.logger import log

class GitService:
    def __init__(self, config, messages):
        self.config = config
        self.messages = messages

    def clean_locks(self, path):
        """Removes stale .git/index.lock files that often block operations on Windows."""
        lock_path = os.path.join(path, ".git", "index.lock")
        if os.path.exists(lock_path):
            try:
                os.remove(lock_path)
                log.info(f"Cleaned stale lock: {lock_path}")
                return True
            except Exception as e:
                log.error(f"Failed to clean lock {lock_path}: {e}")
        return False

    def update_repo(self, path, branch="origin/main"):
        """Performs git fetch and git reset --hard to the specified branch."""
        self.clean_locks(path)
        results = []
        try:
            # 1. Fetch
            fetch_out = subprocess.check_output(
                ["git", "fetch", "--all"], 
                cwd=path, 
                stderr=subprocess.STDOUT
            ).decode('utf-8')
            results.append(fetch_out)
            
            # 2. Reset
            reset_out = subprocess.check_output(
                ["git", "reset", "--hard", branch], 
                cwd=path, 
                stderr=subprocess.STDOUT
            ).decode('utf-8')
            results.append(reset_out)
            
            return True, "\n".join(results)
        except subprocess.CalledProcessError as e:
            error_msg = e.output.decode('utf-8') if e.output else str(e)
            log.error(f"Git update failed at {path}: {error_msg}")
            return False, error_msg
        except Exception as e:
            log.error(f"Unexpected error during git update at {path}: {e}")
            return False, str(e)

    def rollback_repo(self, path):
        """Rollback to the previous state using HEAD@{1}."""
        self.clean_locks(path)
        try:
            output = subprocess.check_output(
                ["git", "reset", "--hard", "HEAD@{1}"],
                cwd=path,
                stderr=subprocess.STDOUT
            ).decode('utf-8')
            return True, output
        except subprocess.CalledProcessError as e:
            error_msg = e.output.decode('utf-8') if e.output else str(e)
            log.error(f"Rollback failed at {path}: {error_msg}")
            return False, error_msg
        except Exception as e:
            return False, str(e)

    def install_dependencies(self, path):
        """Installs dependencies from requirements.txt if it exists."""
        req_path = os.path.join(path, "requirements.txt")
        if not os.path.exists(req_path):
            return True, "No requirements.txt found."
            
        try:
            output = subprocess.check_output(
                [sys.executable, "-m", "pip", "install", "-r", "requirements.txt"],
                cwd=path,
                stderr=subprocess.STDOUT
            ).decode('utf-8')
            return True, output
        except subprocess.CalledProcessError as e:
            error_msg = e.output.decode('utf-8') if e.output else str(e)
            log.error(f"Pip install failed at {path}: {error_msg}")
            return False, error_msg
        except Exception as e:
            return False, str(e)
