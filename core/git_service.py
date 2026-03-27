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
        """This helper removes stuck .git/index.lock files that prevent updates."""
        lock_file = os.path.join(path, ".git", "index.lock")
        if os.path.exists(lock_file):
            try:
                os.remove(lock_file)
                log.info(f"Removed stuck Git lock file: {lock_file}")
            except Exception as e:
                log.error(f"Failed to remove Git lock file {lock_file}: {e}")

    def get_commit_details(self, path, rev="HEAD"):
        """Gets the hash, author, and subject of a specific revision."""
        try:
            # Hash (short)
            commit_hash = subprocess.check_output(["git", "rev-parse", "--short", rev], cwd=path).decode('utf-8').strip()
            # Author
            author = subprocess.check_output(["git", "show", "-s", "--format=%an", rev], cwd=path).decode('utf-8').strip()
            # Message
            message = subprocess.check_output(["git", "show", "-s", "--format=%s", rev], cwd=path).decode('utf-8').strip()
            # Date (relative)
            date = subprocess.check_output(["git", "show", "-s", "--format=%cr", rev], cwd=path).decode('utf-8').strip()
            
            return {
                "hash": commit_hash,
                "author": author,
                "message": message,
                "date": date
            }
        except Exception as e:
            log.error(f"Failed to get commit details for {rev} at {path}: {e}")
            return None

    def get_remote_url(self, path):
        """Gets the web URL of the remote origin."""
        try:
            url = subprocess.check_output(["git", "config", "--get", "remote.origin.url"], cwd=path).decode('utf-8').strip()
            # Convert SSH or .git URL to standard HTTPS web URL
            if url.startswith("git@"):
                url = url.replace(":", "/").replace("git@", "https://")
            if url.endswith(".git"):
                url = url[:-4]
            return url
        except Exception:
            return None

    def update_repo(self, path, branch="origin/main"):
        """This function downloads the latest code from GitHub."""
        self.clean_locks(path)
        results = []
        try:
            # 0. Get current HEAD hash before update
            old_hash = subprocess.check_output(
                ["git", "rev-parse", "HEAD"], 
                cwd=path, 
                stderr=subprocess.STDOUT
            ).decode('utf-8').strip()

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

            # 3. Get new HEAD hash after update
            new_hash = subprocess.check_output(
                ["git", "rev-parse", "HEAD"], 
                cwd=path, 
                stderr=subprocess.STDOUT
            ).decode('utf-8').strip()

            changed = old_hash != new_hash
            details = None
            if changed:
                details = self.get_commit_details(path)
                if details:
                    details["repo_url"] = self.get_remote_url(path)
            
            return True, "\n".join(results), changed, details
        except subprocess.CalledProcessError as e:
            # If a command fails, we get the error message it outputted
            error_msg = e.output.decode('utf-8') if e.output else str(e)
            log.error(f"Git update failed at {path}: {error_msg}")
            return False, error_msg, False, None
        except Exception as e:
            log.error(f"Unexpected error during git update at {path}: {e}")
            return False, str(e), False, None

    def rollback_repo(self, path):
        """This function undoes the last update if it broke something."""
        # self.clean_locks(path) # Removed to avoid clutter if not needed here
        try:
            # Rollback ref from config
            rollback_ref = self.config.get("bot_settings", {}).get("rollback_ref", "HEAD@{1}")
            output = subprocess.check_output(
                ["git", "reset", "--hard", rollback_ref],
                cwd=path,
                stderr=subprocess.STDOUT
            ).decode('utf-8')
            
            details = self.get_commit_details(path)
            if details:
                details["repo_url"] = self.get_remote_url(path)
                
            return True, output, True, details
        except subprocess.CalledProcessError as e:
            error_msg = e.output.decode('utf-8') if e.output else str(e)
            log.error(f"Rollback failed at {path}: {error_msg}")
            return False, error_msg, False, None
        except Exception as e:
            return False, str(e), False, None

    def install_dependencies(self, path):
        """This function installs the libraries the bot needs using 'pip'."""
        req_path = os.path.join(path, "requirements.txt")
        # If there is no requirements file, there is nothing to install
        if not os.path.exists(req_path):
            msg = self.messages.get("error_no_requirements", "No requirements.txt found.")
            return True, msg
            
        try:
            # We run 'pip install' just like we would in a terminal
            req_file = self.config.get("bot_settings", {}).get("requirements_file", "requirements.txt")
            output = subprocess.check_output(
                [sys.executable, "-m", "pip", "install", "-r", req_file],
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
