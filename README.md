# Multiplayer Gaming Platform

A distributed real-time multiplayer gaming platform built with **Python** (FastAPI), **WebSockets**, **Redis Pub/Sub**, and **Event Sourcing**.

## System Architecture

### High-Level Overview

```mermaid
graph TB
    Client(["🎮 Client\n(Browser / App)"])

    subgraph compose["Docker Compose Network"]
        GW["**Gateway**\n:3000\nWebSocket · JWT Auth · HTTP Proxy"]

        subgraph microservices["Microservices"]
            MM["**Matchmaking**\n:3001\nSkill-based queue"]
            LB["**Lobby**\n:3002\nPre-game coordination"]
            GS["**Game Session**\n:3003\nRPS authoritative logic"]
            LD["**Leaderboard**\n:3004\nRankings · Sorted Sets"]
            CH["**Chat**\n:3005\nChannels · Message history"]
            NT["**Notification**\n:3006\nAlerts · Read status"]
        end

        subgraph datalayer["Data Layer"]
            REDIS[("**Redis 7**\n:6379\n─────────────────\nSingle Node\nAOF Persistence\n(no replication)\n─────────────────\nPub/Sub  ·  Sorted Sets\nHashes   ·  Lists · Sets\nStreams  (Event Store)")]
        end
    end

    Client <-->|"WebSocket /ws?token=JWT"| GW
    Client <-->|"HTTP  /auth  /leaderboard  /lobbies"| GW

    GW -.->|"HTTP Proxy /leaderboard/*"| LD
    GW -.->|"HTTP Proxy /lobbies/*"| LB

    GW <-->|"Pub/Sub + State R/W"| REDIS
    MM <-->|"Pub/Sub + State R/W"| REDIS
    LB <-->|"Pub/Sub + State R/W"| REDIS
    GS <-->|"Pub/Sub + State R/W"| REDIS
    LD <-->|"Sorted Sets R/W"| REDIS
    CH <-->|"Pub/Sub + Lists/Sets"| REDIS
    NT <-->|"Pub/Sub + Lists"| REDIS
```
---

### Service-to-Service Communication (Redis Pub/Sub Channels)

All inter-service messaging is routed through Redis Pub/Sub. The diagram below shows the logical flow (each arrow represents a publish → subscribe relationship via a named Redis channel).

```mermaid
flowchart LR
    GW["Gateway\n:3000"]
    MM["Matchmaking\n:3001"]
    LB["Lobby\n:3002"]
    GS["Game Session\n:3003"]
    LD["Leaderboard\n:3004"]
    CH["Chat\n:3005"]
    NT["Notification\n:3006"]

    GW -->|"matchmaking:requests\nmatchmaking:cancel"| MM
    MM -->|"gateway:match_found"| GW
    MM -->|"lobby:create_from_match"| LB

    GW -->|"lobby:create / join / leave / ready"| LB
    LB -->|"gateway:lobby_update"| GW
    LB -->|"session:create_from_lobby"| GS
    LB -->|"notification:send"| NT

    GW -->|"game:action"| GS
    GS -->|"gateway:game_event\nsession:{id}:state"| GW
    GS -->|"leaderboard:update"| LD
    GS -->|"notification:send"| NT

    LD -->|"gateway:ranking_changed"| GW

    GW -->|"chat:join / chat:message"| CH
    CH -->|"gateway:chat_message"| GW

    GW -->|"notification:send\nnotification:broadcast"| NT
    NT -->|"gateway:notification"| GW
```

---

### Redis Data Layout

| Key Pattern | Structure | Owner | Description |
|---|---|---|---|
| `player:{id}:status` | String | Gateway | Player online/offline status |
| `lobby:{id}` | Hash/JSON | Lobby | Full lobby state |
| `lobby:{id}:ready:{player_id}` | String | Lobby | Per-player ready flag |
| `match:{id}` | Hash/JSON | Matchmaking | Match metadata |
| `session:{id}` | Hash/JSON | Game Session | Session metadata |
| `session:{id}:state` | Hash/JSON | Game Session | Live game state |
| `leaderboard:{category}` | Sorted Set | Leaderboard | Rankings (global / casual / ranked) |
| `player_stats:{id}:{category}` | Hash | Leaderboard | Per-player statistics |
| `chat:channel:{id}:members` | Set | Chat | Online members in channel |
| `chat:channel:{id}:messages` | List | Chat | Rolling last-100 messages |
| `notifications:{player_id}` | List | Notification | Last-100 notifications with read status |
| `events:{stream_id}` | Stream | All services | Immutable event-sourcing log |

---

### Services

| Service | Port | Responsibility |
|---------|------|----------------|
| Gateway | 3000 | WebSocket entry point, JWT auth, HTTP reverse proxy, message routing |
| Matchmaking | 3001 | Skill-based player queue (Casual / Ranked), auto-creates lobby on match |
| Lobby | 3002 | Pre-game coordination: join, leave, ready — transitions to Game Session |
| Game Session | 3003 | Authoritative Rock Paper Scissors logic, disconnect handling |
| Leaderboard | 3004 | Persistent rankings via Redis Sorted Sets (global / casual / ranked) |
| Chat | 3005 | Channel-based messaging with rolling 100-message history |
| Notification | 3006 | Async alerts with read/unread tracking, last-100 per player |
| Redis | 6379 | Pub/Sub bus · Distributed state · Event Sourcing streams |

---

## Quick Start

```bash
docker-compose up --build
```

Requires Docker & Docker Compose. All services start automatically.

## Project Structure

```
.
├── docker-compose.yml
├── requirements.txt
├── shared/                # Auth, event sourcing, Redis client, Pydantic types
└── services/
    ├── gateway/           # :3000
    ├── matchmaking/       # :3001
    ├── lobby/             # :3002
    ├── game-session/      # :3003
    ├── leaderboard/       # :3004
    ├── chat/              # :3005
    └── notification/      # :3006
```