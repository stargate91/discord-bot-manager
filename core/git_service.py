import os
import subprocess
import sys
from core.logger import log

# This class handles everything related to GitHub (downloading code, updating etc.)
class GitService:
    def __init__(self, config, messages):
        self.config = config
        self.messages = messages

    def clean_locks(self, path):
        """This function deletes '.lock' files that sometimes stop Git from working on Windows."""
        lock_path = os.path.join(path, ".git", "index.lock")
        if os.path.exists(lock_path):
            try:
                os.remove(lock_path)
                log.info(f"Cleaned stale lock: {lock_path}")
                return True
            except Exception as e:
                # If we couldn't remove it, we log the error
                log.error(f"Failed to clean lock {lock_path}: {e}")
        return False

    def update_repo(self, path, branch="origin/main"):
        """This function downloads the latest code from GitHub."""
        self.clean_locks(path)
        results = []
        try:
            # 1. We ask Git to fetch all the latest changes
            fetch_out = subprocess.check_output(
                ["git", "fetch", "--all"], 
                cwd=path, 
                stderr=subprocess.STDOUT
            ).decode('utf-8')
            results.append(fetch_out)
            
            # 2. We force the local code to be exactly like the code on GitHub
            reset_out = subprocess.check_output(
                ["git", "reset", "--hard", branch], 
                cwd=path, 
                stderr=subprocess.STDOUT
            ).decode('utf-8')
            results.append(reset_out)
            
            return True, "\n".join(results)
        except subprocess.CalledProcessError as e:
            # If a command fails, we get the error message it outputted
            error_msg = e.output.decode('utf-8') if e.output else str(e)
            log.error(f"Git update failed at {path}: {error_msg}")
            return False, error_msg
        except Exception as e:
            log.error(f"Unexpected error during git update at {path}: {e}")
            return False, str(e)

    def rollback_repo(self, path):
        """This function undoes the last update if it broke something."""
        self.clean_locks(path)
        try:
            # HEAD@{1} is a Git trick to go back one step in time
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
        """This function installs the libraries the bot needs using 'pip'."""
        req_path = os.path.join(path, "requirements.txt")
        # If there is no requirements file, there is nothing to install
        if not os.path.exists(req_path):
            return True, "No requirements.txt found."
            
        try:
            # We run 'pip install' just like we would in a terminal
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
