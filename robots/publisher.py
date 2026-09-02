import json
import time
import os 
from config import get_logger, get_robot_id
import paho.mqtt.client as mqtt


logger = get_logger("publisher")
ROBOT_ID = get_robot_id()
MQTT_HOST = os.environ.get("MQTT_HOST", "localhost")
MQTT_PORT = int(os.environ.get("MQTT_PORT", "1883"))
EVENTS_FILE = os.environ.get("EVENTS_FILE", "data/events.jsonl")


logger.info(f"[{ROBOT_ID}] starting up")

def load_my_events(events_file:str,robot_id:str)->list[dict]:
    my_events = []
    with open(events_file,"r") as f:
        for line in f:
            line=line.strip()
            if not line:
                continue
            event = json.loads(line)
            if event.get("robot_id") == robot_id:
                my_events.append(event)
    my_events.sort(key=lambda e: e["t"])
    return my_events

events = load_my_events(EVENTS_FILE, ROBOT_ID)
logger.info(f"[{ROBOT_ID}] loaded {len(events)} events")

def on_connect(client,userdata,flags,reason_code,properties):
    if reason_code == 0:
        logger.info(f"[{ROBOT_ID}] connected to broker at {MQTT_HOST}:{MQTT_PORT}")
    else:
        logger.error(f"[{ROBOT_ID}] connection failed: {reason_code}")

def on_disconnect(client, userdata, flags, reason_code, properties):
    logger.warning(f"[{ROBOT_ID}] disconnected from broker: {reason_code}")


client = mqtt.Client(
    mqtt.CallbackAPIVersion.VERSION2,
    client_id=f"robot-{ROBOT_ID}",
)
client.on_connect = on_connect
client.on_disconnect = on_disconnect 

client.connect(MQTT_HOST, MQTT_PORT)

client.loop_start()

SPEED_MULTIPLIER = float(os.environ.get("SPEED_MULTIPLIER", "10"))
logger.info(f"[{ROBOT_ID}] publishing {len(events)} events at {SPEED_MULTIPLIER}x speed")


previous_t = 0
for event in events:
    real_gap = event["t"] - previous_t
    sleep_time = real_gap / SPEED_MULTIPLIER
    time.sleep(max(sleep_time, 0))

    topic = f"robots/{ROBOT_ID}/state"
    payload = json.dumps(event)
    client.publish(topic, payload, qos=1, retain=True)

    logger.info(f"[{ROBOT_ID}] published t={event['t']} status={event.get('status')}")

    previous_t = event["t"]

logger.info(f"[{ROBOT_ID}] done publishing, exiting")
client.loop_stop()
client.disconnect()