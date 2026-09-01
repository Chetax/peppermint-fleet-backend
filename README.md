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
| Orchestration | Docker Compose | Single `docker compose up`, no manual setup |

## Architecture

```
robots/ (8 publisher     →  broker/ (Mosquitto)  →  backend/ (FastAPI)
processes, one per          retained topics per      ├─ MQTT consumer
robot, replaying              robot                   ├─ in-memory fleet state
data/events.jsonl)                                    ├─ WebSocket stream  ──▶ live clients
                                                       └─ REST /fleet       ──▶ polling clients
```

- **Broker (`broker/`):** Each robot publishes to `robots/{robot_id}/state`,
  retained. A backend that restarts, or a client that reconnects, gets the
  last known value immediately instead of waiting for the next tick.
- **Mock robot fleet (`robots/`):** One publisher per robot in
  `robots.json`, replaying that robot's own recorded events from
  `data/events.jsonl` in order — standing in for what the real robot would
  report live.
- **Backend service (`backend/`):** Subscribes to all robot topics,
  maintains fleet state in memory, and serves it via WebSocket (push) and
  REST (pull) from the same store.
- **Docker Compose:** Brings up the broker, backend, and mock fleet
  together, no manual steps beyond `docker compose up`.

## Project layout

```
peppermint-fleet-backend/
├── broker/              # Mosquitto config
├── robots/              # Mock robot publishers
├── backend/             # FastAPI ingestion + WebSocket + REST
├── data/                # robots.json, events.jsonl (provided fixtures)
├── tests/               # Tests for the trickiest part
├── docker-compose.yml
├── README.md
├── ANSWERS.md
├── SYSTEM_DESIGN.md
└── .gitignore
```

## Running it

```bash
docker compose up --build
```

- Backend REST: `http://localhost:8000/fleet`
- Backend WebSocket: `ws://localhost:8000/ws`

*(Exact ports/routes will be finalized as the backend lands — this section
gets updated then.)*

## What's next

This is the first commit — just the README and Docker Compose scaffold.
The plan is to build this out incrementally (broker config → mock robot
publishers → backend ingestion → WebSocket/REST → tests), with each piece
landing as its own commit/branch as the project moves forward.