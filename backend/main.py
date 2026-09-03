import asyncio
import logging

from fastapi import FastAPI, WebSocket, WebSocketDisconnect

from state import get_snapshot
from connection_manager import ConnectionManager
from mqtt_consumer import start_mqtt_consumer

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("main")

app = FastAPI()
manager = ConnectionManager()


@app.on_event("startup")
async def on_startup():
    loop = asyncio.get_event_loop()
    start_mqtt_consumer(loop, manager)
    logger.info("MQTT consumer started")

@app.get("/fleet")
async def get_fleet():
    return get_snapshot()

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket, get_snapshot())
    queue = manager.active[websocket]
    try:
        while True:
            message = await queue.get()
            await websocket.send_json(message)
    except WebSocketDisconnect:
        pass
    finally:
        manager.disconnect(websocket)
 