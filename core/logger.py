import logging
import sys
from logging.handlers import RotatingFileHandler

def setup_logger(name="BotManager"):
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

        # File Handler (Rotating log: max 5MB, keep 3 backups)
        file_handler = RotatingFileHandler('manager.log', maxBytes=5*1024*1024, backupCount=3, encoding='utf-8')
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    return logger

# Create a default instance for easy import
log = setup_logger()
