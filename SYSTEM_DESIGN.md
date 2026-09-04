1. What happens if we ask you to add a new feature to this later? Does your current design
accommodate that, or does it need a rework? Walk through a specific feature and where it would
plug in.
ANS= A good example is the optional stretch feature: GET /robots/history/{robot_id}, which would return a robot's past states over a time range.

It would plug in easily because of one design choice already in state.py: update_robot() returns the entry it just saved, instead of silently saving it and returning nothing. Right now, the only thing that uses that returned entry is mqtt_consumer.py, which passes it to broadcast() so WebSocket clients get told about it.

To add history, I'd just add a second thing that uses that same returned entry: alongside broadcasting it, also save it into a small database (e.g. SQLite — one row per update: robot_id, x, y, status, battery, last_updated). Then a new REST route would just query that database for one robot, filtered by time.

No existing file would need to change — state.py, connection_manager.py, and the WebSocket/REST endpoints all stay exactly as they are. That's because the current design already separates "something changed" from "who reacts to it," so adding a new reaction (saving history) doesn't touch the old ones (broadcasting live updates).

2. What happens if the number of robots grows a lot, say from eight to five hundred? What is the
first thing that breaks, and why that specifically?

ANS= The first thing to break is ConnectionManager.broadcast(). It loops over every connected WebSocket client on every single incoming update — cost scales with (update rate) × (number of connected clients). At 8 robots publishing every ~5 seconds, that's roughly negligible. At 500 robots, that's ~100 updates/second; with even 50 dashboard clients connected, that's ~5,000 queue-puts per second, and this cost grows multiplicatively as either number increases, not linearly.

The deeper reason this happens is that the whole design — fleet_state, the MQTT consumer, and all WebSocket fanout — lives in one process's memory, on one asyncio event loop. That's fine at 8 robots, but it means you can't scale by just running more backend instances behind a load balancer, since each instance would hold its own separate fleet_state and they'd disagree. At that scale I'd move the broker to something like AWS IoT Core or a managed MQTT service built for many devices, and separate "receiving updates" from "fanning out to dashboard clients" — e.g. a shared store (Redis) that multiple backend instances read from, so WebSocket fanout is no longer one process's job alone.


3. What happens if bandwidth is limited and robots and the backend can only exchange a small amount of data per second? What would you change about what you send, how often, or how much detail it carries?

ANS= With limited bandwidth, three changes would help, in order of impact. First, stop publishing on a fixed 5-second tick regardless of whether anything changed — instead, publish only when x, y, status, or battery actually change meaningfully (e.g. position moved more than some small threshold, or battery changed by more than 1%). A stationary, fully-charged robot would then send almost nothing, while an actively moving robot still updates promptly — this is better than just slowing the fixed interval (e.g. to 20-30s), which would save bandwidth uniformly but make fast-moving robots' dashboard positions noticeably stale.

Second, shrink each message itself: shorter field names (id instead of robot_id, b instead of battery) and fewer decimal places on x/y if the dashboard doesn't need sub-unit precision — small per-message savings that compound across many messages.

Third, apply the same "only send real changes" idea to the WebSocket fanout side (broadcast()) — currently every MQTT update becomes a WebSocket delta unconditionally; the same change-detection logic could be applied once, upstream, so bandwidth is saved on both legs (robot→backend and backend→dashboard) rather than just one.

4. What happens if a robot goes down mid task and stops responding? What should the rest of the
system do about it, and how would it even find out?

ANS= Right now, nothing detects a robot going down. Looking at mqtt_consumer.py and state.py: update_robot() stores a last_updated timestamp on every message, but nothing reads it back. If a robot crashes mid-task, it simply stops publishing — no MQTT message ever arrives saying "I'm down." fleet_state[robot_id] just freezes at its last known values forever, and both REST and WebSocket keep reporting that frozen state as if it were current, with no signal that anything is wrong.

The honest fix, given more time: add a periodic background task (independent of MQTT) that sweeps fleet_state every few seconds, compares each robot's last_updated to the current time, and marks any robot "status": "offline" if too long has passed since its last update (e.g. 3× the expected ~5s publish interval). This status change would go through the same path as a real update — it would be broadcast to WebSocket clients and reflected in the next REST response — so the dashboard would visibly show a robot as offline instead of silently continuing to display stale data as if it were live.


5. What happens if the connection between a robot and the backend is slow or unreliable, and
updates arrive late, out of order, or not at all for a while? What does the rest of the system see
during that time, and how does it recover once the connection is healthy again?

ANS= Late-but-arriving messages need no special handling — update_robot() just applies whatever it receives whenever it arrives. This does expose a real gap: since update_robot() overwrites fleet_state[robot_id] unconditionally with no timestamp check, an out-of-order message (an older update delayed behind a newer one) could briefly make a robot appear to jump backward in position or battery level. Given more time, I'd have update_robot() compare the incoming timestamp against the currently stored one and skip the write if the incoming message is older.

If a robot disconnects and later reconnects, no special recovery is needed on the backend side either — the backend stays subscribed to robots/+/state the entire time, so it simply resumes receiving that robot's messages normally once it starts publishing again.

Where retain=True (from Session 1's MQTT setup) actually matters is if the backend itself restarts and has to resubscribe from scratch — retained messages mean it immediately gets every robot's last known state back from the broker, rather than waiting up to ~5 seconds per robot for the next natural publish.

On the WebSocket side, if a robot goes quiet, connected clients simply stop receiving deltas about it — nothing errors, but (tying back to SYSTEM_DESIGN.md Q4) there's currently no staleness flag, so a client can't distinguish "quiet but fine" from "actually offline." If a WebSocket client itself disconnects and reconnects, ConnectionManager.connect() re-seeds it with a full fresh snapshot, so it always resyncs correctly regardless of how long it was disconnected.