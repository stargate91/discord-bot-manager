import logging
import sys
from logging.handlers import RotatingFileHandler

# Default configuration (can be moved to a config loader if needed)
LOG_FILE = 'manager.log'
MAX_BYTES = 5*1024*1024
BACKUP_COUNT = 3

def setup_logger(name="BotManager", log_file=LOG_FILE, max_bytes=MAX_BYTES, backup_count=BACKUP_COUNT):
    # Create logger
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)

    # Avoid adding handlers if they already exist (for module reloads)
    if not logger.handlers:
        # Create formatters
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

        # Console Handler
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

        # File Handler (Rotating log)
        file_handler = RotatingFileHandler(log_file, maxBytes=max_bytes, backupCount=backup_count, encoding='utf-8')
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    return logger

    logger.info(f"Logger reconfigured: {log_file} (Max: {max_bytes}, Backups: {backup_count})")

def setup_discord_logging(log_file, max_bytes, backup_count):
    """Sets up the 'discord' logger to write to the same file."""
    logger = logging.getLogger("discord")
    logger.setLevel(logging.INFO)
    
    # Remove old handlers
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)
        handler.close()
        
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    
    # File Handler
    file_handler = RotatingFileHandler(log_file, maxBytes=max_bytes, backupCount=backup_count, encoding='utf-8')
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    
    # Console Handler (Optional, but good for debugging)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

# Create a default instance for easy import
log = setup_logger()
