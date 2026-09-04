# Peppermint Fleet Backend

Backend for a robot fleet management dashboard, built for the **Peppermint
Robotics SDE-1 hiring challenge**.

Eight simulated robots publish live telemetry (position, battery, status)
over MQTT. A backend service ingests that feed, keeps a single source of
truth for fleet state, and exposes it two ways at once — a WebSocket
stream for consumers who want live pushes, and a REST endpoint for
consumers who'd rather poll. Both are backed by the same state, so they
can never disagree with each other.

---

## Tech stack

| Layer | Choice | Why |
|---|---|---|
| Broker | Mosquitto (MQTT) | Lightweight pub/sub, retained messages give reconnecting clients last-known state for free, QoS gives delivery guarantees without hand-rolling them |
| Backend | FastAPI (Python) | Native async, first-class WebSocket support, fast to iterate on |
| Mock fleet | Python, one process per robot | Matches "8 compose services / 8 processes, not 8 coroutines" requirement in the brief |
| Orchestration | Docker Compose | Single `docker compose up`, no manual setup, broker healthcheck gates backend/robot startup |

## Architecture

```
robots/ (8 publisher     →  broker/ (Mosquitto)  →  backend/ (FastAPI)
processes, one per          retained topics per      ├─ mqtt_consumer.py (MQTT thread → event loop bridge)
robot, replaying              robot                   ├─ state.py (in-memory fleet state)
data/events.jsonl)                                    ├─ connection_manager.py (WebSocket fanout)
                                                       ├─ WebSocket /ws  ──▶ live clients (snapshot + deltas)
                                                       └─ REST /fleet    ──▶ polling clients
```

- **Broker (`broker/`):** Each robot publishes to `robots/{robot_id}/state`,
  retained. A backend that restarts, or a client that reconnects, gets the
  last known value immediately instead of waiting for the next tick.
  Healthcheck (`mosquitto_pub` ping) gates `depends_on` for both the
  backend and every robot, so nothing starts trying to connect before the
  broker can actually accept connections.
- **Mock robot fleet (`robots/`):** One publisher per robot in
  `robots.json`, replaying that robot's own recorded events from
  `data/events.jsonl` in order — standing in for what the real robot would
  report live.
- **Backend service (`backend/`):**
  - `mqtt_consumer.py` subscribes to `robots/+/state`. Its `on_message`
    callback runs on paho-mqtt's own background thread, so it hands data
    to the asyncio event loop via `asyncio.run_coroutine_threadsafe`
    rather than touching shared state directly from that thread.
  - `state.py` holds fleet state as a plain `dict[robot_id, entry]`, no
    lock. Because every write is routed onto the single-threaded event
    loop (see above) and a dict assignment has no `await` inside it, no
    two writes/reads can interleave mid-operation.
  - `connection_manager.py` tracks connected WebSocket clients, each with
    its own `asyncio.Queue`. A new connection gets the full current
    snapshot immediately (so it starts in sync with what REST would
    return at that instant), then deltas as they arrive.
  - `main.py` wires the above together and exposes `/fleet` (REST) and
    `/ws` (WebSocket).
- **Docker Compose:** Brings up the broker, backend, and mock fleet
  together, no manual steps beyond `docker compose up --build`.

## Project layout

```
peppermint-fleet-backend/
├── broker/                    # Mosquitto config
├── robots/                    # Mock robot publishers
├── backend/
│   ├── main.py                 # FastAPI app, routes, startup wiring
│   ├── state.py                 # Fleet state store
│   ├── connection_manager.py     # WebSocket client tracking + fanout
│   ├── mqtt_consumer.py           # MQTT subscribe + thread→loop bridge
│   ├── requirements.txt
│   ├── Dockerfile
│   └── tests/
│       └── test_state.py       # Tests for state.py (see "Testing" below)
├── data/                       # robots.json, events.jsonl (provided fixtures)
├── docker-compose.yml
├── README.md
├── ANSWERS.md                  # 3 written answers, backend track
├── SYSTEM_DESIGN.md            # 5 written answers, backend track
└── .gitignore
```

