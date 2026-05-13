# System Architecture Structure

## 1. General Overview of the System
The **Multiplayer Gaming Platform** is a real-time, event-driven microservices architecture designed to support scalable multiplayer experiences. It acts as the backbone for connecting players, managing game lobbies, executing real-time game logic (Rock Paper Scissors), and maintaining distributed state.

**High-Level Architecture:**
The platform relies on a set of loosely coupled microservices written in Python (FastAPI), communicating primarily through **Redis Pub/Sub** for real-time messaging and **Redis Streams** for event sourcing. Clients connect via WebSockets to a centralized Gateway.

**Main Architecture Goals:**
- **Real-time Performance:** Low-latency communication via WebSockets.
- **Scalability:** Microservices can be scaled independently.
- **Fault Tolerance:** Robust handling of player disconnects and service restarts.
- **Authoritative Server:** Game logic is strictly enforced on the backend.

---

## 2. Detailed Description of Each Service

### Gateway Service (Port 3000)
- **Responsibility:** Entry point for all client traffic. Manages WebSocket connections and acts as a **Reverse Proxy** for HTTP requests to other services.
- **Authentication:** Handles `/auth/login`, mapping usernames to unique IDs and issuing JWT tokens.
- **Proxying:** Routes `/leaderboard/*` to the Leaderboard service and `/lobbies/*` to the Lobby service.
- **Message Routing:** Dispatches WebSocket messages (Matchmaking, Lobby, Game, Chat) to the respective services via Redis Pub/Sub.
- **Failure Handling:** Emits `PLAYER_DISCONNECTED` events when WebSockets close, triggering cleanups across the system.

### Matchmaking Service (Port 3001)
- **Responsibility:** Matches players of similar rating in different game modes (Casual, Ranked).
- **Algorithm:** Uses a skill-based matching algorithm that widens rating thresholds over time.
- **Lobby Integration:** Automatically triggers lobby creation upon finding a match via the `lobby:create_from_match` channel.

### Lobby Service (Port 3002)
- **Responsibility:** Manages pre-game coordination. Players can join, leave, and set themselves as "Ready".
- **Lifecycle:** Transitions from `CREATED` -> `WAITING` -> `READY` -> `GAME_STARTED`.
- **Fault Tolerance:** Listens for `PLAYER_DISCONNECTED` events from the event stream to automatically remove inactive players from lobbies.

### Game Session Service (Port 3003)
- **Responsibility:** Authoritative host for Rock Paper Scissors.
- **Logic:** 3s countdown -> Move collection -> Round resolution -> Game conclusion (First to 3).
- **Disconnects:** Automatically awards the win to the remaining player if an opponent drops.

### Leaderboard Service (Port 3004)
- **Responsibility:** Persistent ranking of players.
- **Categories:** Global, Casual, Ranked.
- **Global Sync:** All mode-specific updates are also reflected in the "Global" leaderboard.
- **Username Capture:** Listens for connection events to link IDs to usernames across all rankings.

### Chat Service (Port 3005)
- **Responsibility:** Manages real-time communication between players.
- **Channels:** Supports global, lobby-specific, and direct message channels.
- **Persistence:** Maintains a rolling history of the last 100 messages per channel in Redis.

### Notification Service (Port 3006)
- **Responsibility:** Manages and delivers asynchronous alerts to players.
- **Triggers:** Sends notifications for match found, ranking changes, lobby status, and system broadcasts.
- **Persistence:** Stores the last 100 notifications per player, tracking read/unread status.

---

## 3. Communication Architecture

- **WebSocket:** Bi-directional real-time link between Client and Gateway.
- **Redis Pub/Sub:** High-speed event bus for inter-service requests and gateway updates (e.g., `game:action`, `gateway:lobby_update`).
- **Redis Streams:** Persistent event sourcing for a reliable audit trail of all platform actions (`events:*` keys).
- **HTTP Proxying:** Gateway uses `httpx` to route RESTful API calls to internal microservices, providing a single unified endpoint for the frontend.

---

## 4. Rock Paper Scissors Flow

1. **Start:** Lobby sends `session:create_from_lobby` after all players are ready.
2. **Countdown:** Server starts a 3s timer; clients show "Get Ready".
3. **Turn:** Status becomes `in_progress`. Server waits for `rps_move` (via `game:action`) from both players.
4. **Resolution:** Server calculates winner, increments score, and starts the next round countdown or ends the game.
5. **Leaderboard:** Upon `game_finished`, ratings are calculated and published to the Leaderboard service.

---

## 5. Fault Tolerance & Scaling

- **Resilience:** If a service crashes, Redis maintains the source of truth for session and player states.
- **Cleanup:** Disconnect events are propagated system-wide to ensure no "ghost" players remain in lobbies or games.
- **Scaling:** Horizontal scaling is supported by the stateless design of most services, utilizing Redis for shared distributed state and Pub/Sub for communication.
