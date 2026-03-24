# 🤖 Discord Bot Manager

A robust, modular Discord bot designed to oversee, update, and monitor multiple independent Discord bots on a Windows machine. It runs silently in the background and provides a centralized command center for all your bots.

## 🚀 Features

- **Silent Background Execution**: Child bots are launched with hidden console windows (ideal for Task Scheduler).
- **Process Monitoring**: Real-time status tracking and resource usage (CPU, RAM, Uptime).
- **Automated Updates**: Integrated Git pull and pip dependency installation.
- **Self-Management**: The manager can update and restart itself via Discord commands.
- **Crash Alerts**: Real-time notifications if a managed bot stops unexpectedly.
- **Audit Logging**: Rotating log system with a detailed command history (who used which command).
- **Resource Monitoring**: Track CPU (%), RAM (MB), and Uptime for every managed bot via `/status`.
- **Git Rollback**: Quickly revert to the previous Git state (`HEAD@{1}`) if an update breaks anything.
- **Log Access**: Remote retrieval of bot log files directly through Discord.

## 🛠️ Installation

1. **Clone the repository**:
   ```bash
   git clone <repo-url>
   cd discord_bot_manager
   ```

2. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

3. **Configuration**:
   - Create a `.env` file with your `DISCORD_TOKEN`, `GUILD_ID`, and `ADMIN_CHANNEL_ID`.
   - Edit `config.json` to map your Bot IDs to their local paths and start commands.

4. **Run the Manager**:
   ```bash
   python manager.py
   ```

## 📜 Commands

- `/status`: View all bots' status and resource usage.
- `/update <bot_name>`: Git pull + pip install + restart.
- `/restart <bot_name>`: Immediate restart without updating.
- `/rollback <bot_name>`: Revert to the version before the last update.
- `/logs <bot_name> [lines]`: Fetch the last N lines of logs (default: 50).

## 📂 Project Structure

- `manager.py`: Core logic and background process monitor.
- `cogs/`: Command modules (Admin & Monitoring).
- `core/`: Shared utilities and decorators.
- `config.json`: Persistent configuration for managed bots.