## Running it

```bash
docker compose up --build
```

- Backend REST: `http://localhost:8001/fleet`
- Backend WebSocket: `ws://localhost:8001/ws`

(Mapped to host port 8001, not 8000, only because port 8000 was already in
use locally by an unrelated container on the dev machine — the backend
itself listens on 8000 inside its own container, and other services reach
it via `backend:8000` on Compose's internal network.)

## Testing

```bash
cd backend
python3 -m pip install -r requirements.txt
python3 -m pytest tests/ -v
```

Tests cover `state.py`, identified as the trickiest correctness-critical
logic to get right — not the MQTT wiring itself, which is mostly plumbing
best verified by integration testing (i.e. actually running the stack, as
described above), but the in-memory state store that both the WebSocket
stream and the REST endpoint read from:

- Basic store/retrieve correctness.
- **`get_snapshot()` returns an independent copy, not a live reference** —
  the one non-obvious behavior that, if broken, could let a REST response
  reflect a mix of old and new state mid-serialization.
- Malformed input (missing a required field) raises loudly rather than
  silently storing partial data — deliberate, since this is trusted,
  known-shape data from our own publishers, so a missing key signals a
  bug in our own pipeline, not something to paper over.

## AI delegation notes

This backend was built with Claude (Anthropic) as a coding partner, used
deliberately as a teaching/pair-programming tool rather than for
unreviewed code generation: concepts (MQTT retained messages/QoS, the
asyncio event loop vs. paho's background thread, `call_soon_threadsafe`,
snapshot-vs-delta WebSocket design) were explained first, design
decisions were reasoned through and defended before code was written, and
every file was walked through line by line as it landed. Real tracebacks
were debugged from pasted output, not descriptions. All architectural
decisions (MQTT over Kafka/RabbitMQ/Redis, QoS 1, env-var robot identity,
no-lock dict + `call_soon_threadsafe`, snapshot-then-delta WebSocket
payloads, separating `state.py`/`connection_manager.py`/`mqtt_consumer.py`
by concern) were made and can be explained/defended by the author; AI was
not used to generate ANSWERS.md/SYSTEM_DESIGN.md content wholesale, only
to help organize reasoning already worked through in conversation.

## Known gaps / what's next

These are the honest limitations of what a ~6–10 hour timebox allowed.
None of them are hidden or papered over — see ANSWERS.md Q3 and
SYSTEM_DESIGN.md for fuller reasoning on each.

- **MQTT reconnect handling is incomplete.** The broker connection itself
  has no `on_disconnect` + auto-reconnect logic wired up in
  `mqtt_consumer.py` yet — if the broker connection drops mid-run (not
  just at startup, which the healthcheck already covers), the backend
  won't currently recover automatically. Flagged as the next thing to
  build given more time.
- **No timestamp check on incoming updates.** `update_robot()` overwrites
  `fleet_state[robot_id]` unconditionally, with nothing comparing the
  incoming update's time against what's already stored — so an
  out-of-order message (delivered late, after a newer one) could briefly
  make a robot appear to jump backward. A small, targeted fix, not yet
  made.
- **No schema validation** on incoming MQTT payloads — the backend trusts
  the shape of the data because it's produced by our own publishers, but
  this wouldn't hold up against malformed or unexpected input.
- **No staleness detection.** `last_updated` is stored on every update
  but nothing reads it back — a robot that crashes simply stops updating,
  with `fleet_state` freezing at its last known values and no signal to
  REST/WebSocket consumers that anything's wrong.
- Optional stretch goal (`GET /robots/history/{robot_id}`) — not
  attempted; out of scope for the timebox. See `SYSTEM_DESIGN.md` Q1 for
  how it would plug in.
