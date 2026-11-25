# utils/logger.py - Application-wide logging configuration.
# This file sets up clean, formatted log messages so we can see
# what the extraction pipeline is doing at every step.

import logging
import sys


def setup_logger(name: str = "data_extractor") -> logging.Logger:
    """
    Creates and configures a standard logger.

    Args:
        name: The name of the logger instance.

    Returns:
        logging.Logger: Configured logger ready to write formatted messages.
    """
    logger = logging.getLogger(name)

    # If handlers are already configured, avoid adding duplicates
    if logger.handlers:
        return logger

    logger.setLevel(logging.INFO)

    # Format: Timestamp | Log Level | Module Name | Message
    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
        datefmt="%H:%M:%S",
    )

    # StreamHandler prints messages to stdout/console
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    return logger


# Global logger instance for convenience
logger = setup_logger()
