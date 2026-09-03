import asyncio
import json
import os 
import logging
import paho.mqtt.client as mqtt

from state import update_robot

logger = logging.getLogger("mqtt_consumer")

MQTT_HOST = os.environ.get("MQTT_HOST", "localhost")
MQTT_PORT = int(os.environ.get("MQTT_PORT", 1883))
 
async def handle_update(data: dict, manager):
    """
    Runs ON THE EVENT LOOP (scheduled via run_coroutine_threadsafe).
    Does the two steps that must happen together, in order:
    write to state, then notify connected WebSocket clients.
    """
    try:
        entry = update_robot(data)
    except KeyError:
        return  # already logged inside update_robot; nothing to broadcast
    await manager.broadcast(entry)

def start_mqtt_consumer(loop: asyncio.AbstractEventLoop, manager):
    """
    Sets up the MQTT client and starts its network loop on paho's
    own background thread. Called once at FastAPI startup.
    """
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
 
    def on_connect(client, userdata, flags, reason_code, properties):
        logger.info(f"Connected to broker, reason_code={reason_code}")
        # '+' is a single-level MQTT wildcard: matches robots/r1/state,
        # robots/r2/state, ... robots/r8/state in one subscription,
        # instead of subscribing to each robot's topic individually.
        client.subscribe("robots/+/state", qos=1)
 
    def on_message(client, userdata, msg):
        # THIS RUNS ON PAHO'S BACKGROUND THREAD — must not touch
        # fleet_state or the WebSocket clients directly.
        try:
            data = json.loads(msg.payload)
        except json.JSONDecodeError:
            logger.error(f"Non-JSON MQTT payload on {msg.topic}: {msg.payload!r}")
            return
        # Hand off to the event loop safely.
        asyncio.run_coroutine_threadsafe(handle_update(data, manager), loop)
 
    client.on_connect = on_connect
    client.on_message = on_message
    client.connect(MQTT_HOST, MQTT_PORT)
    client.loop_start()  # spawns the background network thread
    return client