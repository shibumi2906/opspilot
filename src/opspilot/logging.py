import sys

from loguru import logger


def configure_logging() -> None:
    # Log only explicit safe summaries; never log settings, request headers or exception values.
    logger.remove()
    logger.add(sys.stderr, serialize=True, diagnose=False, backtrace=False)
