from datetime import datetime, timezone
import logging

logger = logging.getLogger("state")

fleet_state: dict[str, dict] = {}


def update_robot(data: dict) -> dict:
    """
    Merge one incoming update into fleet_state for its robot_id.
    Returns the delta that was applied, so the caller can decide
    what to do with it (e.g. broadcast it) without state.py needing
    to know who's listening.
    """
    try:
        robot_id = data["robot_id"]
        entry = {
            "robot_id": robot_id,
            "x": data["x"],
            "y": data["y"],
            "status": data["status"],
            "battery": data["battery"],
            "last_updated": datetime.now(timezone.utc).isoformat(),
        }
    except KeyError as e:
        logger.error(f"Malformed robot update, missing key {e}: {data}")
        raise
    fleet_state[robot_id] = entry
    return entry


def get_snapshot() -> dict:
    """
    Full current fleet state, as a plain dict of robot_id -> entry.
    Used both by the REST endpoint and to seed a new WebSocket
    connection, so both start from exactly the same data.
    """
    return dict(fleet_state)