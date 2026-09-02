import os
import sys
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)

def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)

def get_robot_id() -> str:
    robot_id = os.environ.get("ROBOT_ID")
    if not robot_id:
        logging.getLogger("config").error(
            "ROBOT_ID environment variable is required"
        )
        sys.exit(1)
    return robot_id