# logger_config.py
import logging
import os
from datetime import datetime

def setup_logger(name: str):
    """Return a logger instance with file + console handlers."""

    LOG_FILE = f"{datetime.now().strftime('%m_%d_%Y_%H_%M_%S')}.log"
    log_path = os.path.join(os.getcwd(), "logs")
    os.makedirs(log_path, exist_ok=True)

    LOG_FILEPATH = os.path.join(log_path, LOG_FILE)

    # Configure logging only once
    logging.basicConfig(
        level=logging.INFO,
        format="[%(asctime)s] %(lineno)d %(name)s - %(levelname)s - %(message)s",
        handlers=[
            logging.FileHandler(LOG_FILEPATH),
            logging.StreamHandler()
        ],
        force=True  # ensure reconfig when called from different modules
    )

    return logging.getLogger(name)
