# Project Architecture

## Backend Architecture
- **Framework**: FastAPI (Python) providing REST endpoints and WebSocket routes.
- **Authentication Service** (`auth_service.py`): X25519 key exchange, challenge‑response, session management, rate limiting, pending device workflow.
- **Capture Service** (`capture_service.py`): Configurable screen capture using OpenCV, runs in an asyncio task, provides frames to the stream service.
- **Stream Service** (`stream_service.py`): UDP socket handling, receives encrypted frames from the client, reassembles them, and forwards to the dashboard via internal queues.
- **Crypto Service** (`crypto_service.py`): Key generation, signature verification, HKDF‑derived session keys, X25519 exchange utilities.
- **Device Registry** (`device_registry.py`): Persistent JSON storage for trusted, blocked, recent, and rejected clients under `backend/data/`.
- **Logger Service** (`logger.py`): Rotating file logger with JSON‑structured events for security‑relevant actions.

## Frontend Architecture
- **Stack**: React + Vite (JavaScript/TypeScript) bundled into `dist/` for production.
- **Dashboard** (`src/`):
  - **WebSocket client** connects to `/ws/dashboard` for real‑time events (pending requests, device updates, stats).
  - **Pages**: Device list, live video canvas, security statistics, logs view.
  - **State Management**: Simple React hooks; data refreshed via WebSocket messages.
- **Build**: `npm run build` outputs static files served by FastAPI's static route.

## Client Architecture (WindowsClient)
- **Entry point**: `main.py` sets up logging, creates a `ConnectionManager`.
- **Connection Manager** (`core/connection_manager.py`): Manages WebSocket to `/ws/auth`, handles HELLO, CHALLENGE_RESPONSE, and maintains session state.
- **State Machine** (`core/state_machine.py`): Tracks connection phases (disconnected, authenticating, streaming).
- **Retry Policy** (`core/retry_policy.py`): Exponential back‑off for reconnect attempts.
- **Video Window UI** (`ui/video_window.py`): Uses OpenCV to display streamed frames locally.

## Data Flow (Screen Streaming Pipeline)
```mermaid
flowchart LR
    A[Screen Capture] --> B[Encoding]
    B --> C[Encryption]
    C --> D[Transport (UDP)]
    D --> E[Client Rendering (Dashboard)]
```
1. **Client** captures the screen region and encodes frames.
2. Frames are encrypted with a session key.
3. Encrypted packets are sent over UDP to the server.
4. Server decrypts, reassembles frames, and pushes them to the dashboard.
5. Dashboard renders the live video.

## Session Lifecycle
- Session created after successful challenge verification.
- TTL = 30 min (configurable via `SESSION_TTL`).
- Single‑use sessions are revoked on WebSocket disconnect.
- Garbage collector runs every 60 s to prune expired sessions and challenges.

## Streaming Lifecycle
- Client captures frames according to config (region, fps, quality).
- Frames encrypted with session key and sent over UDP to the server port.
- Server binds UDP socket on startup; if bind fails, the server runs in degraded mode (no UDP).
- Stream service buffers frames, discards out‑of‑order packets, and forwards ordered frames to the dashboard.

## Component Responsibilities
- **Auth Service**: Device registration, pending queue, challenge issuance, session creation, revocation.
- **Capture Service**: Screen capture, frame encoding, quality scaling.
- **Stream Service**: UDP socket management, packet ordering, stats collection.
- **Device Registry**: Persistent storage of trusted/blocked/recent devices.
- **Logger**: Structured event logging, log rotation, exposure via `/api/logs`.
- **Dashboard**: Real‑time UI, device approvals, security metrics visualization.
- **Client Connection Manager**: WebSocket lifecycle, session key handling, error recovery.
- **Client UI**: Local video preview, user‑triggered shutdown.
